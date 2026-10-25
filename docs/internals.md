# Internals

How HostPost works inside. [AGENTS.md](../AGENTS.md) has the conventions and
rough edges; this page describes the machinery.

## Startup

`src/main.py` (`HostBot.setup_hook`):

1. Creates the MySQL pool (`bot.db_pool`) and starts the shared APScheduler
   (`bot.scheduler`).
2. Loads `autopost_commands` and `hostpost_commands`, then `hosting_signup`, but
   only if `events_scheduled` has a `host_id` column. It has in every schema for a
   while, so the check always passes.
3. Syncs the command tree to `SERVER_ID`.

## Who may run commands

Every command except `/help` carries
`@app_commands.checks.has_any_role(*access_roles)`, with the role ids listed in
`src/data/event_post_text.py`. Discord's Integrations settings can narrow that
further, but can't widen it. A refusal answers that the bot is meant for Circuit
Crew.

The API accepts HostPost's key as staff, so this list is the real gate for what
HostPost does through the API.

## `/event_setup`

The wizard (`views/event_setup.py`) is one ephemeral message, rebuilt on every
click:

- A type-and-lobbies page, a settings modal, and one schedule page with a cursor
  over the slots.
- `EVENT_TYPES` and `LOBBIES` at the top of the file are how FZD runs events, not
  what the API allows. Widening a type's lobbies is an edit there, then a run on
  stage.
- A modal asks for what's typed or fixed. The message asks for what depends on the
  API's answer for a given minute, because a modal can't change while it's open.
- Only the person who ran the command can drive it (`interaction_check`). It times
  out after 14 minutes, just inside Discord's 15-minute token.
- Nothing is written until Confirm. Confirm sends `PUT /v1/events/{id}/scoring`,
  then `PUT /v1/events/{id}/schedule`. Both replace, so running it again after a
  failure is safe. The API refuses to replace a schedule that has results on it.
- After Confirm, a last page asks whether to autopost, and whether to validate the
  final results. The command then hands the written slots to the post pipeline,
  answering through the wizard's latest interaction, since the command's own token
  may have expired.

An event missing from HostPost's event list, or a slot with no short name in
`data/slot_mapping.py` (Pro Tracks, Team Battle), ends at Confirm: the schedule is
written, and no posts are made.

## Building the posts

1. `prix_list_from_slots` (`data/slot_mapping.py`) turns the slots into a list of
   `Prix`, keyed on the short names in `prix_info`.
2. `build_posts` (`utils/build_hostposts.py`) builds `post_struct`: a list of
   `{name, post_text, post_type}` in a **fixed order** the scheduler depends on:
   1hr, 10min, then a GO post and a results post per prix, then the event results.
3. The 1hr, 10min and event results posts are templates from the database's
   `event_messages` table. A row for the event's host wins over the event's default
   row. Templates use `str.format` fields from `TemplateMap`
   (`data/template_mapping.py`). Prix posts are built in code (`build_gp_posts`).
4. `prepare_post_outputs` (`utils/hostpost_exports.py`) optionally runs the template
   editor, hands the posts to the scheduler, and always posts the drafts in the
   channel with a `.txt` copy.

Every draft is `header` plus a fenced body, and only the body is posted
(`clean_post`). A post containing its own triple backticks breaks this.

## Scheduling: two stores

APScheduler holds the timing, and `bot.job_stack` holds the text. They're split so a
post's text stays editable after it's queued: the job looks its message up by name
when it fires. Keep them in step. `schedule_job` adds to both;
`send_and_pop_message` and `remove_event_jobs` remove from both.

**Job names are the glue:** `"{date:%Y-%m-%d} | {event}_{suffix}"`, with suffixes
`1hr`, `10min`, `Prix#N`, `Prix#NResults` and `FinalResults`, plus
`getResults_<event>` and `hostUpdate_<event>`. Grouping, cancelling and validating
all work by matching on these names, so changing the format breaks the
autocompletes, `/cancel_event_posts` and `/validate_results`.

**When each post goes out** (`build_autopost_dict`, `utils/autoposts_utils.py`):

| Post | When | Channel |
|---|---|---|
| 1hr | 60 minutes before the first prix | announcement |
| 10min | 10 minutes before | engagement |
| `Prix#N` (GO) | public lobby: 1 minute before the prix; private: 4 seconds after it opens | engagement |
| `Prix#NResults` | queued **paused**; `/post_prix_winner` resumes it | engagement |
| `FinalResults` | queued **paused**, at scoreboard close: the last prix plus an hour, rounded to the half hour, less a minute | announcement |

**The final results.** `getResults_<event>` fires at scoreboard close:

- It reads the event's scoreboard from the API and fills the podium placeholders
  (`@[first]`, `@(first)`, `[firstpoints]` and so on; `podium` and `fill_podium`).
- It posts straight to the announcement channel only when validation is off and the
  board ranks three players.
- Otherwise, including when the API call fails, the draft goes to the validation
  channel, and the host runs `/validate_results`.
- Winners are mentioned as `<@discord_id>` from the scoreboard, which Discord
  renders without a member cache, so the bot needs no members intent.

**Host personas.** If the event's host has a row in `hosts`, `hostUpdate_<event>`
changes the bot's nickname and avatar to that persona (`bot_display_name`, and a
picture from `images/`) when the first post goes out.

**The job store is in memory.** A restart loses every queued post, with no warning.

## The API and the database

- **Through the API** (`src/fzd_api.py`): the calendar for the event pickers, an
  event's detail and scoreboard, the in-game rotation and lineups, and the scoring,
  schedule and host writes. The API resolves a Discord account to a player, so
  HostPost holds no "which row is this person" logic.
- **Straight to MySQL** (`src/fzd_db.py`): the hosting board, the post templates,
  the event's host and persona, and looking up a scheduled event by name.

## Errors and alerts

Unexpected errors are logged, with the traceback, and reported to
`ERROR_ALERT_CHANNEL_ID` by `error_alerts.py`. Logging goes to stdout at
`LOG_LEVEL`.
