from __future__ import annotations

import pytest

from codex_quota.app_server import decode_rate_limits
from codex_quota.errors import AppServerError


def test_decode_rate_limits_preserves_raw_and_remaining() -> None:
    payload = {
        "rateLimits": {
            "primary": {"usedPercent": 41, "windowDurationMins": 300, "resetsAt": 123},
            "secondary": {"usedPercent": 100, "windowDurationMins": 10080, "resetsAt": 456},
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
            "secondary": {"usedPercent": 50, "windowDurationMins": 10080, "resetsAt": None},
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
            "primary": {"usedPercent": 100, "windowDurationMins": 300, "resetsAt": None},
            "secondary": {"usedPercent": 100, "windowDurationMins": 10080, "resetsAt": None},
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
def test_decode_rate_limits_rejects_malformed_payload(payload: dict[str, object]) -> None:
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
