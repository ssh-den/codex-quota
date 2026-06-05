from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from typer.testing import CliRunner

from codex_quota.cli import app
from codex_quota.filesystem import PRIVATE_DIR_MODE
from codex_quota.models import Profile, ProfileStatus, RateLimits, WindowLimit

runner = CliRunner()


def test_init_creates_config_and_profile_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_QUOTA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("CODEX_QUOTA_PROFILES_DIR", str(tmp_path / "profiles"))

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0
    assert (tmp_path / "config" / "config.json").exists()
    assert (tmp_path / "profiles").is_dir()
    assert not (tmp_path / "profiles" / "personal").exists()
    assert not (tmp_path / "profiles" / "client").exists()
    if os.name == "posix":
        assert stat.S_IMODE((tmp_path / "config").stat().st_mode) == PRIVATE_DIR_MODE
        assert stat.S_IMODE((tmp_path / "profiles").stat().st_mode) == PRIVATE_DIR_MODE


def test_init_preserves_existing_config_without_overwrite(
    tmp_path: Path, monkeypatch
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "profiles_dir": str(tmp_path / "custom-profiles"),
                "codex_bin": "codex-custom",
                "default_model": "custom-model",
                "reasoning_effort": "medium",
                "refresh_seconds": 12.5,
                "profiles": {"legacy": {"codex_home": "/tmp/legacy"}},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("CODEX_QUOTA_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("CODEX_QUOTA_PROFILES_DIR", str(tmp_path / "env-profiles"))

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0
    data = json.loads(config_file.read_text(encoding="utf-8"))
    assert data["profiles_dir"] == str(tmp_path / "custom-profiles")
    assert data["codex_bin"] == "codex-custom"
    assert data["default_model"] == "custom-model"
    assert data["reasoning_effort"] == "medium"
    assert data["refresh_seconds"] == 12.5
    assert data["profiles"] == {"legacy": {"codex_home": "/tmp/legacy"}}


def test_init_overwrite_config_recreates_minimal_config(
    tmp_path: Path, monkeypatch
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "profiles_dir": "/old/profiles",
                "codex_bin": "codex-old",
                "profiles": {"legacy": {"codex_home": "/tmp/legacy"}},
                "custom": True,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("CODEX_QUOTA_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("CODEX_QUOTA_PROFILES_DIR", str(tmp_path / "profiles"))

    result = runner.invoke(app, ["init", "--overwrite-config"])

    assert result.exit_code == 0
    data = json.loads(config_file.read_text(encoding="utf-8"))
    assert data["profiles_dir"] == str(tmp_path / "profiles")
    assert data["codex_bin"] == "codex"
    assert "profiles" not in data
    assert "custom" not in data


def test_profile_add_creates_profile_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_QUOTA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("CODEX_QUOTA_PROFILES_DIR", str(tmp_path / "profiles"))

    result = runner.invoke(app, ["profile", "add", "personal"])

    assert result.exit_code == 0
    assert (tmp_path / "profiles" / "personal").is_dir()
    if os.name == "posix":
        assert (
            stat.S_IMODE((tmp_path / "profiles" / "personal").stat().st_mode)
            == PRIVATE_DIR_MODE
        )


def test_profile_path_prints_codex_home(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_QUOTA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("CODEX_QUOTA_PROFILES_DIR", str(tmp_path / "profiles"))

    add = runner.invoke(app, ["profile", "add", "personal"])
    result = runner.invoke(app, ["profile", "path", "personal"])

    assert add.exit_code == 0
    assert result.exit_code == 0
    assert result.stdout.strip() == str((tmp_path / "profiles" / "personal").resolve())


def test_profile_remove_without_confirmation_keeps_profile(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("CODEX_QUOTA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("CODEX_QUOTA_PROFILES_DIR", str(tmp_path / "profiles"))

    add = runner.invoke(app, ["profile", "add", "personal"])
    result = runner.invoke(app, ["profile", "remove", "personal"], input="n\n")

    assert add.exit_code == 0
    assert result.exit_code == 1
    assert (tmp_path / "profiles" / "personal").is_dir()


def test_profile_remove_yes_deletes_profile(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_QUOTA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("CODEX_QUOTA_PROFILES_DIR", str(tmp_path / "profiles"))

    add = runner.invoke(app, ["profile", "add", "personal"])
    result = runner.invoke(app, ["profile", "remove", "personal", "--yes"])

    assert add.exit_code == 0
    assert result.exit_code == 0
    assert not (tmp_path / "profiles" / "personal").exists()


def test_profile_remove_warns_when_auth_json_exists(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("CODEX_QUOTA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("CODEX_QUOTA_PROFILES_DIR", str(tmp_path / "profiles"))

    add = runner.invoke(app, ["profile", "add", "personal"])
    auth_file = tmp_path / "profiles" / "personal" / "auth.json"
    auth_file.write_text("{}", encoding="utf-8")

    result = runner.invoke(app, ["profile", "remove", "personal", "--yes"])

    assert add.exit_code == 0
    assert result.exit_code == 0
    assert "auth.json exists" in result.stdout
    assert not (tmp_path / "profiles" / "personal").exists()


def test_profile_add_login_passes_device_auth(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_QUOTA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("CODEX_QUOTA_PROFILES_DIR", str(tmp_path / "profiles"))
    calls: list[tuple[str, str, bool]] = []

    def fake_login(profile, codex_bin: str, *, device_auth: bool = False) -> int:
        calls.append((profile.name, codex_bin, device_auth))
        return 0

    monkeypatch.setattr("codex_quota.cli.codex_login", fake_login)

    result = runner.invoke(
        app, ["profile", "add", "personal", "--login", "--device-auth"]
    )

    assert result.exit_code == 0
    assert calls == [("personal", "codex", True)]


def test_profile_add_rejects_device_auth_without_login(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("CODEX_QUOTA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("CODEX_QUOTA_PROFILES_DIR", str(tmp_path / "profiles"))

    result = runner.invoke(app, ["profile", "add", "personal", "--device-auth"])

    assert result.exit_code == 2
    assert "--device-auth requires --login" in result.stdout


def test_login_passes_device_auth_and_create(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_QUOTA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("CODEX_QUOTA_PROFILES_DIR", str(tmp_path / "profiles"))
    calls: list[tuple[str, str, bool]] = []

    def fake_login(profile, codex_bin: str, *, device_auth: bool = False) -> int:
        calls.append((profile.name, codex_bin, device_auth))
        return 0

    monkeypatch.setattr("codex_quota.cli.codex_login", fake_login)

    result = runner.invoke(app, ["login", "personal", "--create", "--device-auth"])

    assert result.exit_code == 0
    assert calls == [("personal", "codex", True)]
    assert (tmp_path / "profiles" / "personal").is_dir()


def test_status_json_shape_with_unknown_profile(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CODEX_QUOTA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("CODEX_QUOTA_PROFILES_DIR", str(tmp_path / "profiles"))

    result = runner.invoke(app, ["status", "missing", "--json"])

    assert result.exit_code == 2
    assert "Unknown profile" in result.stdout


def test_status_json_omits_sensitive_fields_by_default(
    monkeypatch, tmp_path: Path
) -> None:
    profile = Profile(name="personal", codex_home=tmp_path / "profiles" / "personal")
    statuses = [
        ProfileStatus(
            profile=profile,
            rate_limits=RateLimits(
                primary=WindowLimit(
                    used_percent=41,
                    window_duration_mins=300,
                    resets_at=123,
                    raw={"usedPercent": 41},
                ),
                secondary=WindowLimit(
                    used_percent=18,
                    window_duration_mins=10080,
                    resets_at=456,
                    raw={"usedPercent": 18},
                ),
                plan_type="pro",
                rate_limit_reached_type=None,
                credits={"total": 123},
                raw={"planType": "pro", "credits": {"total": 123}},
            ),
            auth_ok=True,
            codex_ok=True,
        )
    ]

    monkeypatch.setattr(
        "codex_quota.cli.collect_statuses", lambda *_args, **_kwargs: statuses
    )
    monkeypatch.setattr("codex_quota.cli._config", object)

    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == [
        {
            "profile": "personal",
            "status": None,
            "auth_ok": True,
            "codex_ok": True,
            "ok": True,
            "error": None,
            "rate_limits": {
                "blocked": False,
                "rate_limit_reached_type": None,
                "primary": {
                    "used_percent": 41,
                    "remaining_percent": 59,
                    "window_duration_mins": 300,
                    "resets_at": 123,
                },
                "secondary": {
                    "used_percent": 18,
                    "remaining_percent": 82,
                    "window_duration_mins": 10080,
                    "resets_at": 456,
                },
            },
        }
    ]


def test_status_json_can_include_paths_and_raw_payload(
    monkeypatch, tmp_path: Path
) -> None:
    profile = Profile(name="personal", codex_home=tmp_path / "profiles" / "personal")
    raw_limits = {"planType": "pro", "credits": {"total": 123}}
    statuses = [
        ProfileStatus(
            profile=profile,
            rate_limits=RateLimits(
                primary=None,
                secondary=None,
                plan_type="pro",
                rate_limit_reached_type="primary",
                credits={"total": 123},
                raw=raw_limits,
            ),
            auth_ok=True,
            codex_ok=True,
        )
    ]

    monkeypatch.setattr(
        "codex_quota.cli.collect_statuses", lambda *_args, **_kwargs: statuses
    )
    monkeypatch.setattr("codex_quota.cli._config", object)

    result = runner.invoke(app, ["status", "--json", "--json-paths", "--json-raw"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload[0]["status"] is None
    assert payload[0]["path"] == str(profile.codex_home)
    assert payload[0]["rate_limits"]["plan_type"] == "pro"
    assert payload[0]["rate_limits"]["credits"] == {"total": 123}
    assert payload[0]["rate_limits"]["raw"] == raw_limits


def test_status_json_includes_status_and_preserves_raw_error(
    monkeypatch, tmp_path: Path
) -> None:
    profile = Profile(name="personal", codex_home=tmp_path / "profiles" / "personal")
    raw_error = '{"code":401,"message":"401 Unauthorized"}'
    statuses = [
        ProfileStatus(
            profile=profile,
            rate_limits=None,
            auth_ok=False,
            codex_ok=True,
            error=raw_error,
            status="AUTH_REQUIRED",
        )
    ]

    monkeypatch.setattr(
        "codex_quota.cli.collect_statuses", lambda *_args, **_kwargs: statuses
    )
    monkeypatch.setattr("codex_quota.cli._config", object)

    result = runner.invoke(app, ["status", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == [
        {
            "profile": "personal",
            "status": "AUTH_REQUIRED",
            "auth_ok": False,
            "codex_ok": True,
            "ok": False,
            "error": raw_error,
            "rate_limits": None,
        }
    ]


def test_status_human_output_shows_auth_required(monkeypatch, tmp_path: Path) -> None:
    profile = Profile(name="personal", codex_home=tmp_path / "profiles" / "personal")
    statuses = [
        ProfileStatus(
            profile=profile,
            rate_limits=None,
            auth_ok=False,
            codex_ok=True,
            error='{"code":401,"message":"token_invalidated"}',
            status="AUTH_REQUIRED",
        )
    ]

    monkeypatch.setattr(
        "codex_quota.cli.collect_statuses", lambda *_args, **_kwargs: statuses
    )
    monkeypatch.setattr("codex_quota.cli._config", object)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "AUTH_REQUIRE" in result.stdout
    assert "D" in result.stdout
    assert "token_invalidated" not in result.stdout


def test_wake_forces_auth_refresh(monkeypatch, tmp_path: Path) -> None:
    profile = Profile(name="personal", codex_home=tmp_path / "profiles" / "personal")
    statuses = [
        ProfileStatus(
            profile=profile,
            rate_limits=RateLimits(
                primary=None,
                secondary=None,
                plan_type="pro",
                rate_limit_reached_type=None,
                credits={},
                raw={},
            ),
            auth_ok=True,
            codex_ok=True,
        )
    ]
    calls: list[tuple[str | None, bool]] = []

    def fake_collect_statuses(
        _config,
        profile_name: str | None = None,
        *,
        force_auth_refresh: bool = False,
    ) -> list[ProfileStatus]:
        calls.append((profile_name, force_auth_refresh))
        return statuses

    monkeypatch.setattr("codex_quota.cli.collect_statuses", fake_collect_statuses)
    monkeypatch.setattr("codex_quota.cli._config", object)

    result = runner.invoke(app, ["wake", "personal"])

    assert result.exit_code == 0
    assert calls == [("personal", True)]
