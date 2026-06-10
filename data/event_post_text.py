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
    {"shortname": "worldtour", "fullname": "Frozen World Tour", "emoji": "<:WTMini:1462608159913934881>", "mirror_emoji": "", "tickets": 0, "mode": "99"},
    {"shortname": "miniwt", "fullname": "Mini World Tour", "emoji": "<:WTMini:1462608159913934881>", "mirror_emoji": "", "tickets": 0, "mode": "99"}
]

schedule_line = {
    "public_multi_tickets": "<:EventTimer:1213542180195536897> {0} <:Tickets:1218943498338697256> Public {1} {2} {3}\n",
    "public_one_ticket": "<:EventTimer:1213542180195536897> {0} <:Ticket:1194747589610967131> Public {1} {2} {3}\n",
    "public_no_tickets": "<:EventTimer:1213542180195536897> {0} Public {1} {2} {3}\n",
    "private": "<:EventTimer:1213542180195536897> {0} <:Private:1227046530721251479> Private {1} {2} {3}\n",
            }

# Note that 'fullname' needs to be the same as the name in the 'events' table in the database.
events = [
    {"shortname": "machine_mastery", "fullname": "Machine Mastery",
     "score_channel": "https://discordapp.com/channels/1019374132342816800/1212468365826981888",
     "announcement_intro": ":PoroSad: {0} {1}", 
     "announcement_outro": ":PoroSad: {0} {1}"
     },
    {"shortname": "friday_eu", "fullname": "Friday EU GP", # fzd_dev="Friday FZD EU"; fzd_prod=""Friday EU GP"
     "score_channel": "https://discordapp.com/channels/1019374132342816800/1212468711185715260",
     "announcement_intro": "# :earth_africa: Friday EU FZD GP starts {0} at {1}! :earth_africa: \n<@&1197169889417371689> Welcome back to another THRILLING addition of Friday FZD EU!\n## Schedule\n", 
     "announcement_outro": "Reminders will be posted on <#1185690454658912397> when the GP starts. Submit points in https://discord.com/channels/1019374132342816800/1212468711185715260. GLHF pilots <:FalconSalute:1154766486875938856>\n\n### You will need {0} {1} tickets to compete in this event."
     },
    {"shortname": "friday_na", "fullname": "Friday NA GP", # fzd_dev="Friday FZD NA"; fzd_prod=""Friday NA GP"
     "score_channel": "https://discordapp.com/channels/1019374132342816800/1212468778609147976",
     "announcement_intro": "# Friday NA FZD GP starts {0} at {1}! <:BFZ:1326207149252018247> \n<@&1197169889417371689>  Welcome back to another THRILLING addition of Friday FZD Americas!\n## Schedule\n", 
     "announcement_outro": "Be sure to join IMMEDIATELY when the lobby opens!\nYou will need **{0} {1} tickets** for this event.\n\nReminders will be posted on <#1185690454658912397>"
     },
    {"shortname": "ead", "fullname": "Euro-Asia Drift",
     "score_channel": "https://discordapp.com/channels/1019374132342816800/1289209764307406909",
     "announcement_intro": "# :star: Euro-Asia Drift starts {0} at {1}!\n<@&1197169889417371689> Welcome to another edition of Euro-Asia-Drift! Prepare for some intense lobbies in this event, perfect for both European and Japanese players!\n## Schedule\n", 
     "announcement_outro": "Reminders are to be posted in <#1185690454658912397> when each lobby starts. Do you have what it takes to become the next Mr. EAD? Go submit your points in https://discord.com/channels/1019374132342816800/1289209764307406909. GLHF pilots <:FalconSalute:1154766486875938856>\n\n「Euro-Asia-Drift」の新シリーズへようこそ!\nヨーロッパと日本のプレイヤーの両方にぴったりのこのイベントでは、GPをプレイします!\n\n各ロビー開始時には、#f-zero99-racetrack にてリマインドが投稿されます。\n次の 「Mr. EAD」 になる覚悟はありますか？\nポイントは以下から提出してください: https://discord.com/channels/1019374132342816800/1289209764307406909\n\nGLHF!! (Good Luck, Have Fun)\n\n### You will need **{0} {1} tickets** for this event."
     },
    {"shortname": "classics", "fullname": "Saturday Classics", 
     "score_channel": "https://discordapp.com/channels/1019374132342816800/1344118938539135030",
     "announcement_intro": "<@&1343646386981437561>\n# <:MPClassicMini:1222897226880123022> Saturday Classics starts {0} at {1}!\n## _IMPORTANT_ :bangbang:\n> If the initial lobby is full, and you end up in a secondary lobby, you are still allowed to participate and submit your score as long as:\n> - There is at least 1 other player in the lobby\n> - You take a screenshot of the final results screen and post it in the scoring thread: https://discordapp.com/channels/1019374132342816800/1344118938539135030\n> \n> In the event of multiple lobbies, there will be 2 podiums to accommodate all players.\n\n## 重要_:bangbang:\n> - 複数の部屋が許可されています\n> - もしあなたが二つ目の部屋に行くことになったら. あなたはまだ参加できます. 少なくとも1人の他の人がいる限り.\n> - 結果のスクリーンショットを共有してください https://discordapp.com/channels/1019374132342816800/1344118938539135030\n\nWelcome back to Saturday Classics!\n## Schedule\n",
     "announcement_outro": "Please submit your points in https://discord.com/channels/1019374132342816800/1344118938539135030. Codes will be put in https://discordapp.com/channels/1019374132342816800/1185690454658912397. GLHF pilots <:FalconSalute:1154766486875938856>\n\nポイントはこちらから提出してください: https://discord.com/channels/1019374132342816800/1344118938539135030 コードは https://discordapp.com/channels/1019374132342816800/1185690454658912397 に投稿されますパイロットの皆さん、頑張ってください <:FalconSalute:1154766486875938856>\n\n### You will need {0} {1} tickets to compete in this event."
     }, 
    {"shortname": "cracked", "fullname": "Cracked Cup",
     "score_channel": "https://discordapp.com/channels/1019374132342816800/1212468894124736613",
     "announcement_intro": "# Cracked Cup starts {0} at {1}! <:READY:1226990432454578277>\n<@&1197169889417371689> FZD's premier public event continues!\n## Schedule\n", 
     "announcement_outro": "Reminders will be posted on <#1185690454658912397>\n### **This event requires {0} {1} tickets to see Mute Cities.**"
     },
    {"shortname": "apac", "fullname": "Asia-Pacific Open", 
     "score_channel": "https://discordapp.com/channels/1019374132342816800/1228660432307490846",
     "announcement_intro": "# The :flag_au: :flag_jp: Asia Pacific Open starts {0} at {1}! <:READY:1226990432454578277>\n<@&1197169889417371689> Prepare yourself for intense competition! In this event, perfect for the Pacific-adjacent, we'll run highly competitive races.\n## Schedule\n", 
     "announcement_outro": "Submit your scores at https://discord.com/channels/1019374132342816800/1228660432307490846 to see how well you did! Good luck and see you on the racetrack!\n\nYou will need **{0} {1} tickets** for this event."
     },
    {"shortname": "classic_mm", "fullname": "Classic Machine Mastery",
     "score_channel": "https://discordapp.com/channels/1019374132342816800/1406063056861007872",
     "announcement_intro": "# <:MPClassicMini:1222897226880123022> Classic Mini Prix races start {0} at {1}! <:MPClassicMini:1222897226880123022>\n## _IMPORTANT_ :bangbang:\n> Be sure to request the <@&1343646386981437561> role in https://discordapp.com/channels/1019374132342816800/1234791008407912510 if you want to receive ping notifications for private lobby codes during the event. (This is the only role we ping during classic events).\n## Private Classic Mini Prix Schedule - :lock: :MPClassicMini: :calendar_spiral:\n", 
     "announcement_outro": "## Rules - Machine Mastery\n> Pick the machine you think will perform best for each line-up\n> You _MUST_ pick a different machine for each line-up\n\n## Scoring\n> How to submit your score: https://discord.com/channels/1019374132342816800/1206737911161290822/1416205571174039552\n> Submit your scores here: https://discord.com/channels/1019374132342816800/1406063056861007872\n\n### _Machine Mastery_\n## イベント情報 cMP (クラシックミニ)\n> 4つのマシンをすべて使用する必要があります。<:F2PFalcon:1199871007633195098> <:F2PFox:1199871009537392720> <:F2PGoose:1199871012913827870> <:F2PStingray:1199871016353153146>\n> 各クラシックミニに異なるマシンを選んでください。\n> 部屋コードはここで発表されます https://discord.com/channels/1019374132342816800/1185690454658912397\n\nここにスコアを入力してください https://discordapp.com/channels/1019374132342816800/1406063056861007872\nイベントの1時間後に勝者が発表されます。\nYou will need **{0} {1} tickets** for this event."
     },
    {"shortname": "wacky_w", "fullname": "Wacky Wednesday",
     "score_channel": "https://discordapp.com/channels/1019374132342816800/1219953737284587570", 
     "announcement_intro": "<@&1197169889417371689>\n# :tada: Wacky Wednesday starts {0} at {1}! :tada:\nWelcome to the most unpredictable event of the week! Each week, we'll feature a wacky lineup of prix that will challenge even the most seasoned racers. Expect the unexpected and get ready for some wild fun on the track!\n## Schedule\n",
     "announcement_outro": "Reminders will be posted on <#1185690454658912397>\n### **This event requires {0} {1} tickets to see Mute Cities.**"
     },
]

custom_text = [
    {"clean_driving": "\nFor each mWT you complete, you can earn 5,000 points for driving CLEAN. What is driving CLEAN? Driving CLEAN means you have to play without using unconventional strategies to farm points, like holding up a race to get gems.\n\n"}
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
"### /list_autopost_events\n> Lists the events that are currently queued for autoposting.\n\n\
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
### /help\n> Shows this message.\n\nIf you have any questions, suggestions, \
or issues, please contact lurch."
)