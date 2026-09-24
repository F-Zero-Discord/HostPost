'''
Autopost logic
'''
from datetime import UTC, datetime, timedelta
from typing import TypedDict

import discord

from src.data.slot_mapping import Prix
from src.settings import get_settings
from src.utils.build_hostposts import Post
from src.utils.hostpost_utils import round_to_30_minutes


class Autopost(TypedDict):
    """One post as `PostScheduler.schedule_job` queues it."""

    job_name: str
    time: datetime
    text: str
    channel: discord.Object
    pause: bool
    """Scheduled paused, to be resumed by a command: prix results and the final results."""

''' Global Test Variables '''
test_flag = get_settings().test_flag == 1
test_interval = 30 # seconds


def clean_post(post: str) -> str:
    # Helper function to clean the post text by removing code block formatting if present.
    start = post.find("```") + len("```")
    end = post.find("```", start)
    return post[start:end].strip()

def build_autopost_dict(event: str, post_struct: list[Post], prix_info: list[Prix]) -> list[Autopost]:
    # Identify whether we are in test mode or not. If in test mode, all posts will be scheduled to be posted
    # test_interval seconds apart starting from now for testing purposes.
    if test_flag:
        print("Test mode is ON.")

    # Get discord channels where posts will go. Note: test and production channels are toggled directly in the .env file.
    settings = get_settings()
    hour_post_channel = discord.Object(id=int(settings.event_announce_channel))
    other_post_channel = discord.Object(id=int(settings.engage_channel))
    print(f"hour_post_channel: {hour_post_channel}")

    autoposts: list[Autopost] = []
    start_time = prix_info[0]['time']
    job_name_template = f"{start_time.strftime('%Y-%m-%d')} | {event}_"

    # 1 hour post
    autoposts.append(
        {'job_name': f"{job_name_template}1hr",
        'time': start_time - timedelta(minutes=60),
        'text': clean_post(post_struct[0]["post_text"]),
        'channel': hour_post_channel,
        'pause': False
        })

    # 10 minute post
    autoposts.append(
        {'job_name': f"{job_name_template}10min",
        'time': start_time - timedelta(minutes=10),
        'text': clean_post(post_struct[1]["post_text"]),
        'channel': other_post_channel,
        'pause': False
        })

    # Public lobby posts will occur one minute before the prix opens. Private lobby posts will occur at lobby opening.
    post_struct_index = 1
    for index, prix in enumerate(prix_info):
        post_struct_index += 1
        match post_struct[post_struct_index]["post_type"]:
            case "go_post":
                if prix["prix_type"] == "public":
                    autoposts.append(
                        {'job_name': f"{job_name_template}Prix#{index+1}",
                        'time': prix["time"] - timedelta(minutes=1),
                        'text': clean_post(post_struct[post_struct_index]["post_text"]),
                        'channel': other_post_channel,
                        'pause': False
                        })
                else:
                    autoposts.append(
                        {'job_name': f"{job_name_template}Prix#{index+1}",
                        'time': prix["time"] + timedelta(seconds=4),
                        'text': clean_post(post_struct[post_struct_index]["post_text"]),
                        'channel': other_post_channel,
                        'pause': False
                        })
                # Make results_post posts
                post_struct_index += 1
                autoposts.append(
                    {'job_name': f"{job_name_template}Prix#{index+1}Results",
                    'time': prix["time"],
                    'text': clean_post(post_struct[post_struct_index]["post_text"]),
                    'channel': other_post_channel,
                    'pause': True
                    })
            case _:
                raise RuntimeError("Encountered unexpected post_type when building autoposts.")

    # Add autopost for "event_result" post
    autoposts.append(
        {'job_name': f"{job_name_template}FinalResults",
         # round to nearest 30 minutes and subtract 1 minute to get scoreboard close time
        'time': round_to_30_minutes(prix_info[-1]["time"] + timedelta(minutes=60)) - timedelta(minutes=1),
        'text': clean_post(post_struct[-1]["post_text"]),
        'channel': hour_post_channel,
        'pause': True
        })


    if test_flag:
        # Set all post times to be test_interval seconds apart starting from now for testing purposes.
        start_time = datetime.now(UTC)
        for index, post in enumerate(autoposts):
            # Comment the line below out to test using normal timings but no pings
            post['time'] = start_time + timedelta(seconds=test_interval * (index + 1))
            # Replace any @Events pings
            post['text'] =  post['text'].replace('<@&1197169889417371689>', '<events test ping>')
            # Replace any @Classic Events pings
            post['text'] =  post['text'].replace('<@&1343646386981437561>', '<classic test ping>')

    return autoposts

