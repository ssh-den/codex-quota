# Changelog

## 1.1.0 - 2026-06-05

### Added

- Opportunistic auth keepalive during `status`, `check`, and TUI refreshes using the official Codex App Server `account/read` call with `refreshToken=true`.
- Persistent per-profile `auth_refresh` timestamps in application config using UTC ISO-8601 `Z` timestamps.
- Additive `status` field in machine-readable status output for explicit classifications such as `AUTH_REQUIRED`.

### Changed

- Status collection now follows `login_status()`, best-effort auth refresh, and `account/rateLimits/read` without requiring a separate maintenance command.
- App Server access now uses a reusable JSON-RPC request path while preserving the existing initialize and initialized handshake.

### Fixed

- Auth failures such as invalidated or missing managed tokens are now classified as `AUTH_REQUIRED` without dumping backend JSON into human-readable tables.
- Non-auth refresh failures no longer block quota reads when `account/rateLimits/read` still succeeds.
- Future or malformed `auth_refresh` timestamps are treated as stale so keepalive refresh resumes immediately instead of being skipped indefinitely.
- Raw JSON-RPC error responses from `codex app-server --stdio` are now preserved exactly as returned for JSON and internal error handling.

## 1.0.0 - 2026-06-04

### Added

- `codex-quota login <profile> --device-auth` for device-code login on headless or remote machines.
- `codex-quota profile add <profile> --login --device-auth` to create and authenticate a profile in one step.
- TUI support for `login <profile> --device-auth`.

### Fixed

- `profile add --device-auth` without `--login` now exits with a clear user-facing error.
- POSIX profile/config directories are now created and tightened with `0700` permissions.
- `exec` now respects user Codex config and rules by default.
- Hardened profile discovery so symlinked directories cannot be treated as external `CODEX_HOME` locations.
- Safe-by-default JSON status output avoids leaking path and quota metadata into CI logs.

## 0.3.0 - 2026-06-03

### Added

- Filesystem-based profile discovery under `~/.codex-quota/profiles`.
- Profile management commands: `profile list`, `profile add`, `profile remove`, and `profile path`.
- `codex-quota login <profile> --create`.
- `codex-quota init --verify`.
- Dedicated profile and App Server modules for safer path handling and quota reads.
- Stable `ok` field in JSON status output.

### Changed

- `~/.codex-quota/profiles/<profile>/` became the source of truth for profile existence.
- Config no longer stores a static profile registry.
- `codex-quota init` now bootstraps and validates the environment only.
- status and check dynamically discover profiles from the filesystem.
- Config loading preserves unknown legacy keys while ignoring old profile registry data for discovery.
- TUI now uses dynamic profile discovery and shared service logic.

### Fixed

- Long-path wrapping in profile path output.
- macOS temp-path and symlink-sensitive profile path handling.
- Per-profile status collection now continues when one profile fails.
- Missing Codex binary is represented as a per-profile status error where appropriate.
- Malformed config JSON now raises a clear config error.
- Malformed App Server responses now raise a clear app-server error.

## 0.2.0 - 2026-06-03

### Added

- Textual-based fullscreen TUI.
- `Refreshed at HH:MM DD.MM.YYYY` timestamp above the status table.
- `codex_ok` field in JSON status output.
- Safer unknown-profile validation for `status` and `check`.
- User-facing refresh/loading messages in TUI.
- Scroll-safe TUI input handling through Textual widgets.

### Changed

- Replaced the old Rich `Live` + manual prompt TUI with Textual.
- Improved status table formatting, colors, widths, and percentage display.
- `service.collect_statuses()` now distinguishes missing Codex binary from profile/auth failures.
- TUI refresh now runs asynchronously and does not block the command input field.
- Manual refresh no longer leaves a persistent `Refreshed.` panel.

### Fixed

- Mouse wheel escape-sequence pollution in the TUI command input.
- Refresh message panel persisting after manual refresh.
- Possible `KeyError` for unknown profile names in `status` and `check`.
- Date formatting from `DD:MM:YYYY` to `DD.MM.YYYY`.

### Removed

- Old Rich `Live` fullscreen TUI implementation.
- Manual raw terminal input handling with `select` / `read(1)`.

## 0.1.0 - 2026-06-03

Initial preview release.

### Added

- Python package under `src/codex_quota`.
- Multi-profile config stored separately from Codex homes.
- Profile directory initialization.
- Official Codex login delegation per profile via `CODEX_HOME`.
- App Server JSON-RPC quota reader for `account/rateLimits/read`.
- Human-readable status table and JSON output.
- Automation-friendly `check` command.
- Minimal low-reasoning `codex exec` wrapper.
- Simple Rich-based TUI with refresh, login, exec, and quit commands.
