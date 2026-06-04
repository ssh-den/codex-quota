from __future__ import annotations

from collections.abc import Callable, Sequence

from .app_server import read_rate_limits
from .codex import login_status
from .errors import CodexNotFoundError
from .models import AppConfig, Profile, ProfileStatus, RateLimits
from .profiles import discover_profiles, get_profile

RateLimitReader = Callable[[Profile, str], RateLimits]
LoginChecker = Callable[[Profile, str], bool]


def selected_profiles(config: AppConfig, profile_name: str | None = None) -> list[Profile]:
    if profile_name:
        return [get_profile(config, profile_name)]
    return discover_profiles(config)


def collect_statuses(
    config: AppConfig,
    profile_name: str | None = None,
    *,
    profiles: Sequence[Profile] | None = None,
    rate_limit_reader: RateLimitReader = read_rate_limits,
    login_checker: LoginChecker = login_status,
) -> list[ProfileStatus]:
    selected = list(profiles) if profiles is not None else selected_profiles(config, profile_name)

    statuses: list[ProfileStatus] = []
    for profile in selected:
        auth_ok = False
        codex_ok = True
        try:
            auth_ok = login_checker(profile, config.codex_bin)
            limits = rate_limit_reader(profile, config.codex_bin) if auth_ok else None
            error = None if auth_ok else "auth_required"
            statuses.append(ProfileStatus(profile, limits, auth_ok, codex_ok, error))
        except CodexNotFoundError as exc:
            statuses.append(ProfileStatus(profile, None, auth_ok, False, str(exc)))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # Convert per-profile failures into structured status.
            statuses.append(ProfileStatus(profile, None, auth_ok, codex_ok, str(exc)))
    return statuses


def check_failed(statuses: Sequence[ProfileStatus]) -> bool:
    if not statuses:
        return True
    return any(not item.ok for item in statuses)
