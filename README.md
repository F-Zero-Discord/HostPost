# Purpose
The HostPost bot streamlines the process of hosting an event, eliminating most of the usual preparation work–including the need to develop timestamps–minimizing the pressure on the host to perform multiple actions as lobbies open, eliminating the cutting and pasting of lobby results, and tapping into information already captured in the database. The purpose of HostPost is to make hosting less stressful and easier to distribute among FZD staff. In exchange for the benefits, the host must spend some time learning the appropriate slash commands and the janky Discord ui.
HostPost provides the following features:
Auto-generates posts for an event using only the event name, GPs in the event, and time gaps between each GP.
Automatically posts 1hr, 10min, and GP start posts at the appropriate times.
Uses a slash command to post the GP winner to the engagement channel (i.e. #f-zero99-racetrack), selecting the winner from a dropdown of server members.
Provides the draft event results post in the staging channel (i.e. #playground) for the host to review and then approve for final posting in the announcement channel (i.e. #fzd-events) using a slash command.
Allows for all posts to be modified using a popout.

# Commands
### /event_setup
This command starts the interactive process for creating event posts. The bot will ask you to select the prix and time offsets for each prix in your event. The time offset can be done in 'Simple' mode, where standard time offsets are provided, or in 'Custom' mode, where you can specify times to the minute. The time offset for the first prix is usually 0 or 'no offset', but could be adjusted if your starting prix does not start exactly on the hour. Once complete, your will be asked if you want the bot to automatically post the announcement and prix opening posts at the scheduled times in ⁠F-Zero Discord⁠fzd-events and ⁠F-Zero Discord⁠f-zero99-racetrack. Posts are then generated.
### /list_autopost_events
Lists the events that are currently queued for autoposting.
### /list_all_autoposts
Lists all queued automatic posts and their post times in Coordinated Universal Time (UTC).
### /cancel_event_posts
Allows the user to cancel all automatic posts for the scheduled events.
### /cancel_all_posts
Allows you to cancel all queued posts. Brute force. Use with care.
### /post_prix_winner
Allows you to select a pending prix result post and a member of the server and posts the prix results post in racetrack. 
### /edit_pending_autopost
Pulls up a dialog box with the selected post and allows for editing.
### /validate_results
Allows the host to post the event results message. Cancels any other pending jobs for the event, and closes the event.
### /push_job
Triggers any pending job, whether scheduled or paused. Shouldn’t need to be used outside of testing.
### /hosting_schedule
Lists the schedule for the coming week and who is assigned to host.
### /update_host_for_event
Adds or changes who is listed as the host for an event.
### /remove_host_from_event
Removes who is listed as host for an event.
### /help
Shows this message.

The three hosting commands are only available when the database supports host assignment; see Architecture below.

`/update_host_for_event` and `/remove_host_from_event` go through the FZD API rather than writing to the database directly, so they need `FZD_API_BASE_URL` and `FZD_API_KEY` in `.env` (see `.env.example`). Without them those two commands reply that the API is not configured; every other command is unaffected.

# Access
HostPost commands have restricted access to the following roles:
- Captain Fox
- Mr. Zero
- Staff Ghost
- FZD Luminary
- Circuit Crew
- TestRole (in lurchin’ about test server)

The commands will be visible to any channel that HostPost has access to (including #f-zero99-racetrack, because the bot must post there), but anyone attempting to access without one of the above roles will be provided a message that the bot is meant for Circuit Crew so join today! Note that if HostPost is to write to a private channel, HostPost needs a role that has access to that channel, such as Circuit Crew.
There is no channel restriction within the bot, so the bot should be granted access to specific channels from the discord server.
Guild member intents are necessary because the bot looks up server members when allowing the host to select the mention of the member who won the prix.

# Channels
HostPost accesses these channel ids from a .env file:
- EVENT_ANNOUNCE_CHANNEL=
- ENGAGE_CHANNEL=
- VALIDATION_CHANNEL=
- ERROR_ALERT_CHANNEL_ID=
- HOSTING_SCHEDULE_CHANNEL=
- HOSTING_SCHEDULE_MESSAGE_ID=

1-hour and event results messages are posted to the EVENT_ANNOUNCE_CHANNEL, the draft results message is posted for host validation in VALIDATION_CHANNEL, and all other messages are posted in ENGAGE_CHANNEL. Errors are routed to ERROR_ALERT_CHANNEL_ID. The hosting schedule embed is kept up to date by editing the message at HOSTING_SCHEDULE_MESSAGE_ID in HOSTING_SCHEDULE_CHANNEL.

All of the above are required with no default, so the bot will not start until each is present in .env.

# Testing
The .env file has a TEST_FLAG. When set to 1, the time of each automatic post is overridden, and each is posted 30 seconds after the previous.Additionally, in test mode the pings to @Events and @Classic Events are also overridden so that they won’t activate.
Architecture
HostPost is constructed using command cogs similar to as is done in fzd-bot. This bot has three cogs/main modules: one to manage the `/event_setup` command and methods to build the posts, another to manage the commands associated with scheduling (using the APScheduler package), and a third for host assignment and the hosting schedule embed. The third is loaded conditionally — it is skipped if the `events_scheduled` table has no `host_id` column — so on a database without host support the hosting commands simply do not appear. In each is a god-class. Each also has one or more modules for functions that can live outside the class definition. One module contains all the relevant view classes (dropdowns, popups, buttons,...). The “event_post_text” module has the textual data (primarily template language), similar to how Pengbot manages data. The fzd_db.py module is a stripped down version of fzd-bot’s database interaction functions. The fzd_api.py module talks to the FZD API, which holds the database credentials; host assignment goes that way and no longer resolves users itself, so the “which row in `users` is this person” rule lives in one place instead of being copied into every bot. The remaining commands still use fzd_db.py, and the two will coexist until the rest of them move. The scheduler.py modules initializes the global scheduler. The scheduler has a job store in memory. Whenever the bot is restarted, job information is lost. Luckily, event setup is pretty straightforward in case of an outage. It is possible in the future to use the database as a job store.
One quirk (or, inefficiency) in the bot is that it includes both the APScheduler class job store and a global job stack list (not actually a stack, as it is not FIFO). These contain complementary information. The only reason for the job stack is that message info needs to be stored there so that it is editable, as messages contained in the job stack cannot be. The code takes pains to create a new job stack entry whenever a job is registered in the APScheduler job store, and it is removed from the job stack when a job is completed.

In the Discord Developer Portal, the bot must be provided both messaging and guild member intents.

# Known Issues
Several user interactions are not completely handled:
- When selecting prix times for an event, Custom mode allows free text of any number, positive or negative. In the future perhaps restrict to +/- 60 minutes.
- Autocomplete is doing a lot of the heavy lifting as to what commands can do what to what jobs. 
