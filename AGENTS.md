# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

HostPost is a Discord bot for the F-Zero Discord (FZD) that builds and auto-posts the message
sequence around a weekly racing event: announcement (1 hr out), 10-minute warning, per-prix "GO"
posts, per-prix winner posts, and a final results post assembled from scores in the FZD MySQL
database. See `README.md` for the user-facing command reference.

## Design philosophy

Per decision 0009: **contributor experience outranks robustness.** Four volunteers touch FZD's
code, and this bot is maintained and deployed by one of them on their own hardware. A change that
generally works and ships beats one that always works and never lands. When a choice trades "harder
to contribute to" against "harder to break", choose the one that can be contributed to — the
question a review asks is "could the maintainer of this bot land this change?", ahead of "is this
maximally correct?".

**The governing principle is simplicity.** This is a low-throughput hobby bot: a handful of
scheduled posts per event. Code should be as simple as possible while doing what it has to. Do not
add an abstraction, safeguard or pattern unless there is a clear, present need — not a hypothetical
future one. Do not add a step unless it is obviously needed. Prefer readable code over code that
guards against concurrency or edge cases that this scale makes negligible.

When to add, and when to remove:

- **Structure has to pay for something specific.** A helper, a layer or a rule exists because it
  makes one named hard thing mechanical — the two-store split under "Scheduling" exists so post text
  stays editable after a job is queued, and for no other reason. Anything not paying for something
  like that should be deleted, not kept out of respect.
- **An exception is the bar for the next one.** The optional API settings under "Configuration" are
  the deliberate guard this bot carries: a bounded failure of two commands instead of the whole
  bot. A new guard is measured against that one and has to be at least as well-founded.
- **Name the price.** A pattern that costs every ordinary change something is fine only if the text
  next to it says what that is and what it buys.
- **Retire on evidence, not calendar.** Remove a guard or a branch when it is observed to be
  unused, not when it feels old — the vestigial `information_schema` check on the hosting cog is a
  candidate — and do not keep it because it might be needed someday.

Two things are outside this decision, and only two: unrecoverable loss of data, and reliability
during a major event such as a GGP. Everything else is "breaks on Friday, fixed on Saturday". Where
simplicity and correctness pull apart, say so in the change rather than quietly optimising for
robustness out of habit.

## Commands

```bash
uv sync                               # install (Python 3.12, uv-managed; uv.lock is authoritative)
uv run hostpost                       # run the bot on .env — must be from the repo root
uv run hostpost --env stage           # against api-stage.fzd.gg / fzd_stage
uv run hostpost --env stage-local-api # against a local fzd-api over the stage database
uv run python -m src.main             # the same entry point, without the script
```

Run it from the repo root and as a module or script, never `python src/main.py`: every import is
absolute (`from src.…`), and `change_name_and_pfp` opens `images/<file>` relative to the CWD.

There is no test suite, linter, or formatter configured. `requirements.txt` is a stale export kept
alongside `pyproject.toml`; edit dependencies in `pyproject.toml`.

## Configuration

`src/settings.py` is a pydantic-settings `Settings` model that reads **`.env`**, or with
`hostpost --env NAME` **`.env.NAME` in its place** — not on top of it: a setting the named file
leaves out fails startup rather than being taken from `.env`, and a name with no file is refused.
Settings are cached with `lru_cache`, so `get_settings()` is safe to call anywhere. Every `.env*`
but `.env.example` is gitignored. The names in use, same shape as fzdbot's:

| File | Run |
|---|---|
| `.env.dev` | fully local: a local MySQL and a local fzd-api |
| `.env.stage` | this bot, locally, against `api-stage.fzd.gg` and `fzd_stage` |
| `.env.stage-local-api` | this bot, locally, against a local `fzd-api` on `:8000` over `fzd_stage` (`uv run serve --env stage-db` in `../fzd-api` first) |
| `.env.prod` | the live bot's settings; on a development machine keep them here, not in `.env` |

The two stage files run as HostPost's secondary Discord application in the `lurchin about` test
guild, so they can run alongside a fzdbot stage run, which is a different application. Their
`FZD_API_KEY` is the same key fzdbot's stage files use — the stage bot key from
`/etc/fzd-api/issued/stage-fzdbot.key` on the VPS, and the locally minted key in
`~/.config/fzd/local-api-key.txt` — since one bot key serves any client and both may run at once.

Required (no default): `DISCORD_TOKEN`, `SERVER_ID`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`,
`EVENT_ANNOUNCE_CHANNEL`, `ENGAGE_CHANNEL`, `VALIDATION_CHANNEL`, `ERROR_ALERT_CHANNEL_ID`,
`HOSTING_SCHEDULE_CHANNEL`, `HOSTING_SCHEDULE_MESSAGE_ID`. The last three may be present but
empty: an empty alert channel turns alerts off, and an empty hosting channel or message id makes
the host commands say the board is not configured and skip refreshing it.

`FZD_API_BASE_URL` and `FZD_API_KEY` are **optional on purpose** (`FZD_API_TIMEOUT_SECONDS`
defaults to 10). They are needed by `/event_setup`, `/update_host_for_event` and
`/remove_host_from_event`; left empty, those three reply that the API is not configured and the
job-management commands are unaffected. Making them required would take the whole bot down, which
is the bounded failure Plan 15 deliberately designed against — lurch deploys this bot, and that
deploy is not simultaneous with anything.

Known gap: `HOSTING_SCHEDULE_CHANNEL` and `HOSTING_SCHEDULE_MESSAGE_ID` are still absent from the
untracked `.env.dev` and `.env.prod` (absent, not empty), so startup raises a pydantic
`ValidationError` against either until the lines are added. The stage files have the channel and
an empty message id: no anchor message has been posted in the test guild yet, so the board is
skipped there.

`TEST_FLAG=1` rewrites every scheduled post time to fire ~30 s apart starting now and swaps the
`@Events` / `@Classic Events` role pings for inert placeholders (`src/utils/autoposts_utils.py`).

## Architecture

Startup (`src/main.py`, `HostBot.setup_hook`) creates the aiomysql pool (`bot.db_pool`) and the
global APScheduler (`bot.scheduler`), then loads three cogs and force-syncs the command tree to
`SERVER_ID` — all commands are guild-scoped, so changes appear immediately.

- `cogs/hostpost_commands.py` — `/event_setup` (schedule and scoring entry, then the post builder)
  and `/help`. The wizard itself is `views/event_setup.py`.
- `cogs/autopost_commands.py` — `PostScheduler`: scheduling plus every job-management command.
- `cogs/hosting_signup.py` — host assignment (`/update_host_for_event`,
  `/remove_host_from_event`) and the live schedule embed (`/hosting_schedule`). The two host
  commands go through the **FZD API** (`src/fzd_api.py`), not the database — see below.
  **Loaded conditionally**: `check_db_for_hosting_support` inspects `information_schema` and skips the cog
  if `events_scheduled.host_id` does not exist. The column now exists in all three schemas
  (`fzd_dev`, `fzd_prod`, `fzd_playground`), so the guard always passes — it is vestigial, kept
  against a rollback rather than protecting a live gap.

### The post-building pipeline

`/event_setup <event>` → `EventSetupView` (`views/event_setup.py`) collects the scoring, the kind
of evening, and one entry per slot, then at Confirm sends `PUT /v1/events/{id}/scoring` and
`PUT /v1/events/{id}/schedule` and keeps the slots the second answers → `prix_list_from_slots`
(`data/slot_mapping.py`) turns those into per-prix `{prix, time, prix_type, lineup}` keyed on the
`prix_info` shortnames → `build_posts` (`utils/build_hostposts.py`) → `post_struct`, a list of
`{name, post_text, post_type}` dicts in a **fixed order** the scheduler depends on: 1hr, 10min,
then alternating go_post/results_post per prix, then event_results. `prepare_post_outputs`
(`utils/hostpost_exports.py`) optionally runs the edit wizard, hands `post_struct` to
`PostScheduler.post_scheduler`, and always echoes drafts to the channel plus a `.txt` attachment.

The wizard's draft is view state until Confirm: the message is ephemeral, `interaction_check`
refuses anyone but the invoker, nothing is cached across commands, and both writes replace, so a
second run after a failure is safe. `slot_mapping.py` is the one place the API's `(mode name,
lineup name)` meets `prix_info`; a `lineup` track list is filled only for a private Mini Prix,
because a filled list is what makes the templates print the set and hand out a passcode.

Post text for the 1hr, 10min, and event-results posts comes from the **database** (`event_messages`
joined to `events`), not from code: `get_post_template` prefers a row matching the event's assigned
`host_id` and falls back to the row with `host_id IS NULL`. Templates use `str.format` placeholders
supplied by `TemplateMap.mapping` (`data/template_mapping.py`). Prix go/results posts are still
built as f-strings in `build_gp_posts`.

Every draft is `"<header>```<body>```"`. `clean_post` strips the header and fences — the fenced body
is what actually gets posted. Nested triple-backticks inside a post will break this.

### Scheduling: two parallel stores

APScheduler holds the timing; `bot.job_stack` (a plain list on the bot, keys `job_name` / `message` /
`time`) holds the text. The split exists so text stays editable after a job is queued — the fired
callback `post_message` looks the message up by `job_name` at send time. Both must be kept in sync:
`schedule_job` appends to the stack, `send_and_pop_message` and `remove_event_jobs` remove from it.

Job names are the coupling glue: `f"{start_date:%Y-%m-%d} | {event}_{suffix}"` with suffixes `1hr`,
`10min`, `Prix#N`, `Prix#NResults`, `FinalResults`, plus `getResults_<event>` and
`hostUpdate_<event>`. Grouping and cancellation work by substring / `rsplit("_", 1)` on the job id,
so changing this convention breaks autocomplete, `/cancel_event_posts`, and `/validate_results`.
The same string is rebuilt independently in `hostpost_commands.event_setup` as
`scheduled_event_name` to look the event up in `events_scheduled.display_name`.

Prix-results and FinalResults jobs are scheduled **paused**; `/post_prix_winner` and
`/validate_results` resume them. `getResults_*` fires at scoreboard close, pulls scores, substitutes
the `@[first]` / `@(first)` / `[firstpoints]` placeholders, and either posts straight to the
announce channel or drops a draft in the validation channel for the host to approve.

The APScheduler job store is **in memory** — a bot restart silently loses every queued post.

### The FZD API

`src/fzd_api.py` is an `aiohttp` client for `api.fzd.gg`. `/update_host_for_event` and
`/remove_host_from_event` (task 15-04, the first bot commands in the project to move) `PUT` /
`DELETE /v1/events/{scheduled_event_id}/host`, sending the host's Discord snowflake and username,
and the API resolves that to a row in `users` and writes `events_scheduled.host_id` itself. This
bot never sees a `users.id`, which is why the commands were ported rather than handed an identity
endpoint. `/event_setup` (task 19-06) reads the calendar (`GET /v1/events`), an event
(`GET /v1/events/{id}`), the in-game rotation and lineup offers (`GET /v1/ingame/…`) and the
lineup catalogue (`GET /v1/lineups`), and writes the scoring and the schedule. Every method
answers the decoded JSON as sent, datetimes as ISO 8601 strings; callers parse what they use.

Deliberate properties, all of them load-bearing:

- **No fallback to a direct connection.** A failure is reported to the host and nothing is written.
  A fallback would put a second copy of the identity policy back in this bot.
- **`FzdApiError` only.** The cog catches that and replies; anything else propagates to
  `HostBot.on_app_command_error`, which alerts.
- **Both commands `defer()` before the call.** An HTTP hop from lurch's Raspberry Pi to the VPS
  plus a board refresh can outrun Discord's 3-second interaction window. `HostingSchedule.respond`
  exists because a deferred interaction can only be answered with a followup, and the same helpers
  are reached from both the deferred and the undeferred path.
- The snowflake goes over the wire as a **string** — it exceeds 2^53 and fzd-web is also a client.
- `tag` is trimmed to 10 characters here; the API rejects a longer one rather than truncating.

The client is built in `HostBot.setup_hook` as `bot.api` and closed in `HostBot.close`.

### Database

`src/fzd_db.py` is a trimmed copy of fzd-bot's DB layer: `get_db_connection` is an async context
manager over the pool, `execute_query` commits or rolls back per call. All access is raw SQL against
the shared FZD schema — `events`, `events_scheduled`, `users`, `event_result_points`,
`event_messages`, `hosts`. The bot only reads events the FZD database has already scheduled; it
cannot invent one. `get_scheduled_event_id` (a lookup by `events_scheduled.display_name`, rebuilt
from the job name) is still what `autopost_commands` uses to find the event a job belongs to.

Its `users` footprint is now exactly two read-joins, and both read a *username* for display — do
not repoint either at the snowflake: `get_event_scores`, whose `discord_name` feeds
`discord.utils.get(..., name=...)` in `autopost_commands`, and `get_hosting_schedule`. The write
path against `users` and against `events_scheduled.host_id` is gone; see the FZD API above.

That schema is much larger than the slice HostPost touches, and dev/prod are not the same shape.
`../fzd-db` documents all three schemas (generated from live introspection): `docs/overview.md`
for the inventory, `docs/drift.md` for what differs between `fzd_dev`, `fzd_prod`, and
`fzd_playground`, and `docs/<schema>/tables/*.md` per table. Regenerate with the scripts in
`../fzd-db/tools/`. Relevant to changes here: `events` handles time differently in dev
(`utc_time_std` + `utc_time_dst` + `dst_region`) than in prod (a single `utc_time`).

### Hardcoded IDs

Role IDs (command access, `@Events` pings), custom emoji IDs, and score-channel URLs live inline in
`data/event_post_text.py` and `utils/build_hostposts.py`. The `events` list there is matched against
`events.name` in the database, and dev and prod use different display names for the same event (see
the comments on `friday_eu` / `friday_na`) — an event that works in dev can silently 404 in prod.
The `/event_setup` wizard's buttons are the exception to the inline emoji ids: they look a prix's
emoji up **by name** in the guild the command runs in (`slot_mapping.prix_emoji_name`), so the
`lurchin about` test guild carries copies of FZD's twelve prix emoji under the same names, and a
button emoji never depends on an FZD id.

## Conventions and rough edges to expect

- The codebase mixes `print` and `logging`; new code should use module-level `logger`, and errors
  routed through `src/error_alerts.py` reach the configured alert channel.
- `hostpost_exports.prepare_post_outputs` constructs a **second** `PostScheduler(bot)` rather than
  fetching the loaded cog. It works only because the scheduler and job stack both live on `bot`.
- `main.py` builds `intents` twice (module level and in `main()`); the one in `main()` wins and does
  not set `members`, even though member lookup is used for winner mentions.
- Work happens on `dev`; `main` is the PR target.

## Comments and comment structure

Code should be self-documenting, to the best extent possible. Comments should be
sparse, and not document the obvious. If the code needs comments, you may be
writing code that could be simplified. Sparse is about count, not length: a few
comments that orient a reader, not a remark at every site — and one of them may
run to a paragraph where the reason is real.

If the solution is best left as it is, a short comment that explains it is
welcomed.

**A comment states a present property of the code or the platform, and one this
repo can check.** That is the whole test. Write what a reader of the line cannot
deduce from it: a behaviour that makes the obvious code wrong, the constraint a
shape exists to satisfy, which of two readings of a value is meant.

Never in a comment:

- **Progress, tasks, plans or project decisions.** No task numbers, no "the plan
  asks for this", no "decision 0009". Those live in `fzd-project` and describe
  how the work is organised, not what the code does. A reason worth keeping is
  worth stating on its own; if it cannot be, it is not the code's business.
  Prose in this repo's docs may still cite them.
- **The past — of the code, of the data, or of a decision.** No "used to be", no
  "split from", no "rows written before the rename", no "we decided". History
  goes out of date silently: nothing fails, nobody notices, and the next reader
  trusts it. State the present property instead — the column *is* nullable, so
  the code *does* handle `None`.
- **The future.** No "this goes away once the API takes over", no "the next task
  will want it". Scope is a present fact and may be written down — "GGP8 only;
  another event is another module" — but a timeline is a prediction, and a
  comment that outlives one lies.
- **Another repo's internals, or an appeal to its docs.** `fzd-database`'s view
  definitions, `fzd-api`'s mappers, "the API docs say" — nothing here can notice
  when those stop being true. State the contract this repo owns instead: the
  request it sends and what it does with the answer.
- **First person.** "We" is either the authors, which is decision narration, or
  the code, which has a name.
- **A verdict where a mechanism belongs.** "That library is the wrong shape"
  gives the next reader nothing to act on. Name the thing they would otherwise
  reach for, then the property that rules it out: "Not `Format.RelativeTime`,
  the obvious candidate: it reads the clock itself and memoises on its
  arguments, so the string it returns is frozen at the first call".

Two things that look like violations and are not. **An absence may be
documented** — "no retries, no caching; this is not a queue" — because what a
thing deliberately does not do is a present fact about it. And **a comment may
say where to change something**: "this is the only place that names a group",
"delete this constant to hand the decision back to the caller". That is a
pointer, not a plan.

## Commits

**No `Co-Authored-By:` trailer.** A commit has one author. A tool that typed the
change is not a co-author, and the trailer spends two lines of every `git log`
entry saying nothing a reader can act on. This overrides any default instruction
to add one.
