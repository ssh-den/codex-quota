from __future__ import annotations

import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from codex_quota.config import (
    auth_refresh_due,
    ensure_config,
    get_last_auth_refresh,
    load_config,
    persist_auth_refresh,
    save_config,
    with_auth_refresh,
)
from codex_quota.filesystem import PRIVATE_DIR_MODE
from codex_quota.models import AppConfig


def test_ensure_config_creates_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CODEX_QUOTA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("CODEX_QUOTA_PROFILES_DIR", str(tmp_path / "profiles"))

    cfg = ensure_config()

    assert cfg.profiles_dir == tmp_path / "profiles"
    assert (tmp_path / "config" / "config.json").is_file()
    data = json.loads((tmp_path / "config" / "config.json").read_text(encoding="utf-8"))
    assert "profiles" not in data
    if os.name == "posix":
        assert stat.S_IMODE((tmp_path / "config").stat().st_mode) == PRIVATE_DIR_MODE


def test_load_config_ignores_old_profiles_registry_but_preserves_extra(
    tmp_path: Path,
) -> None:
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


def test_legacy_config_without_auth_refresh_loads_cleanly(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"profiles_dir": str(tmp_path / "profiles")}), encoding="utf-8"
    )

    cfg = load_config(path)

    assert get_last_auth_refresh(cfg, "personal") is None
    assert auth_refresh_due(
        cfg, "personal", now=datetime(2026, 6, 5, 12, 0, tzinfo=UTC)
    )


def test_malformed_refresh_timestamps_are_ignored_safely(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "profiles_dir": str(tmp_path / "profiles"),
                "auth_refresh": {
                    "bad-format": "2026-06-05 10:00:00",
                    "not-a-string": 123,
                },
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(path)

    assert get_last_auth_refresh(cfg, "bad-format") is None
    assert get_last_auth_refresh(cfg, "not-a-string") is None
    assert auth_refresh_due(
        cfg, "bad-format", now=datetime(2026, 6, 5, 12, 0, tzinfo=UTC)
    )


def test_future_refresh_timestamp_is_treated_as_due(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "profiles_dir": str(tmp_path / "profiles"),
                "auth_refresh": {"personal": "2026-06-05T13:00:00Z"},
            }
        ),
        encoding="utf-8",
    )

    cfg = load_config(path)

    assert auth_refresh_due(
        cfg, "personal", now=datetime(2026, 6, 5, 12, 0, tzinfo=UTC)
    )


def test_persist_auth_refresh_preserves_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    cfg = AppConfig(
        profiles_dir=tmp_path / "profiles",
        extra={"custom": True, "auth_refresh": {"existing": "2026-06-05T08:00:00Z"}},
    )

    updated = persist_auth_refresh(
        cfg,
        "personal",
        datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
        path=path,
    )

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["custom"] is True
    assert data["auth_refresh"]["existing"] == "2026-06-05T08:00:00Z"
    assert data["auth_refresh"]["personal"] == "2026-06-05T12:00:00Z"
    assert updated.extra["custom"] is True


def test_with_auth_refresh_keeps_sibling_timestamps_and_extra_keys(
    tmp_path: Path,
) -> None:
    cfg = AppConfig(
        profiles_dir=tmp_path / "profiles",
        extra={
            "custom": {"nested": True},
            "auth_refresh": {
                "first": "2026-06-05T08:00:00Z",
                "second": "2026-06-05T09:00:00Z",
            },
        },
    )

    updated = with_auth_refresh(
        cfg,
        "third",
        datetime(2026, 6, 5, 12, 30, tzinfo=UTC),
    )

    assert updated.extra["custom"] == {"nested": True}
    assert updated.extra["auth_refresh"]["first"] == "2026-06-05T08:00:00Z"
    assert updated.extra["auth_refresh"]["second"] == "2026-06-05T09:00:00Z"
    assert updated.extra["auth_refresh"]["third"] == "2026-06-05T12:30:00Z"
