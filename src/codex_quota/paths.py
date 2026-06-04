from __future__ import annotations

import os
from pathlib import Path

from .models import Paths


def _env_path(name: str, fallback: Path) -> Path:
    value = os.environ.get(name)
    if value:
        return Path(value).expanduser()
    return fallback


def default_paths() -> Paths:
    home = Path.home()
    config_dir = _env_path(
        "CODEX_QUOTA_CONFIG_DIR",
        home / ".config" / "codex-quota",
    )
    profiles_dir = _env_path(
        "CODEX_QUOTA_PROFILES_DIR",
        home / ".codex-quota" / "profiles",
    )
    return Paths(
        config_dir=config_dir,
        config_file=config_dir / "config.json",
        profiles_dir=profiles_dir,
    )
