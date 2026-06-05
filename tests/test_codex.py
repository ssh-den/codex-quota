from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

from codex_quota.codex import login, simple_exec
from codex_quota.filesystem import PRIVATE_DIR_MODE
from codex_quota.models import AppConfig, Profile


def test_login_uses_device_auth_when_requested(monkeypatch, tmp_path: Path) -> None:
    profile = Profile(name="personal", codex_home=tmp_path / "personal")
    calls: list[tuple[list[str], dict[str, str]]] = []

    monkeypatch.setattr(
        "codex_quota.codex.find_codex", lambda _codex_bin: "/usr/bin/codex"
    )

    def fake_call(args: list[str], *, env: dict[str, str]) -> int:
        calls.append((args, env))
        return 0

    monkeypatch.setattr("codex_quota.codex.subprocess.call", fake_call)

    result = login(profile, device_auth=True)

    assert result == 0
    assert profile.codex_home.is_dir()
    if os.name == "posix":
        assert stat.S_IMODE(profile.codex_home.stat().st_mode) == PRIVATE_DIR_MODE
    assert calls[0][0] == ["/usr/bin/codex", "login", "--device-auth"]
    assert calls[0][1]["CODEX_HOME"] == str(profile.codex_home)


def test_login_omits_device_auth_by_default(monkeypatch, tmp_path: Path) -> None:
    profile = Profile(name="personal", codex_home=tmp_path / "personal")
    calls: list[list[str]] = []

    monkeypatch.setattr(
        "codex_quota.codex.find_codex", lambda _codex_bin: "/usr/bin/codex"
    )

    def fake_call(args: list[str], *, env: dict[str, str]) -> int:
        _ = env
        calls.append(args)
        return 0

    monkeypatch.setattr("codex_quota.codex.subprocess.call", fake_call)

    result = login(profile)

    assert result == 0
    assert calls == [["/usr/bin/codex", "login"]]


def test_simple_exec_respects_user_config_and_rules(
    monkeypatch, tmp_path: Path
) -> None:
    profile = Profile(name="personal", codex_home=tmp_path / "personal")
    config = AppConfig(profiles_dir=tmp_path / "profiles")
    captured: dict[str, object] = {}

    def fake_run_codex(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(["codex"], 0, stdout="", stderr="")

    monkeypatch.setattr("codex_quota.codex.run_codex", fake_run_codex)

    result = simple_exec(profile, "Reply with exactly: ok", config)

    assert result.returncode == 0
    assert captured["args"] == [
        "exec",
        "--skip-git-repo-check",
        "--ephemeral",
        "-m",
        "gpt-5.4-mini",
        "-c",
        'model_reasoning_effort="low"',
        "--json",
        "Reply with exactly: ok",
    ]
