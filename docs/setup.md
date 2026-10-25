# Setup

How to get HostPost running on your own machine.

## What you need

- **Python 3.12**, and [uv](https://docs.astral.sh/uv/).
- **A Discord application of your own**, or HostPost's secondary test application,
  in a test server, with the message-content intent turned on. Never run locally
  with the live token: two processes on one token both answer every command.
- **MySQL credentials** for the environment you're testing against. Most commands
  read the database directly.
- **Optionally, an FZD API and a key for it.** `/event_setup`,
  `/update_host_for_event` and `/remove_host_from_event` go through the API; without
  it, those three say the API isn't configured, and the rest work.

## Install

```bash
uv sync
```

`uv.lock` pins every version. To upgrade a dependency, run
`uv lock --upgrade-package <name>`, try the bot on stage, and commit the lock.

## Configure

Settings come from `.env` in the repository root, or from `.env.NAME` with
`uv run hostpost --env NAME`. The named file is read **instead of** `.env`, not on
top of it. Start from `.env.example`, which also explains the variants in use. Every
`.env*` file except `.env.example` is ignored by git.

`src/settings.py` is the source of truth for what follows.

| Setting | Required | Default | What it does |
|---|---|---|---|
| `DISCORD_TOKEN` | yes | | The bot's token. |
| `SERVER_ID` | yes | | The server the commands are registered to. |
| `DB_USER`, `DB_PASSWORD`, `DB_NAME` | yes | | The database account and schema. |
| `DB_HOST` | no | `localhost` | |
| `DB_PORT` | no | `3306` | |
| `EVENT_ANNOUNCE_CHANNEL` | yes | | Where the 1-hour post and the final results go. |
| `ENGAGE_CHANNEL` | yes | | Where the 10-minute post, the GO posts and the prix results go. |
| `VALIDATION_CHANNEL` | yes | | Where final results wait for a host to check them. |
| `ERROR_ALERT_CHANNEL_ID` | yes, may be empty | | Where unexpected errors are reported. Empty turns alerts off. |
| `HOSTING_SCHEDULE_CHANNEL`, `HOSTING_SCHEDULE_MESSAGE_ID` | yes, may be empty | | The hosting board: the bot edits that message in place. Empty makes the host commands say the board isn't configured, and skip it. |
| `FZD_API_BASE_URL` | no | empty | Where the FZD API is. Empty turns off the three commands that use it. |
| `FZD_API_KEY` | no | empty | HostPost's key for that API. |
| `FZD_API_TIMEOUT_SECONDS` | no | `10` | How long an API call may take. |
| `LOG_LEVEL` | no | `INFO` | |
| `TEST_FLAG` | no | `0` | `1` turns on test mode (below). |

"May be empty" means the line has to be in the file, but its value can be blank. A
missing line stops the bot at startup.

**Point the API and the database at the same environment.** The commands that use
the API and the ones that use the database directly would otherwise read different
data, and the setup looks fine while testing nothing.

## Run

Always from the repository root, as a script or a module, never as
`python src/main.py`. Imports are absolute (`from src.…`), and the host personas'
pictures are opened from `images/` relative to the current directory.

```bash
uv run hostpost                         # reads .env
uv run hostpost --env stage             # reads .env.stage
uv run python -m src.main               # the same entry point, without the script
```

On startup HostPost creates its database pool and scheduler, loads its cogs, and
syncs its commands to `SERVER_ID`.

## Test mode

With `TEST_FLAG=1`, every queued post goes out about 30 seconds after the one
before, starting now, instead of at its real time. The `@Events` and
`@Classic Events` pings are replaced with harmless placeholders. Use it to walk
through an event's posts in a few minutes.

## Before you open a pull request

```bash
uv run pyright        # clean is the bar
uv run ruff check     # clean is the bar
```

There's no test suite. `ruff format` hasn't been applied to the whole repo: format
the files you change, not their neighbours.
