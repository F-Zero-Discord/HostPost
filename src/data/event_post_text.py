"""
This module contains text information used in developing a posts for regular weekly events
"""

access_roles = [
    1504297025615822909, # TestRole, in lurchin' about
    1370902782860726362, # Circuit Crew
    1379213282984071169, # FZD Luminary
    1203448624000798750, # Staff Ghost
    1152973858773663744, # Mr. Zero
    1175813598040297483, # Captain Fox
]

automatable_posts = ["1hr", "10min", "go_post"]

prix_info = [
    {"shortname": "knight", "fullname": "Knight League", "emoji": "<:GPKnight:1195076261232525332>", "mirror_emoji": "", "tickets": 3, "mode": "99"},
    {"shortname": "mknight", "fullname": "Mirror Knight League", "emoji": "<:GPMirrorKnight:1222897223054921832>", "mirror_emoji": "<:Mirror:1258440078665977926>", "tickets": 3, "mode": "99"},
    {"shortname": "queen", "fullname": "Queen League", "emoji": "<:GPQueen:1195076266311811233>", "mirror_emoji": "", "tickets": 3, "mode": "99"},
    {"shortname": "mqueen", "fullname": "Mirror Queen League", "emoji": "<:GPMirrorQueen:1227803769950048296>", "mirror_emoji": "<:Mirror:1258440078665977926>", "tickets": 3, "mode": "99"},
    {"shortname": "king", "fullname": "King League", "emoji": "<:GPKing:1195076258002899024>", "mirror_emoji": "", "tickets": 3, "mode": "99"},
    {"shortname": "mking", "fullname": "Mirror King League", "emoji": "<:GPMirrorKing:1232859986405756968>", "mirror_emoji": "<:Mirror:1258440078665977926>", "tickets": 3, "mode": "99"},
    {"shortname": "ace", "fullname": "Ace League", "emoji": "<:GPAce:1291196458233630760>", "mirror_emoji": "", "tickets": 3, "mode": "99"},
    {"shortname": "mace", "fullname": "Mirror Ace League", "emoji": "<:GPMirrorAce:1400238135232958554>", "mirror_emoji": "<:Mirror:1258440078665977926>", "tickets": 3, "mode": "99"},
    {"shortname": "classicprix", "fullname": "Classic Mini Prix", "emoji": "<:MPClassicMini:1222897226880123022>", "mirror_emoji": "", "tickets": 1, "mode": "classic"},
    {"shortname": "miniprix", "fullname": "Mini Prix", "emoji": "<:MPMini:1195076264294363187>", "mirror_emoji": "", "tickets": 1, "mode": "99"},
    {"shortname": "glitchgp", "fullname": "Glitch GP", "emoji": "<:GPSecretKnight:1462611891447791700>", "mirror_emoji": "", "tickets": 3, "mode": "99"},
    {"shortname": "worldtour", "fullname": "World Tour", "emoji": "<:WTMini:1462608159913934881>", "mirror_emoji": "", "tickets": 0, "mode": "99"},
    {"shortname": "miniwt", "fullname": "Mini World Tour", "emoji": "<:WTMini:1462608159913934881>", "mirror_emoji": "", "tickets": 0, "mode": "99"}
]

schedule_line = {
    "public_multi_tickets": "<:EventTimer:1213542180195536897> {0} <:Tickets:1218943498338697256> Public {1} {2} {3}\n",
    "public_one_ticket": "<:EventTimer:1213542180195536897> {0} <:Ticket:1194747589610967131> Public {1} {2} {3}\n",
    "public_no_tickets": "<:EventTimer:1213542180195536897> {0} Public {1} {2} {3}\n",
    "private": "<:EventTimer:1213542180195536897> {0} <:Private:1227046530721251479> Private {1} {2} {3}\n",
    "private_mp_lineup": "<:EventTimer:1213542180195536897> {0}  {1} > {2} > {3}\n",
            }

# Note that 'fullname' needs to be the same as the name in the 'events' table in the database.
events = [
    {"shortname": "machine_mastery", "fullname": "Machine Mastery",
     "score_channel": "https://discordapp.com/channels/1019374132342816800/1212468365826981888"
     },
    {"shortname": "friday_eu", "fullname": "Friday EU GP", # fzd_dev="Friday FZD EU"; fzd_prod=""Friday EU GP"
     "score_channel": "https://discordapp.com/channels/1019374132342816800/1212468711185715260"
     },
    {"shortname": "friday_na", "fullname": "Friday NA GP", # fzd_dev="Friday FZD NA"; fzd_prod=""Friday NA GP"
     "score_channel": "https://discordapp.com/channels/1019374132342816800/1212468778609147976"
     },
    {"shortname": "ead", "fullname": "Euro-Asia Drift",
     "score_channel": "https://discordapp.com/channels/1019374132342816800/1289209764307406909"
     },
    {"shortname": "classics", "fullname": "Saturday Classics", 
     "score_channel": "https://discordapp.com/channels/1019374132342816800/1344118938539135030"
     }, 
    {"shortname": "cracked", "fullname": "Cracked Cup",
     "score_channel": "https://discordapp.com/channels/1019374132342816800/1212468894124736613"
     },
    {"shortname": "apac", "fullname": "Asia-Pacific Open", 
     "score_channel": "https://discordapp.com/channels/1019374132342816800/1228660432307490846"
     },
    {"shortname": "classic_mm", "fullname": "Classic Machine Mastery",
     "score_channel": "https://discordapp.com/channels/1019374132342816800/1406063056861007872"
     },
    {"shortname": "wacky_w", "fullname": "Wacky Wednesday",
     "score_channel": "https://discordapp.com/channels/1019374132342816800/1219953737284587570"
     },
]

custom_text = [
    {"clean_driving": "For each WT you complete, you can earn 5,000 points for driving CLEAN. What is driving CLEAN? Driving CLEAN means you have to play without using unconventional strategies to farm points, like holding up a race to get gems.\n\n"}
]

clean_driving_list = ["miniwt", "worldtour"]

time_offset_options = {
    "no offset": 0,
    "15 minutes": 15,
    "20 minutes": 20,
    "30 minutes": 30,
    "40 minutes": 40,
    "60 minutes": 60
}

help_text_1 = (
    "## HostPost Help\n\
This bot assists hosts of weekly FZD events in creating and posting event announcements, \
prix opening posts, and event results posts. It also has an autoposting feature that can \
automatically post the announcement and prix opening posts at the scheduled times.\n\n\
**Note:** There currently is no PengBot support for importing prix and times, so the user \
will need to look them up first. Also, that means there is no support for mini prix lineups \
in the posts.\n\n\
### /event_setup\n> This command starts the interactive process for creating \
event posts. The bot will ask you to select the prix and time offsets for each prix in your \
event. The time offset can be done in 'Simple' mode, where standard time offsets are provided, \
or in 'Custom' mode, where you can specify times to the minute. The time offset for the first \
prix is usually 0 or 'no offset', but could be adjusted if your starting prix does not start \
exactly on the hour. Once complete, your will be asked if you want the bot to automatically \
post the announcement and prix opening posts at the scheduled times in \
https://discordapp.com/channels/1019374132342816800/1244994645155385404 and \
https://discordapp.com/channels/1019374132342816800/1185690454658912397. Posts are then \
generated.\n"
)

help_text_2 = (
"## Event Management\n\
### /list_autopost_events\n> Lists the events that are currently queued for autoposting.\n\n\
### /list_all_autoposts\n> Lists all queued automatic posts and their post times in \
Coordinated Universal Time (UTC).\n\n\
### /cancel_event_posts\n> Allows the user to cancel all automatic posts for the scheduled events.\n\n\
### /cancel_all_posts\n> Allows you to cancel all queued posts. Brute force. Use with care.\n\n\
### /post_prix_winner\n> Allows you to select a pending prix result post and a member of the server \
and posts the prix results post in racetrack.\n\n\
### /edit_pending_autopost\n> Pulls up a dialog box with the selected post and allows for editing.\n\n\
### /validate_results\n> Allows the host to post the event results message. Cancels any other \
pending jobs for the event, and closes the event.\n\n\
### /push_job\n> Triggers any pending job, whether scheduled or paused. Shouldn’t need to be used \
outside of testing.\n\n\
## Hosting Management\n\
### /hosting_schedule\n> List the schedule for the coming week and who is assigned to host.\n\n\
### /update_host_for_event\n> Add or change who is listed as the host for an event.\n\n\
### /remove_host_from_event\n> Remove who is listed as host for an event.\n\n\
### /help\n> Shows this message.\n\nIf you have any questions, suggestions, \
or issues, please contact lurch."
)