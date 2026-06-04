from __future__ import annotations

import json
import subprocess
import time
from typing import Any

from . import __version__
from .codex import codex_env, find_codex
from .errors import AppServerError
from .filesystem import ensure_private_dir
from .models import Profile, RateLimits, WindowLimit


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
    rate_limits = payload.get("rateLimits") or payload.get("result", {}).get("rateLimits")
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

    def read_rate_limits(self) -> RateLimits:
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
                request_id = 1
                send(
                    {
                        "jsonrpc": "2.0",
                        "id": request_id,
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
                        raise AppServerError(json.dumps(msg["error"]))

                    if msg.get("id") == 1 and not initialized:
                        initialized = True
                        send({"jsonrpc": "2.0", "method": "initialized", "params": {}})
                        request_id = 2
                        send(
                            {
                                "jsonrpc": "2.0",
                                "id": request_id,
                                "method": "account/rateLimits/read",
                                "params": {},
                            }
                        )
                        continue

                    if msg.get("id") == request_id:
                        result = msg.get("result")
                        if not isinstance(result, dict):
                            raise AppServerError(f"Malformed JSON-RPC response: {msg}")
                        return decode_rate_limits(result)

                raise AppServerError("Timed out waiting for Codex app-server rate limits")
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()


def read_rate_limits(
    profile: Profile,
    codex_bin: str = "codex",
    timeout: float = 30.0,
) -> RateLimits:
    return AppServerClient(profile, codex_bin=codex_bin, timeout=timeout).read_rate_limits()
