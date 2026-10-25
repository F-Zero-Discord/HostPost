# How-to

## Add a command

1. Add it to the cog it belongs with, under `src/cogs/`, with
   `@app_commands.command(name=…, description=…)` and
   `@discord.app_commands.checks.has_any_role(*access_roles)`, as the other
   commands have. Describe every argument with `@app_commands.describe`.
2. Bind any autocomplete in the cog's `cog_load`.
3. Read and write through `src/fzd_api.py` where the API has the route; add a
   method there that returns a type from `src/api_types.py`.
4. Run `uv run pyright` and `uv run ruff check`.
5. Check the command's permissions in Discord: Server Settings → Integrations →
   HostPost.
6. Document it. In `fzd-docs`, run `make generate`, give the command an entry in
   `tools/commands/hostpost.toml`, then run `make repo-docs` to refresh
   [commands.md](commands.md). Update the staff how-to it affects, and `/help`'s
   text in `src/data/event_post_text.py`.

## Change a post's wording

- **The 1-hour, 10-minute and results posts** are rows in the database's
  `event_messages` table, one per event. A row for a specific host replaces the
  event's default row for events that host runs. A template uses `str.format`
  fields such as `{event_name}`, `{schedule}`, `{start_time_long}` and
  `{role_ping}`; `TemplateMap.mapping` in `src/data/template_mapping.py` lists them
  all.
- **The GO and prix results posts** are built in code, in `build_gp_posts`
  (`src/utils/build_hostposts.py`).
- **For one event only,** a host can edit the templates in the wizard's last step,
  or edit a queued post with `/edit_pending_autopost`.

## Offer another kind of event in `/event_setup`

`EVENT_TYPES` and `LOBBIES` at the top of `src/views/event_setup.py` say which types
and lobbies the wizard offers. Change them there, then try the wizard on stage. A
mode with no short name in `src/data/slot_mapping.py` still gets its schedule
written, but no posts.

## Add a host persona

A persona is a row in the `hosts` table (`bot_display_name`, and the picture's file
name) for the host's account, plus the picture in `images/`. The bot switches to it
when the first post of an event that host runs goes out.

## Regenerate `api_types.py`

```bash
uv run scripts/api_types.py                # from a ../fzd-api checkout
uv run scripts/api_types.py --url URL      # or from a running API's /openapi.json
```

Never edit the file by hand.

## Deploy

[deploy/README.md](../deploy/README.md) has the layout, the from-scratch install, and
the update command. HostPost runs from `dev`.
