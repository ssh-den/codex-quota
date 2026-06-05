from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from codex_quota.errors import AppServerError, CodexNotFoundError, ProfileNotFoundError
from codex_quota.models import AccountInfo, AppConfig, Profile, RateLimits, WindowLimit
from codex_quota.profiles import add_profile
from codex_quota.service import (
    AUTH_REQUIRED,
    check_failed,
    collect_statuses,
    refresh_auth_if_needed,
)


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
        account_reader=lambda *_args, **_kwargs: AccountInfo(
            account={"type": "chatgpt"},
            requires_openai_auth=True,
            raw={},
        ),
        rate_limit_reader=reader,
        config_persister=lambda current, _name, _ts: current,
        now=datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
    )

    assert statuses[0].error == "broken"
    assert statuses[1].ok is True


def test_login_status_unauthenticated_reports_auth_required(tmp_path: Path) -> None:
    cfg = AppConfig(profiles_dir=tmp_path / "profiles")
    profile = add_profile(cfg, "personal")

    statuses = collect_statuses(
        cfg,
        profiles=[profile],
        login_checker=lambda _profile, _bin: False,
    )

    assert statuses[0].auth_ok is False
    assert statuses[0].status == AUTH_REQUIRED
    assert statuses[0].error is None
    assert check_failed(statuses) is True


def test_refresh_skipped_when_last_refresh_under_four_hours(tmp_path: Path) -> None:
    cfg = AppConfig(
        profiles_dir=tmp_path / "profiles",
        extra={"auth_refresh": {"personal": "2026-06-05T08:30:00Z"}},
    )
    profile = add_profile(cfg, "personal")
    called = False

    def reader(*_args, **_kwargs) -> AccountInfo:
        nonlocal called
        called = True
        return AccountInfo(
            account={"type": "chatgpt"}, requires_openai_auth=True, raw={}
        )

    updated, status, error = refresh_auth_if_needed(
        cfg,
        profile,
        account_reader=reader,
        config_persister=lambda current, _name, _ts: current,
        now=datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
    )

    assert called is False
    assert updated is cfg
    assert status is None
    assert error is None


def test_refresh_runs_when_last_refresh_is_four_hours_old(tmp_path: Path) -> None:
    cfg = AppConfig(
        profiles_dir=tmp_path / "profiles",
        extra={"auth_refresh": {"personal": "2026-06-05T08:00:00Z"}},
    )
    profile = add_profile(cfg, "personal")
    calls: list[bool] = []

    def reader(*_args, **_kwargs) -> AccountInfo:
        calls.append(True)
        return AccountInfo(
            account={"type": "chatgpt"}, requires_openai_auth=True, raw={}
        )

    refresh_auth_if_needed(
        cfg,
        profile,
        account_reader=reader,
        config_persister=lambda current, _name, _ts: current,
        now=datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
    )

    assert calls == [True]


def test_successful_refresh_updates_timestamp(tmp_path: Path) -> None:
    cfg = AppConfig(profiles_dir=tmp_path / "profiles")
    profile = add_profile(cfg, "personal")
    saved: list[tuple[AppConfig, str, datetime]] = []

    def persister(current: AppConfig, name: str, refreshed_at: datetime) -> AppConfig:
        saved.append((current, name, refreshed_at))
        return AppConfig(
            profiles_dir=current.profiles_dir,
            codex_bin=current.codex_bin,
            default_model=current.default_model,
            reasoning_effort=current.reasoning_effort,
            refresh_seconds=current.refresh_seconds,
            extra={"auth_refresh": {name: "2026-06-05T12:00:00Z"}},
        )

    updated, status, error = refresh_auth_if_needed(
        cfg,
        profile,
        account_reader=lambda *_args, **_kwargs: AccountInfo(
            account={"type": "chatgpt"},
            requires_openai_auth=True,
            raw={},
        ),
        config_persister=persister,
        now=datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
    )

    assert status is None
    assert error is None
    assert saved[0][1] == "personal"
    assert updated.extra["auth_refresh"]["personal"] == "2026-06-05T12:00:00Z"


def test_failed_refresh_does_not_update_timestamp(tmp_path: Path) -> None:
    cfg = AppConfig(profiles_dir=tmp_path / "profiles")
    profile = add_profile(cfg, "personal")
    calls: list[tuple[str, datetime]] = []

    def persister(current: AppConfig, name: str, ts: datetime) -> AppConfig:
        calls.append((name, ts))
        return current

    updated, status, error = refresh_auth_if_needed(
        cfg,
        profile,
        account_reader=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AppServerError("temporary")
        ),
        config_persister=persister,
        now=datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
    )

    assert updated is cfg
    assert status is None
    assert error == "temporary"
    assert not calls


def test_auth_related_refresh_failure_becomes_auth_required(tmp_path: Path) -> None:
    cfg = AppConfig(profiles_dir=tmp_path / "profiles")
    profile = add_profile(cfg, "personal")

    updated, status, error = refresh_auth_if_needed(
        cfg,
        profile,
        account_reader=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AppServerError('{"code":401,"message":"token_invalidated"}')
        ),
        config_persister=lambda current, _name, _ts: current,
        now=datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
    )

    assert updated is cfg
    assert status == AUTH_REQUIRED
    assert error == '{"code":401,"message":"token_invalidated"}'


def test_non_auth_refresh_failure_still_allows_rate_limit_collection(
    tmp_path: Path,
) -> None:
    cfg = AppConfig(profiles_dir=tmp_path / "profiles")
    profile = add_profile(cfg, "personal")

    statuses = collect_statuses(
        cfg,
        profiles=[profile],
        login_checker=lambda _profile, _bin: True,
        account_reader=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AppServerError('{"code":500,"message":"temporary unavailable"}')
        ),
        rate_limit_reader=lambda _profile, _bin: limits(),
        config_persister=lambda current, _name, _ts: current,
        now=datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
    )

    assert statuses[0].ok is True
    assert statuses[0].status is None
    assert statuses[0].error is None


def test_account_requires_openai_auth_becomes_auth_required(tmp_path: Path) -> None:
    cfg = AppConfig(profiles_dir=tmp_path / "profiles")
    profile = add_profile(cfg, "personal")

    statuses = collect_statuses(
        cfg,
        profiles=[profile],
        login_checker=lambda _profile, _bin: True,
        account_reader=lambda *_args, **_kwargs: AccountInfo(
            account=None,
            requires_openai_auth=True,
            raw={"account": None, "requiresOpenaiAuth": True},
        ),
        rate_limit_reader=lambda _profile, _bin: limits(),
        config_persister=lambda current, _name, _ts: current,
        now=datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
    )

    assert statuses[0].status == AUTH_REQUIRED
    assert statuses[0].auth_ok is False
    assert statuses[0].error == "account requires OpenAI authentication"


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
        login_checker=lambda _profile, _bin: (_ for _ in ()).throw(
            CodexNotFoundError("missing")
        ),
        rate_limit_reader=lambda _profile, _bin: limits(),
    )

    assert statuses[0].codex_ok is False
    assert statuses[0].error == "missing"


def test_status_collection_continues_when_one_profile_hits_auth_required(
    tmp_path: Path,
) -> None:
    cfg = AppConfig(profiles_dir=tmp_path / "profiles")
    first = add_profile(cfg, "first")
    second = add_profile(cfg, "second")

    def account_reader(
        profile: Profile, _bin: str, *, refresh_token: bool = False
    ) -> AccountInfo:
        assert refresh_token is True
        if profile.name == "first":
            raise AppServerError('{"code":401,"message":"401 Unauthorized"}')
        return AccountInfo(
            account={"type": "chatgpt"}, requires_openai_auth=True, raw={}
        )

    statuses = collect_statuses(
        cfg,
        profiles=[first, second],
        login_checker=lambda _profile, _bin: True,
        account_reader=account_reader,
        rate_limit_reader=lambda _profile, _bin: limits(),
        config_persister=lambda current, _name, _ts: current,
        now=datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
    )

    assert statuses[0].status == AUTH_REQUIRED
    assert statuses[1].ok is True
