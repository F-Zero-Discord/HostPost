# Structure

```text
src/
  main.py                   entry point: settings, database pool, scheduler, cogs, command sync
  settings.py               every setting, typed (pydantic-settings)
  fzd_api.py                the FZD API client
  api_types.py              the API's request and response shapes, generated
  fzd_db.py                 the MySQL pool and queries: scheduled events, hosts, post templates
  error_alerts.py           error reports to the alert channel
  cogs/
    hostpost_commands.py      /event_setup and /help
    autopost_commands.py      the post scheduler, and every command that manages queued posts
    hosting_signup.py         the hosting board and the host commands
  views/
    event_setup.py            the /event_setup wizard
    hostpost_views.py         the post template editor
  data/
    event_post_text.py        the role list, help text, prix names and emoji, post wording
    slot_mapping.py           turns the API's schedule into the prix list the posts are built from
    template_mapping.py       the fields a post template can use
  utils/
    build_hostposts.py        builds an event's posts from its name and prix list
    autoposts_utils.py        when each post goes out and where, and the final results podium
    hostpost_exports.py       the optional template edit, scheduling, and the drafts file
    scheduler.py              the shared APScheduler instance
    hostpost_utils.py         small time helpers
images/                     the host personas' profile pictures
scripts/
  api_types.py              regenerates src/api_types.py
deploy/                     the systemd unit, the update script and the deploy procedure
docs/                       this documentation
```

`commands.md` lists every command with its handler and line.
