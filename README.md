# codex-quota

A utility for managing isolated Codex CLI profiles and monitoring quota usage across multiple Codex environments.

Includes JSON output for automation and a live terminal dashboard.

> **Note:** This is an independent community tool. It is not affiliated with or endorsed by OpenAI.

---

## Requirements

- Python 3.11+
- Official Codex CLI available as `codex`

Install Codex CLI:

```bash
npm install -g @openai/codex
```

or

```bash
brew install codex
```

Tested with `codex-cli 0.136.0`.

---

## Installation

> PyPI package coming soon. For now, clone the repository and install manually:

```bash
git clone https://github.com/ssh-den/codex-quota.git
cd codex-quota
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

---

## Quick Start

```bash
# Initialize (creates config and profiles directory)
codex-quota init

# Add a profile and log in
codex-quota profile add personal --login

# Check quota status
codex-quota status

# Launch the live terminal dashboard
codex-quota tui
```

---

## Security

Authentication is fully delegated to the official Codex CLI. `codex-quota` never reads, stores, or transmits credentials. It sets `CODEX_HOME` and calls `codex` on your behalf.

Profile and config directories are created with `0700` permissions on POSIX systems so `auth.json` and related state are not exposed by a weak `umask` on multi-user machines.

---

## Script filesystem layout

```
~/.codex-quota/profiles/
├── personal/
├── work/
└── testing/

~/.config/codex-quota/
└── config.json
```

The filesystem is the source of truth. Profiles are discovered dynamically. The configuration file stores application settings only and does not maintain a profile registry.

---

## Configuration

Default configuration:

```json
{
  "profiles_dir": "~/.codex-quota/profiles",
  "codex_bin": "codex",
  "default_model": "gpt-5.4-mini",
  "reasoning_effort": "low",
  "refresh_seconds": 30.0
}
```

Edit `~/.config/codex-quota/config.json` to change model defaults or reasoning effort.

---

## Initialization

```bash
codex-quota init
```

Behavior:

- Create config directory if missing
- Create profiles directory if missing
- Create `config.json` if missing
- Preserve existing configuration
- Verify Codex CLI installation
- Print detected Codex version
- Discover existing profiles by scanning `~/.codex-quota/profiles/*`

Overwrite configuration:

```bash
codex-quota init --overwrite-config
```

Run bootstrap plus quota verification (`--check` is an alias):

```bash
codex-quota init --verify
```

---

## Profile management

List profiles:

```bash
codex-quota profile list
```

Add profile:

```bash
codex-quota profile add personal
```

Create and login immediately:

```bash
codex-quota profile add personal --login
```

Create and force device-code auth on headless or remote machines:

```bash
codex-quota profile add personal --login --device-auth
```

Print profile path:

```bash
codex-quota profile path personal
```

Remove profile:

```bash
codex-quota profile remove personal
```

Force remove (non-interactive):

```bash
codex-quota profile remove personal --yes
```

Profile names are validated. Path traversal, path separators, absolute paths, whitespace, and suspicious characters are rejected.

---

## Login

```bash
codex-quota login personal
```

Equivalent to:

```bash
CODEX_HOME="$HOME/.codex-quota/profiles/personal" codex login
```

Use device authorization instead of the local browser callback flow:

```bash
codex-quota login personal --device-auth
```

Create the profile automatically if missing:

```bash
codex-quota login personal --create
```

Combine both when bootstrapping a remote profile in one step:

```bash
codex-quota login personal --create --device-auth
```

---

## Status

All profiles:

```bash
codex-quota status
```

Single profile:

```bash
codex-quota status personal
```

JSON output:

```bash
codex-quota status --json
```

Example human-readable output:

```
Profile   Status   5h Left   Week Left
personal  OK       99%       69%
work      OK       74%       52%
```

Default JSON is safe for CI logs and automation:

- No absolute profile paths
- No raw `rateLimits` payload
- No plan or credits metadata unless explicitly requested

Opt in to the extra fields only when you need them:

```bash
codex-quota status --json --json-paths --json-raw
```

Quota lockout detection uses `rateLimitReachedType != null`. The tool does not infer lockout solely from `usedPercent == 100`.

---

## Check command

Automation-oriented health check:

```bash
codex-quota check
```

Single profile:

```bash
codex-quota check personal
```

Exit codes:

| Code | Meaning |
|------|---------|
| 0 | Selected profiles are authenticated, readable, and not quota-blocked |
| 2 | Codex missing, auth missing/expired, app-server failure, quota block, or no selected profiles found |

---

## Exec

Run Codex under a selected profile:

```bash
codex-quota exec personal "Reply with exactly: ok"
```

Disable forced JSON output:

```bash
codex-quota exec personal "Say hello" --raw
```

`exec` now respects the user's existing Codex config and rules by default instead of disabling them.

---

## TUI

Launch:

```bash
codex-quota tui
```

Custom refresh interval:

```bash
codex-quota tui --refresh 15
```

The TUI uses Textual and dynamically discovers profiles from the filesystem.

Available commands:

```
refresh
login <profile> [--device-auth]
exec <profile> <prompt>
quit
```

---

## Internal quota API

Status collection launches:

```bash
CODEX_HOME=<profile-home> codex app-server --stdio
```

Then performs the following JSON-RPC sequence:

```
1. initialize
2. initialized
3. account/rateLimits/read
```

Responses are normalized for display and safe JSON output. Raw API values are available only through explicit `--json-raw`.

---

## License

MIT License
