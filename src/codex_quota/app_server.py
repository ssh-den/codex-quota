from __future__ import annotations

import json
import subprocess
import time
from typing import Any

from . import __version__
from .codex import codex_env, find_codex
from .errors import AppServerError
from .filesystem import ensure_private_dir
from .models import AccountInfo, Profile, RateLimits, WindowLimit


def _window(data: object) -> WindowLimit | None:
    if not isinstance(data, dict):
        return None
    return WindowLimit(
        used_percent=int(data.get("usedPercent", 0)),
        window_duration_mins=int(data.get("windowDurationMins", 0)),
        resets_at=data.get("resetsAt"),
        raw=data,
    )


def decode_rate_limits(payload: dict[str, Any]) -> RateLimits:
    rate_limits = payload.get("rateLimits") or payload.get("result", {}).get(
        "rateLimits"
    )
    if not isinstance(rate_limits, dict):
        raise AppServerError(f"Unexpected rate limit response: {payload}")

    credits_data = rate_limits.get("credits")
    return RateLimits(
        primary=_window(rate_limits.get("primary")),
        secondary=_window(rate_limits.get("secondary")),
        plan_type=rate_limits.get("planType"),
        rate_limit_reached_type=rate_limits.get("rateLimitReachedType"),
        credits=credits_data if isinstance(credits_data, dict) else {},
        raw=rate_limits,
    )


def decode_account(payload: dict[str, Any]) -> AccountInfo:
    account = payload.get("account")
    if account is not None and not isinstance(account, dict):
        raise AppServerError(f"Unexpected account response: {payload}")
    return AccountInfo(
        account=account,
        requires_openai_auth=bool(payload.get("requiresOpenaiAuth")),
        raw=payload,
    )


class AppServerClient:
    def __init__(
        self,
        profile: Profile,
        *,
        codex_bin: str = "codex",
        timeout: float = 30.0,
    ) -> None:
        self.profile = profile
        self.codex_bin = codex_bin
        self.timeout = timeout

    def request(  # pylint: disable=too-many-locals
        self,
        method: str,
        params: dict[str, Any],
        *,
        timeout_message: str,
    ) -> dict[str, Any]:
        binary = find_codex(self.codex_bin)
        ensure_private_dir(self.profile.codex_home, parents=True, exist_ok=True)
        with subprocess.Popen(
            [binary, "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=codex_env(self.profile),
        ) as proc:
            stdin = proc.stdin
            stdout = proc.stdout
            stderr = proc.stderr
            if stdin is None or stdout is None or stderr is None:
                raise AppServerError("codex app-server stdio pipes were not available")

            def send(obj: dict[str, Any]) -> None:
                stdin.write(json.dumps(obj) + "\n")
                stdin.flush()

            try:
                initialize_id = 1
                request_id = 2
                send(
                    {
                        "jsonrpc": "2.0",
                        "id": initialize_id,
                        "method": "initialize",
                        "params": {
                            "clientInfo": {
                                "name": "codex-quota",
                                "version": __version__,
                            },
                            "capabilities": {"experimentalApi": True},
                        },
                    }
                )

                deadline = time.monotonic() + self.timeout
                initialized = False

                while time.monotonic() < deadline:
                    line = stdout.readline()

                    if not line:
                        if proc.poll() is not None:
                            stderr_output = stderr.read()
                            raise AppServerError(
                                stderr_output.strip() or "codex app-server exited early"
                            )
                        time.sleep(0.02)
                        continue

                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if not isinstance(msg, dict):
                        continue

                    if msg.get("error"):
                        raise AppServerError(line)

                    if msg.get("id") == initialize_id and not initialized:
                        initialized = True
                        send({"jsonrpc": "2.0", "method": "initialized", "params": {}})
                        send(
                            {
                                "jsonrpc": "2.0",
                                "id": request_id,
                                "method": method,
                                "params": params,
                            }
                        )
                        continue

                    if msg.get("id") == request_id:
                        result = msg.get("result")
                        if not isinstance(result, dict):
                            raise AppServerError(f"Malformed JSON-RPC response: {msg}")
                        return result

                raise AppServerError(timeout_message)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()

    def read_rate_limits(self) -> RateLimits:
        result = self.request(
            "account/rateLimits/read",
            {},
            timeout_message="Timed out waiting for Codex app-server rate limits",
        )
        return decode_rate_limits(result)

    def read_account(self, *, refresh_token: bool = False) -> AccountInfo:
        result = self.request(
            "account/read",
            {"refreshToken": refresh_token},
            timeout_message="Timed out waiting for Codex app-server account",
        )
        return decode_account(result)


def read_rate_limits(
    profile: Profile,
    codex_bin: str = "codex",
    timeout: float = 30.0,
) -> RateLimits:
    return AppServerClient(
        profile, codex_bin=codex_bin, timeout=timeout
    ).read_rate_limits()


def read_account(
    profile: Profile,
    codex_bin: str = "codex",
    timeout: float = 30.0,
    *,
    refresh_token: bool = False,
) -> AccountInfo:
    return AppServerClient(profile, codex_bin=codex_bin, timeout=timeout).read_account(
        refresh_token=refresh_token
    )
