from __future__ import annotations

from pathlib import Path

import pytest

from codex_quota.errors import CodexNotFoundError, ProfileNotFoundError
from codex_quota.models import AppConfig, Profile, RateLimits, WindowLimit
from codex_quota.profiles import add_profile
from codex_quota.service import check_failed, collect_statuses


def limits(blocked: bool = False) -> RateLimits:
    return RateLimits(
        primary=WindowLimit(
            used_percent=25,
            window_duration_mins=300,
            resets_at=None,
            raw={"usedPercent": 25},
        ),
        secondary=WindowLimit(
            used_percent=90,
            window_duration_mins=10080,
            resets_at=None,
            raw={"usedPercent": 90},
        ),
        plan_type="pro",
        rate_limit_reached_type="primary" if blocked else None,
        credits={},
        raw={"planType": "pro", "rateLimitReachedType": "primary" if blocked else None},
    )


def test_collect_statuses_continues_after_profile_error(tmp_path: Path) -> None:
    cfg = AppConfig(profiles_dir=tmp_path / "profiles")
    first = add_profile(cfg, "first")
    second = add_profile(cfg, "second")

    def login_checker(_profile: Profile, _codex_bin: str) -> bool:
        return True

    def reader(profile: Profile, _codex_bin: str) -> RateLimits:
        if profile.name == "first":
            raise RuntimeError("broken")
        return limits()

    statuses = collect_statuses(
        cfg,
        profiles=[first, second],
        login_checker=login_checker,
        rate_limit_reader=reader,
    )

    assert statuses[0].error == "broken"
    assert statuses[1].ok is True


def test_collect_statuses_reports_auth_required(tmp_path: Path) -> None:
    cfg = AppConfig(profiles_dir=tmp_path / "profiles")
    profile = add_profile(cfg, "personal")

    statuses = collect_statuses(
        cfg,
        profiles=[profile],
        login_checker=lambda _profile, _bin: False,
        rate_limit_reader=lambda _profile, _bin: limits(),
    )

    assert statuses[0].auth_ok is False
    assert statuses[0].error == "auth_required"
    assert check_failed(statuses) is True


def test_check_failed_on_blocked_quota(tmp_path: Path) -> None:
    cfg = AppConfig(profiles_dir=tmp_path / "profiles")
    profile = add_profile(cfg, "personal")
    statuses = collect_statuses(
        cfg,
        profiles=[profile],
        login_checker=lambda _profile, _bin: True,
        rate_limit_reader=lambda _profile, _bin: limits(blocked=True),
    )

    assert check_failed(statuses) is True


def test_unknown_profile_raises(tmp_path: Path) -> None:
    with pytest.raises(ProfileNotFoundError):
        collect_statuses(AppConfig(profiles_dir=tmp_path / "profiles"), "missing")


def test_codex_missing_is_per_profile_error(tmp_path: Path) -> None:
    cfg = AppConfig(profiles_dir=tmp_path / "profiles")
    profile = add_profile(cfg, "personal")
    statuses = collect_statuses(
        cfg,
        profiles=[profile],
        login_checker=lambda _profile, _bin: (_ for _ in ()).throw(CodexNotFoundError("missing")),
        rate_limit_reader=lambda _profile, _bin: limits(),
    )

    assert statuses[0].codex_ok is False
    assert statuses[0].error == "missing"
