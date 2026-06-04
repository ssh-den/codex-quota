from __future__ import annotations

from codex_quota.render import fmt_reset


def test_fmt_reset_unknown() -> None:
    assert fmt_reset(None) == "unknown"
