from __future__ import annotations

import re
import shutil
from pathlib import Path

from .errors import ProfileError, ProfileNameError, ProfileNotFoundError
from .filesystem import ensure_private_dir
from .models import AppConfig, Profile

PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def validate_profile_name(name: str) -> str:
    if not isinstance(name, str) or not name:
        raise ProfileNameError("Profile name must not be empty")
    if name in {".", ".."}:
        raise ProfileNameError("Profile name cannot be '.' or '..'")
    if "/" in name or "\\" in name:
        raise ProfileNameError("Profile name cannot contain path separators")
    if not PROFILE_NAME_RE.fullmatch(name):
        raise ProfileNameError(
            "Profile name must start with a letter or digit and contain only letters, "
            "digits, dot, underscore, or dash"
        )
    return name


def ensure_profiles_dir(config: AppConfig) -> Path:
    profiles_dir = config.profiles_dir.expanduser()
    return ensure_private_dir(profiles_dir, parents=True, exist_ok=True)


def _resolved_profiles_dir(config: AppConfig) -> Path:
    return ensure_profiles_dir(config).resolve()


def profile_path(config: AppConfig, name: str) -> Path:
    validate_profile_name(name)
    base = _resolved_profiles_dir(config)
    candidate = (base / name).resolve()

    if candidate.parent != base:
        raise ProfileError(f"Profile path escapes profiles_dir: {candidate}")

    return candidate


def discover_profiles(config: AppConfig) -> list[Profile]:
    base = ensure_profiles_dir(config)
    resolved_base = base.resolve()
    profiles: list[Profile] = []

    for entry in sorted(base.iterdir(), key=lambda item: item.name.lower()):
        if not entry.is_dir():
            continue
        if entry.is_symlink():
            continue
        try:
            validate_profile_name(entry.name)
        except ProfileNameError:
            continue
        resolved_entry = entry.resolve()
        if resolved_entry.parent != resolved_base:
            continue
        profiles.append(Profile(name=entry.name, codex_home=resolved_entry))

    return profiles


def profile_map(config: AppConfig) -> dict[str, Profile]:
    return {profile.name: profile for profile in discover_profiles(config)}


def get_profile(config: AppConfig, name: str) -> Profile:
    path = profile_path(config, name)

    if not path.is_dir():
        known = ", ".join(profile.name for profile in discover_profiles(config)) or "<none>"
        raise ProfileNotFoundError(f"Unknown profile: {name}. Known: {known}")

    return Profile(name=name, codex_home=path)


def add_profile(config: AppConfig, name: str, *, exist_ok: bool = False) -> Profile:
    path = profile_path(config, name)

    if path.exists():
        if not path.is_dir():
            raise ProfileError(f"Profile path exists and is not a directory: {path}")
        if not exist_ok:
            raise ProfileError(f"Profile already exists: {name}")
        ensure_private_dir(path, exist_ok=True)
    else:
        ensure_private_dir(path, parents=False, exist_ok=False)

    return Profile(name=name, codex_home=path)


def remove_profile(config: AppConfig, name: str) -> Profile:
    profile = get_profile(config, name)
    base = _resolved_profiles_dir(config)
    target = profile.codex_home.resolve()

    if target == base or target.parent != base:
        raise ProfileError(f"Refusing to delete unsafe profile path: {target}")

    shutil.rmtree(target)
    return profile
