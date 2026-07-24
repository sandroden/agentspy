# Installation

Two install scripts automate the setup: `install.sh` (Linux/macOS) and
`install.ps1` (Windows PowerShell). Both are idempotent (safe to re-run) and
reversible.

## What the scripts do

- generate `~/.config/agentspy/hooks.json` from `hooks/settings-example.json`,
  substituting the real path of this checkout for the `/PATH/TO/agentspy`
  placeholder;
- add a `claude-spy [tag]` function to your shell so a session is spied on with
  a single command.

```bash
git clone <this repo> && cd agentspy
bash install.sh          # or: chmod +x install.sh && ./install.sh
# open a new shell (or: source ~/.bashrc / ~/.zshrc)

cd agentspy && just up
cd my-project-to-spy
claude-spy my-tag
```

On Windows:

```powershell
.\install.ps1
# open a new PowerShell (or: . $PROFILE)
```

## The `claude-spy` shell function

The generated function wraps a single `claude` invocation with everything
needed to spy on it: it points `ANTHROPIC_BASE_URL` at the collector
(`http://127.0.0.1:8082`), sets the tag on both channels
(`ANTHROPIC_CUSTOM_HEADERS: x-agentspy-tag: <tag>` and `AGENTSPY_TAG`), clears
`ANTHROPIC_API_KEY`, and loads the generated `hooks.json` with `--settings`.
The tag argument defaults to `spy` when omitted (`claude-spy` == `claude-spy
spy`).

## Flags

- `install.sh --uninstall` / `install.ps1 -Uninstall`: remove the `claude-spy`
  function from the shell rc files (the generated `hooks.json` is left in
  place; remove it by hand if you want).
- `install.sh --no-rc` / `install.ps1 -NoRc`: write `hooks.json` only and print
  the function instead of touching your shell config.
- `install.sh --help`.

`install.ps1` is community-contributed and not covered by CI on Windows —
please report issues.

## Service commands (justfile)

The `justfile` in the repo root drives the collector ([just](https://just.systems)):

| Command | Effect |
|---------|--------|
| `just up` | build the frontend, then start the collector in the background (default port 8082, DB `./agentspy.db`) |
| `just down` | stop the collector |
| `just restart` | `down` + `up` (migrations and rehydration run on start) |
| `just status` | is the collector running? |
| `just build` | build the UI only (served by the collector on `/ui`) |
| `just seed` | populate the demo DB and print how to run it |
| `just test` | run the collector tests |

Variables are overridable: `just port=8082 db=./server/agentspy.db up`. There
is no `just install` — the initial setup is `install.sh` / `install.ps1`.

## See also

- [Providers and gateways](providers-and-gateways.md) — routing one instance
  per upstream (Anthropic, OpenRouter).
- [Hooks](hooks.md) — the hooks channel that `hooks.json` sets up.
- [Development](development.md) — running from source, tests, demo seed.
- [`.okf/runbooks/quickstart.md`](../.okf/runbooks/quickstart.md) — the
  internal quick-start runbook.
