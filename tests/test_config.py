from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from codex_quota.config import ensure_config, load_config, save_config
from codex_quota.filesystem import PRIVATE_DIR_MODE
from codex_quota.models import AppConfig


def test_ensure_config_creates_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CODEX_QUOTA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("CODEX_QUOTA_PROFILES_DIR", str(tmp_path / "profiles"))

    cfg = ensure_config()

    assert cfg.profiles_dir == tmp_path / "profiles"
    assert (tmp_path / "config" / "config.json").is_file()
    data = json.loads((tmp_path / "config" / "config.json").read_text(encoding="utf-8"))
    assert "profiles" not in data
    if os.name == "posix":
        assert stat.S_IMODE((tmp_path / "config").stat().st_mode) == PRIVATE_DIR_MODE


def test_load_config_ignores_old_profiles_registry_but_preserves_extra(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "profiles_dir": "~/custom-profiles",
                "codex_bin": "codex-dev",
                "profiles": {"old": {"codex_home": "/tmp/old"}},
                "custom": True,
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(path)

    assert cfg.codex_bin == "codex-dev"
    assert cfg.extra["profiles"] == {"old": {"codex_home": "/tmp/old"}}
    assert cfg.extra["custom"] is True


def test_save_config_preserves_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    cfg = AppConfig(profiles_dir=tmp_path / "profiles", extra={"profiles": {"old": {}}})

    save_config(cfg, path)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["profiles"] == {"old": {}}
    assert data["profiles_dir"] == str(tmp_path / "profiles")
