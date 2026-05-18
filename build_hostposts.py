'''
Functions in this module take the following to build posts for regular weekly events:
- Event name (e.g. "Friday FZD EU")
- List of dicts containing prix info (e.g. [{"prix": "knight", "time": datetime, "prix_type": "public"}, ...])


'''
import random
from datetime import datetime, timedelta
from hostpost_utils import discord_timestamp, round_to_30_minutes
from event_post_text import prix_info, schedule_line, events
# from pengbot_addons import event_post_text

def build_posts(event_name: str, prix_list: list[dict[str, any]]):
    # Format of event_dict:
    #   [
    #   {gp_name: value (str)
    #   gp_time: value (datetime)
    #   prix_type: value (str, e.g. "public" or "private")}
    #   ...
    #   ]

    # Get number of tickets needed (sure there is a list comprehension for this but too much brainpower)
    tickets_needed = 0
    for prix in prix_list:
        if prix["prix_type"] == "public":
            tickets_needed += next((item for item in prix_info if item["shortname"] == prix["prix"]), None)["tickets"]
    print(f"Tickets needed for {event_name}: {tickets_needed}")

    # Get event info dictionary associated with event_name
    event_info = next((item for item in events if item["fullname"] == event_name), None)

    # Build 1hr post
    hour_post = ""
    hour_post += event_info.get("announcement_intro").format(
        discord_timestamp(prix_list[0]["time"], "relative"), discord_timestamp(prix_list[0]["time"], "short"))
    hour_post += build_schedule(prix_list)
    hour_post += event_info.get("announcement_outro").format(
        ":Ticket:" if tickets_needed == 1 else ":Tickets:", tickets_needed)
    
    # Note: passing this as a string for current testing purposes. Will ultimately return a list of strings, with 
    # each string being a post.
    hour_post = f"One Hour Post```{hour_post}```"
    
    # Build prix-start and prix-results posts
    go_posts, results_posts = build_gp_posts(event_name, prix_list)

    # Build event results post
    event_results_post = f"""
    Results Post```# {event_name.upper()} \
RESULTS ARE IN!\nAnd three pilots emerge victorious:\n\
## :trophy: 1st Place – @[first]: [firstpoints] Points\n\
## :second_place: 2nd Place – @[second]: [secondpoints] Points\n\
## :third_place: 3rd Place – @[third]: [thirdpoints] Points\n\
Congratulations to @(first), @(second), and @(third) for their \
performances in a rough set of prix, and thank you \
to everyone who participated!```"""
    
    # Build post structure
    post_struct = []
    post_struct.append({
        "name": "1 Hour Post",
        "post_text": hour_post,
        "post_type": "1hr"
    })
    # Replace hour post header withe 10 min post header
    header_index = hour_post.find('`')
    if header_index != 1:
        ten_min_post = "10 Minute Post" + hour_post[header_index:]
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

def build_schedule(prix_list: list[dict[str, any]]) -> str:
    # Build the multi-line schedule text for the event post based on the prix list and the schedule_line templates.
    schedule_text = ""
    for prix in prix_list:
        prix_dict = next((item for item in prix_info if item["shortname"] == prix["prix"]), None)
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


def build_gp_posts(event_name: str, prix_list: list[dict[str, any]]) -> list[str]:
    # Build the posts that will be posted at the start and end of each GP. This will be 
    # based on the prix type and the prix info.
    go_posts = []
    results_posts = []
    for index, prix in enumerate(prix_list):
        prix_dict = next((item for item in prix_info if item["shortname"] == prix["prix"]), None)
        score_channel = next((item for item in events if item["fullname"] == event_name), None)["score_channel"]
        
        # Determine ticket text based on number of tickets needed for the prix.
        if prix_dict['tickets'] == 1:
            ticket_text = ":Ticket:"
        else:
            ticket_text = ":Tickets:"
        
        # Determine role called based on mode ("99" or "classic")
        if prix_dict["mode"] == "classic":
            role_ping = "<@&1343646386981437561>" # "@Classic Events" role
        else:
            role_ping = "<@&1197169889417371689>" # "@Events" role 

        # Build prix start post
        match prix["prix_type"]:
            case "public":
                # Build the post using the prix_dict info and the event_name. This is where we would also include any special instructions for certain prix types (e.g. "Be sure to join immediately when the lobby opens for Cracked Cup!")
                go_posts.append(f"Prix #{prix_list.index(prix) + 1}```{role_ping}\n# {event_name} {ticket_text} Public {prix_dict['emoji']} {prix_dict['mirror_emoji']} {prix_dict['fullname']} starts SOON, {discord_timestamp(prix['time'], 'relative')}! :READY: :GO:\n## Join as soon as the prix opens!```")
            case "private":
                # Build the post using the prix_dict info and the event_name. This is where we would also include any special instructions for certain prix types.
                go_posts.append(f"Prix #{prix_list.index(prix) + 1}```{role_ping}\n# {event_name} :Private: Private {prix_dict['emoji']} {prix_dict['mirror_emoji']} {prix_dict['fullname']} starts NOW! :GO:\n## :Private: Passcode: {str(random.randint(0,9999)).zfill(4)} :Private:```")
        # Build score-recording string differently for last prix in event
        if prix_list.index(prix) + 1 == len(prix_list):
            # round to nearest 30 minutes and subtract 1 minute to get scoreboard close time
            scoreboard_close_time = round_to_30_minutes(prix["time"] + timedelta(minutes=60)) - timedelta(minutes=1)
            scoring_text = f"That marks the end of {event_name}!\n\nScoreboard closes {discord_timestamp(scoreboard_close_time, 'relative')}, at {discord_timestamp(scoreboard_close_time, 'short')}, so quickly go to {score_channel} to submit your scores!```"
        else:
            next_prix_dict = next((item for item in prix_info if item["shortname"] == prix_list[prix_list.index(prix) + 1]["prix"]), None)
            scoring_text = f"Head over to {score_channel} to submit your scores!\nThe {prix_list[prix_list.index(prix) + 1]['prix_type'].capitalize()} {next_prix_dict['emoji']} {next_prix_dict['mirror_emoji']} {next_prix_dict['fullname']} will start {discord_timestamp(prix_list[prix_list.index(prix) + 1]['time'], 'relative')}!```"
        results_posts.append(f"Prix #{prix_list.index(prix) + 1} Results```# :1st: Congratulations @[Player] for winning the {prix['prix_type'].capitalize()} {prix_dict['emoji']} {prix_dict['mirror_emoji']} {prix_dict['fullname']}!\n{scoring_text}")
    return go_posts, results_posts