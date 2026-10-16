'''
Builds the posts for a regular weekly event from its name and its `Prix` list
(see `data/slot_mapping.py`, which builds that from the API's slots).
'''
import random
from datetime import timedelta
from typing import TypedDict

from src.data.event_post_text import (
    PrixInfo,
    clean_driving_list,
    custom_text,
    prix_info,
    racetrack_channel,
    schedule_line,
    scoreboard_channel,
)
from src.data.slot_mapping import Prix
from src.data.template_mapping import TemplateMap
from src.fzd_db import get_db_connection, get_event_host_id, get_post_template
from src.main import HostBot
from src.utils.hostpost_utils import discord_timestamp, round_to_30_minutes


class Post(TypedDict):
    """One draft, `"<header>```<body>```"`; the fenced body is what is posted."""

    name: str
    post_text: str
    post_type: str
    """`1hr`, `10min`, `go_post`, `results_post` or `event_results`; the scheduler keys on it."""


def prix_template(shortname: str) -> PrixInfo:
    return next(item for item in prix_info if item["shortname"] == shortname)


async def build_posts(bot: HostBot, event_name: str,
                      scheduled_event_id: int,
                      prix_list: list[Prix]) -> list[Post]:
    # Create mapping for event
    map = TemplateMap()

    # Get number of tickets needed (sure there is a list comprehension for this but too much brainpower)
    tickets_needed = 0
    for prix in prix_list:
        if prix["prix_type"] == "public":
            tickets_needed += prix_template(prix["prix"])["tickets"]
    print(f"Tickets needed for {event_name}: {tickets_needed}")

    # Check for need for clean driving message
    if any(prix["prix"] in clean_driving_list for prix in prix_list):
        map.custom_text = next(item["clean_driving"] for item in custom_text)

    # Build string mapping
    map.event_name = event_name
    map.schedule = build_schedule(prix_list)
    map.start_time_short = discord_timestamp(prix_list[0]["time"], "short")
    map.start_time_relative = discord_timestamp(prix_list[0]["time"], "relative")
    map.tickets_number = tickets_needed
    if tickets_needed == 1:
        map.tickets_emoji = "<:Ticket:1194747589610967131>"
        map.tickets_word = "ticket"
    else:
        map.tickets_emoji = "<:Tickets:1218943498338697256>"
        map.tickets_word = "tickets"

    # Build 1hr, 10 min, and Results posts
    async with get_db_connection(bot.db_pool) as db:
        host_id = await get_event_host_id(db, scheduled_event_id)
        # custom_message = await check_for_custom_message(db, event_name, post_type, host_id)
        hour_template =  await get_post_template(db, event_name, "one_hour", host_id)
        ten_min_template =  await get_post_template(db, event_name, "ten_minute", host_id)
        event_results_template = await get_post_template(db, event_name, "event_results", host_id)
    hour_post = rf"One Hour Post```{hour_template.format(**map.mapping).replace(r"\n", "\n")}```"
    ten_min_post = rf"10 Minute Post```{ten_min_template.format(**map.mapping).replace(r"\n", "\n")}```"
    event_results_post = rf"Results Post```{event_results_template.format(**map.mapping).replace(r"\n", "\n")}```"

    # Build prix-start and prix-results posts
    go_posts, results_posts = build_gp_posts(event_name, prix_list)

    # Build post structure
    post_struct: list[Post] = []
    post_struct.append({
        "name": "1 Hour Post",
        "post_text": hour_post,
        "post_type": "1hr"
    })
    # # Replace hour post header withe 10 min post header
    # header_index = hour_post.find('`')
    # if header_index != 1:
    #     ten_min_post = "10 Minute Post" + hour_post[header_index:]
    post_struct.append({
        "name": "10 Minute Post",
        "post_text": ten_min_post,
        "post_type": "10min"
    })
    for index, post in enumerate(go_posts):
        post_struct.append({
            "name": f"Prix #{index+1} Post",
            "post_text": post,
            "post_type": "go_post"
        })
        post_struct.append({
            "name": f"Prix #{index+1} Results",
            "post_text": results_posts[index],
            "post_type": "results_post"
        })
    post_struct.append({
        "name": "Event Results Post",
        "post_text": event_results_post,
        "post_type": "event_results"
    })

    # return [hour_post], go_posts, results_posts, [event_results_post]
    return post_struct

def build_schedule(prix_list: list[Prix]) -> str:
    # Build the multi-line schedule text for the event post based on the prix list and the schedule_line templates.
    schedule_text = ""
    for prix in prix_list:
        prix_dict = prix_template(prix["prix"])
        if prix["lineup"]:
            schedule_text += schedule_line["private_mp_lineup"].format(
                    discord_timestamp(prix["time"], "short"), prix["lineup"][0].upper(), prix["lineup"][1].upper(), prix["lineup"][2].upper())
        else:
            match prix["prix_type"]:
                case "public":
                    # Note we'll need to make a less clean option if any prix requires tickets in increments other than 0, 1, or 3. But for now this should work fine.
                    match prix_dict["tickets"]:
                        case 3:
                            schedule_text += schedule_line["public_multi_tickets"].format(
                                discord_timestamp(prix["time"], "short"), prix_dict["emoji"], prix_dict["mirror_emoji"], prix_dict["fullname"])
                        case 1:
                            schedule_text += schedule_line["public_one_ticket"].format(
                                discord_timestamp(prix["time"], "short"), prix_dict["emoji"], prix_dict["mirror_emoji"], prix_dict["fullname"])
                        case 0:
                            schedule_text += schedule_line["public_no_tickets"].format(
                                discord_timestamp(prix["time"], "short"), prix_dict["emoji"], prix_dict["mirror_emoji"], prix_dict["fullname"])
                case "private":
                    schedule_text += schedule_line["private"].format(
                        discord_timestamp(prix["time"], "short"), prix_dict["emoji"], prix_dict["mirror_emoji"], prix_dict["fullname"])
    return schedule_text


def build_gp_posts(event_name: str, prix_list: list[Prix]) -> tuple[list[str], list[str]]:
    # Build the posts that will be posted at the start and end of each GP. This will be
    # based on the prix type and the prix info.
    go_posts = []
    results_posts = []
    for prix in prix_list:
        prix_dict = prix_template(prix["prix"])

        # Determine ticket text based on number of tickets needed for the prix.
        ticket_text = "<:Ticket:1194747589610967131>" if prix_dict["tickets"] == 1 else "<:Tickets:1218943498338697256>"

        # Determine role called based on mode ("99" or "classic")
        # "@Classic Events" for a classic prix, "@Events" for the rest.
        role_ping = "<@&1343646386981437561>" if prix_dict["mode"] == "classic" else "<@&1197169889417371689>"

        # Build prix start post
        if prix["lineup"]:
            go_posts.append(f"Prix #{prix_list.index(prix) + 1}```{role_ping}\n# {event_name} <:Private:1227046530721251479> Private {prix_dict['emoji']} {prix_dict['mirror_emoji']} {prix_dict['fullname']} starts NOW! <:GO:1226991337723662497>\n## {prix['lineup'][0].upper()} > {prix['lineup'][1].upper()} > {prix['lineup'][2].upper()}\n## <:Private:1227046530721251479> Passcode: {str(random.randint(0,9999)).zfill(4)} <:Private:1227046530721251479>```")
        else:
            match prix["prix_type"]:
                case "public":
                    # Build the post using the prix_dict info and the event_name. This is where we would also include any special instructions for certain prix types (e.g. "Be sure to join immediately when the lobby opens for Cracked Cup!")
                    go_posts.append(f"Prix #{prix_list.index(prix) + 1}```{role_ping}\n# {event_name} {ticket_text} Public {prix_dict['emoji']} {prix_dict['mirror_emoji']} {prix_dict['fullname']} starts SOON, {discord_timestamp(prix['time'], 'relative')}! <:READY:1226990432454578277> <:GO:1226991337723662497>\n## Join as soon as the prix opens!```")
                case "private":
                    # Build the post using the prix_dict info and the event_name. This is where we would also include any special instructions for certain prix types.
                    go_posts.append(f"Prix #{prix_list.index(prix) + 1}```{role_ping}\n# {event_name} <:Private:1227046530721251479> Private {prix_dict['emoji']} {prix_dict['mirror_emoji']} {prix_dict['fullname']} starts NOW! <:GO:1226991337723662497>\n## <:Private:1227046530721251479> Passcode: {str(random.randint(0,9999)).zfill(4)} <:Private:1227046530721251479>```")
            # Build score-recording string differently for last prix in event
        if prix_list.index(prix) + 1 == len(prix_list):
            # round to nearest 30 minutes and subtract 1 minute to get scoreboard close time
            scoreboard_close_time = round_to_30_minutes(prix["time"] + timedelta(minutes=60)) - timedelta(minutes=1)
            scoring_text = f"That marks the end of {event_name}!\n\nScoreboard closes {discord_timestamp(scoreboard_close_time, 'relative')}, at {discord_timestamp(scoreboard_close_time, 'short')}, so quickly submit your scores with the command `/submit` directly here in {racetrack_channel}! If you want to see the current standings, head over to {scoreboard_channel}.```"
        else:
            next_prix_dict = prix_template(prix_list[prix_list.index(prix) + 1]["prix"])
            scoring_text = f"To submit your scores, use the command `/submit` directly here in {racetrack_channel}. If you want to see the current standings, head over to {scoreboard_channel}.\nThe {prix_list[prix_list.index(prix) + 1]['prix_type'].capitalize()} {next_prix_dict['emoji']} {next_prix_dict['mirror_emoji']} {next_prix_dict['fullname']} will start {discord_timestamp(prix_list[prix_list.index(prix) + 1]['time'], 'relative')}!```"
        results_posts.append(f"Prix #{prix_list.index(prix) + 1} Results```# <:1st:1201576405339754546> Congratulations @[Player] for winning the {prix['prix_type'].capitalize()} {prix_dict['emoji']} {prix_dict['mirror_emoji']} {prix_dict['fullname']}!\n{scoring_text}")
    return go_posts, results_posts
