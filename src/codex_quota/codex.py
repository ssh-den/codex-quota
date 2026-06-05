from __future__ import annotations

import os
import shutil
import subprocess

from .errors import CodexCommandError, CodexNotFoundError
from .filesystem import ensure_private_dir
from .models import AppConfig, Profile


def find_codex(codex_bin: str = "codex") -> str:
    found = shutil.which(codex_bin)
    if not found:
        raise CodexNotFoundError(
            "Codex CLI was not found. Install the official Codex CLI and ensure "
            "it is available on PATH, or set codex_bin in config.json."
        )
    return found


def codex_env(profile: Profile) -> dict[str, str]:
    return {**os.environ, "CODEX_HOME": str(profile.codex_home)}


def run_codex(
    args: list[str],
    *,
    profile: Profile | None = None,
    codex_bin: str = "codex",
    timeout: float = 60.0,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    binary = find_codex(codex_bin)
    env = codex_env(profile) if profile else os.environ.copy()
    try:
        proc = subprocess.run(
            [binary, *args],
            text=True,
            capture_output=True,
            env=env,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CodexCommandError(f"codex {' '.join(args)} timed out") from exc
    if check and proc.returncode != 0:
        raise CodexCommandError(
            proc.stderr.strip() or proc.stdout.strip() or "codex command failed"
        )
    return proc


def codex_version(codex_bin: str = "codex") -> str:
    proc = run_codex(["--version"], codex_bin=codex_bin, timeout=10)
    if proc.returncode != 0:
        raise CodexCommandError(
            proc.stderr.strip() or "Failed to read Codex CLI version"
        )
    return proc.stdout.strip() or proc.stderr.strip() or "unknown"


def login_status(profile: Profile, codex_bin: str = "codex") -> bool:
    if not profile.auth_file.is_file():
        return False
    proc = run_codex(
        ["login", "status"], profile=profile, codex_bin=codex_bin, timeout=20
    )
    output = f"{proc.stdout}\n{proc.stderr}".lower()
    return proc.returncode == 0 and ("logged in" in output or "authenticated" in output)


def login(
    profile: Profile,
    codex_bin: str = "codex",
    *,
    device_auth: bool = False,
) -> int:
    binary = find_codex(codex_bin)
    ensure_private_dir(profile.codex_home, parents=True, exist_ok=True)
    args = [binary, "login"]
    if device_auth:
        args.append("--device-auth")
    return subprocess.call(args, env=codex_env(profile))


def simple_exec(
    profile: Profile,
    prompt: str,
    config: AppConfig,
    *,
    json_output: bool = True,
    timeout: float = 180.0,
) -> subprocess.CompletedProcess[str]:
    args = [
        "exec",
        "--skip-git-repo-check",
        "--ephemeral",
        "-m",
        config.default_model,
        "-c",
        f'model_reasoning_effort="{config.reasoning_effort}"',
    ]
    if json_output:
        args.append("--json")
    args.append(prompt)
    return run_codex(args, profile=profile, codex_bin=config.codex_bin, timeout=timeout)
