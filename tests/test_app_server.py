from __future__ import annotations

import json

import pytest

from codex_quota.app_server import AppServerClient, decode_account, decode_rate_limits
from codex_quota.errors import AppServerError
from codex_quota.models import Profile


def test_decode_rate_limits_preserves_raw_and_remaining() -> None:
    payload = {
        "rateLimits": {
            "primary": {"usedPercent": 41, "windowDurationMins": 300, "resetsAt": 123},
            "secondary": {
                "usedPercent": 100,
                "windowDurationMins": 10080,
                "resetsAt": 456,
            },
            "planType": "pro",
            "rateLimitReachedType": None,
            "credits": {"foo": "bar"},
        }
    }

    decoded = decode_rate_limits(payload)

    assert decoded.raw is payload["rateLimits"]
    assert decoded.primary is not None
    assert decoded.primary.raw is payload["rateLimits"]["primary"]
    assert decoded.primary.remaining_percent == 59
    assert decoded.secondary is not None
    assert decoded.secondary.remaining_percent == 0
    assert decoded.is_blocked is False


def test_decode_rate_limits_treats_reached_type_as_authoritative_block() -> None:
    payload = {
        "rateLimits": {
            "primary": {"usedPercent": 99, "windowDurationMins": 300, "resetsAt": None},
            "secondary": {
                "usedPercent": 50,
                "windowDurationMins": 10080,
                "resetsAt": None,
            },
            "planType": "pro",
            "rateLimitReachedType": "primary",
        }
    }

    decoded = decode_rate_limits(payload)

    assert decoded.is_blocked is True
    assert decoded.rate_limit_reached_type == "primary"
    assert decoded.primary is not None
    assert decoded.primary.remaining_percent == 1


def test_decode_rate_limits_does_not_infer_block_from_100_percent() -> None:
    payload = {
        "rateLimits": {
            "primary": {
                "usedPercent": 100,
                "windowDurationMins": 300,
                "resetsAt": None,
            },
            "secondary": {
                "usedPercent": 100,
                "windowDurationMins": 10080,
                "resetsAt": None,
            },
            "planType": "pro",
            "rateLimitReachedType": None,
        }
    }

    decoded = decode_rate_limits(payload)

    assert decoded.is_blocked is False
    assert decoded.primary is not None
    assert decoded.primary.remaining_percent == 0


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"rateLimits": None},
        {"rateLimits": []},
        {"result": {}},
        {"result": {"rateLimits": []}},
    ],
)
def test_decode_rate_limits_rejects_malformed_payload(
    payload: dict[str, object],
) -> None:
    with pytest.raises(AppServerError):
        decode_rate_limits(payload)


def test_decode_rate_limits_handles_missing_windows() -> None:
    payload: dict[str, object] = {
        "rateLimits": {
            "planType": "pro",
            "rateLimitReachedType": None,
            "credits": [],
        }
    }

    decoded = decode_rate_limits(payload)

    assert decoded.primary is None
    assert decoded.secondary is None
    assert not decoded.credits
    assert decoded.is_blocked is False


def test_decode_account_surfaces_requires_openai_auth() -> None:
    decoded = decode_account({"account": None, "requiresOpenaiAuth": True})

    assert decoded.account is None
    assert decoded.requires_openai_auth is True


class _FakeStdout:
    def __init__(self, lines: list[str]) -> None:
        self._lines = iter(lines)

    def readline(self) -> str:
        return next(self._lines, "")


class _FakeStdin:
    def __init__(self) -> None:
        self.writes: list[str] = []

    def write(self, text: str) -> None:
        self.writes.append(text)

    def flush(self) -> None:
        return None


class _FakeStderr:
    def read(self) -> str:
        return ""


class _FakeProc:
    def __init__(self, lines: list[str]) -> None:
        self.stdin = _FakeStdin()
        self.stdout = _FakeStdout(lines)
        self.stderr = _FakeStderr()

    def __enter__(self) -> _FakeProc:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def poll(self) -> int | None:
        return None

    def terminate(self) -> None:
        return None

    def wait(self, timeout: float | None = None) -> None:
        _ = timeout

    def kill(self) -> None:
        return None


def test_read_account_uses_refresh_token_request_path(monkeypatch, tmp_path) -> None:
    profile = Profile(name="personal", codex_home=tmp_path / "personal")
    lines = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n",
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "account": {"type": "chatgpt", "email": "user@example.com"},
                    "requiresOpenaiAuth": True,
                },
            }
        )
        + "\n",
    ]
    proc = _FakeProc(lines)

    monkeypatch.setattr(
        "codex_quota.app_server.find_codex", lambda _bin: "/usr/bin/codex"
    )
    monkeypatch.setattr(
        "codex_quota.app_server.ensure_private_dir", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        "codex_quota.app_server.subprocess.Popen", lambda *_args, **_kwargs: proc
    )

    account = AppServerClient(profile).read_account(refresh_token=True)

    writes = [json.loads(line) for line in proc.stdin.writes]
    assert writes[1] == {"jsonrpc": "2.0", "method": "initialized", "params": {}}
    assert writes[2]["method"] == "account/read"
    assert writes[2]["params"] == {"refreshToken": True}
    assert account.account == {"type": "chatgpt", "email": "user@example.com"}
    assert account.requires_openai_auth is True


def test_request_preserves_raw_json_rpc_errors(monkeypatch, tmp_path) -> None:
    profile = Profile(name="personal", codex_home=tmp_path / "personal")
    raw_error = {"code": 401, "message": "401 Unauthorized"}
    raw_line = json.dumps({"jsonrpc": "2.0", "id": 2, "error": raw_error}) + "\n"
    proc = _FakeProc(
        [
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n",
            raw_line,
        ]
    )

    monkeypatch.setattr(
        "codex_quota.app_server.find_codex", lambda _bin: "/usr/bin/codex"
    )
    monkeypatch.setattr(
        "codex_quota.app_server.ensure_private_dir", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        "codex_quota.app_server.subprocess.Popen", lambda *_args, **_kwargs: proc
    )

    with pytest.raises(AppServerError) as exc:
        AppServerClient(profile).read_account(refresh_token=True)

    assert str(exc.value) == raw_line
