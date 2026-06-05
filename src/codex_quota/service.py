from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from .app_server import read_account, read_rate_limits
from .codex import login_status
from .config import auth_refresh_due, persist_auth_refresh
from .errors import AppServerError, CodexNotFoundError
from .models import AccountInfo, AppConfig, Profile, ProfileStatus, RateLimits
from .profiles import discover_profiles, get_profile

RateLimitReader = Callable[[Profile, str], RateLimits]
LoginChecker = Callable[[Profile, str], bool]
AccountReader = Callable[..., AccountInfo]
ConfigPersister = Callable[[AppConfig, str, datetime], AppConfig]
AUTH_REQUIRED = "AUTH_REQUIRED"
AUTH_ERROR_MARKERS = (
    "token_invalidated",
    "401 unauthorized",
    "login required",
    "invalid refresh token",
    "authentication required",
    "account requires openai authentication",
)


def selected_profiles(
    config: AppConfig, profile_name: str | None = None
) -> list[Profile]:
    if profile_name:
        return [get_profile(config, profile_name)]
    return discover_profiles(config)


def is_auth_error_message(error: str) -> bool:
    normalized = error.casefold()
    return any(marker in normalized for marker in AUTH_ERROR_MARKERS)


def _persist_config(
    config: AppConfig, profile_name: str, refreshed_at: datetime
) -> AppConfig:
    return persist_auth_refresh(config, profile_name, refreshed_at)


def refresh_auth_if_needed(
    config: AppConfig,
    profile: Profile,
    *,
    account_reader: AccountReader = read_account,
    config_persister: ConfigPersister = _persist_config,
    now: datetime | None = None,
) -> tuple[AppConfig, str | None, str | None]:
    current_time = now or datetime.now(UTC)
    if not auth_refresh_due(config, profile.name, now=current_time):
        return config, None, None

    try:
        account = account_reader(profile, config.codex_bin, refresh_token=True)
    except AppServerError as exc:
        error = str(exc)
        if is_auth_error_message(error):
            return config, AUTH_REQUIRED, error
        return config, None, error

    if account.account is None and account.requires_openai_auth:
        return config, AUTH_REQUIRED, "account requires OpenAI authentication"

    updated_config = config_persister(config, profile.name, current_time)
    return updated_config, None, None


def collect_statuses(  # pylint: disable=too-many-arguments,too-many-locals
    config: AppConfig,
    profile_name: str | None = None,
    *,
    profiles: Sequence[Profile] | None = None,
    rate_limit_reader: RateLimitReader = read_rate_limits,
    login_checker: LoginChecker = login_status,
    account_reader: AccountReader = read_account,
    config_persister: ConfigPersister = _persist_config,
    now: datetime | None = None,
) -> list[ProfileStatus]:
    selected = (
        list(profiles)
        if profiles is not None
        else selected_profiles(config, profile_name)
    )

    statuses: list[ProfileStatus] = []
    current_config = config
    for profile in selected:
        auth_ok = False
        codex_ok = True
        try:
            auth_ok = login_checker(profile, config.codex_bin)
            if not auth_ok:
                statuses.append(
                    ProfileStatus(
                        profile=profile,
                        rate_limits=None,
                        auth_ok=False,
                        codex_ok=codex_ok,
                        error=None,
                        status=AUTH_REQUIRED,
                    )
                )
                continue

            current_config, status, refresh_error = refresh_auth_if_needed(
                current_config,
                profile,
                account_reader=account_reader,
                config_persister=config_persister,
                now=now,
            )
            if status == AUTH_REQUIRED:
                statuses.append(
                    ProfileStatus(
                        profile=profile,
                        rate_limits=None,
                        auth_ok=False,
                        codex_ok=codex_ok,
                        error=refresh_error,
                        status=AUTH_REQUIRED,
                    )
                )
                continue

            limits = rate_limit_reader(profile, config.codex_bin)
            statuses.append(
                ProfileStatus(
                    profile=profile,
                    rate_limits=limits,
                    auth_ok=True,
                    codex_ok=codex_ok,
                    error=None,
                    status=None,
                )
            )
        except CodexNotFoundError as exc:
            statuses.append(
                ProfileStatus(profile, None, auth_ok, False, str(exc), None)
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # Convert per-profile failures into structured status.
            error = str(exc)
            status = AUTH_REQUIRED if is_auth_error_message(error) else None
            statuses.append(
                ProfileStatus(
                    profile, None, auth_ok and status is None, codex_ok, error, status
                )
            )
    return statuses


def check_failed(statuses: Sequence[ProfileStatus]) -> bool:
    if not statuses:
        return True
    return any(not item.ok for item in statuses)
