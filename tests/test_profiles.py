from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from codex_quota.errors import ProfileError, ProfileNameError, ProfileNotFoundError
from codex_quota.filesystem import PRIVATE_DIR_MODE
from codex_quota.models import AppConfig
from codex_quota.profiles import (
    add_profile,
    discover_profiles,
    ensure_profiles_dir,
    get_profile,
    profile_path,
    remove_profile,
)


def config(tmp_path: Path) -> AppConfig:
    return AppConfig(profiles_dir=tmp_path / "profiles")


@pytest.mark.parametrize("name", ["personal", "work-1", "foo.bar", "foo_bar", "a1"])
def test_validate_and_add_profile(tmp_path: Path, name: str) -> None:
    cfg = config(tmp_path)
    profile = add_profile(cfg, name)

    assert profile.name == name
    assert profile.codex_home.is_dir()
    assert profile.codex_home == (cfg.profiles_dir / name).resolve()
    if os.name == "posix":
        assert stat.S_IMODE(cfg.profiles_dir.stat().st_mode) == PRIVATE_DIR_MODE
        assert stat.S_IMODE(profile.codex_home.stat().st_mode) == PRIVATE_DIR_MODE


@pytest.mark.parametrize(
    "name",
    ["", ".", "..", "../x", "/tmp/x", "a/b", "a\\b", " name", "x y", "$bad"],
)
def test_rejects_unsafe_profile_names(tmp_path: Path, name: str) -> None:
    with pytest.raises(ProfileNameError):
        profile_path(config(tmp_path), name)


def test_profile_path_returns_direct_child_of_profiles_dir(tmp_path: Path) -> None:
    cfg = config(tmp_path)

    path = profile_path(cfg, "personal")

    assert path == (tmp_path / "profiles" / "personal").resolve()
    assert path.parent == (tmp_path / "profiles").resolve()


def test_discover_profiles_scans_directories_only(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    add_profile(cfg, "personal")
    add_profile(cfg, "work")
    (cfg.profiles_dir / "README").write_text("ignore", encoding="utf-8")
    (cfg.profiles_dir / "bad name").mkdir()

    assert [profile.name for profile in discover_profiles(cfg)] == ["personal", "work"]


def test_discover_profiles_ignores_nested_directories(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    profile = add_profile(cfg, "personal")
    (profile.codex_home / "nested").mkdir()

    assert [item.name for item in discover_profiles(cfg)] == ["personal"]


def test_discover_profiles_ignores_symlinked_directories(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    add_profile(cfg, "personal")
    external = tmp_path / "external-profile"
    external.mkdir()
    cfg.profiles_dir.mkdir(parents=True, exist_ok=True)
    (cfg.profiles_dir / "linked").symlink_to(external, target_is_directory=True)

    assert [item.name for item in discover_profiles(cfg)] == ["personal"]


def test_ensure_profiles_dir_tightens_existing_permissions(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("POSIX permission bits are required for this assertion")

    cfg = config(tmp_path)
    cfg.profiles_dir.mkdir(parents=True, exist_ok=True)
    cfg.profiles_dir.chmod(0o755)

    ensure_profiles_dir(cfg)

    assert stat.S_IMODE(cfg.profiles_dir.stat().st_mode) == PRIVATE_DIR_MODE


def test_get_profile_requires_existing_directory(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    add_profile(cfg, "personal")

    assert get_profile(cfg, "personal").name == "personal"
    with pytest.raises(ProfileNotFoundError):
        get_profile(cfg, "missing")


def test_add_profile_fails_if_existing_without_exist_ok(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    add_profile(cfg, "personal")

    with pytest.raises(ProfileError):
        add_profile(cfg, "personal")

    assert add_profile(cfg, "personal", exist_ok=True).name == "personal"


def test_add_profile_fails_if_path_exists_as_file(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    cfg.profiles_dir.mkdir(parents=True)
    (cfg.profiles_dir / "personal").write_text("not a dir", encoding="utf-8")

    with pytest.raises(ProfileError):
        add_profile(cfg, "personal")


def test_remove_profile_deletes_only_profile_dir(tmp_path: Path) -> None:
    cfg = config(tmp_path)
    profile = add_profile(cfg, "personal")
    (profile.codex_home / "config.toml").write_text("", encoding="utf-8")

    removed = remove_profile(cfg, "personal")

    assert removed.name == "personal"
    assert not profile.codex_home.exists()
    assert cfg.profiles_dir.exists()


def test_remove_profile_rejects_missing_profile(tmp_path: Path) -> None:
    cfg = config(tmp_path)

    with pytest.raises(ProfileNotFoundError):
        remove_profile(cfg, "missing")
