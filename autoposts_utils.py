'''
Autopost logic
'''
import os
import re
import discord
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
from build_hostposts import round_to_30_minutes


''' Global Test Variables '''
load_dotenv()
TEST_FLAG = os.getenv('TEST_FLAG')
if TEST_FLAG == '1':
    test_flag = True
else:
    test_flag = False
test_interval = 30 # seconds


def clean_post(post: str) -> str:
    # Helper function to clean the post text by removing code block formatting if present.
    start = post.find("```") + len("```")
    end = post.find("```", start)
    return post[start:end].strip()

def insert_new_message_contents(post:str, new_content: str) -> str:
    if post.count("```") > 2:
        print("Backtick blocks (```) are not allowed within posts/.")
        return
    else:
        start_str = r"\```"
        end_str = r"\```"
        pattern = f"(?<={start_str}).*?(?={end_str})"
        return re.sub(pattern, new_content, post)


def build_autopost_dict(event: str, post_struct: list[dict], prix_info: list[dict]) -> list[dict]:
    # 
    # prix_info is a list of dicts with keys "prix" (str), "time" (datetime), and "prix_type" ("public"/"private").
    
    # Identify whether we are in test mode or not. If in test mode, all posts will be scheduled to be posted 
    # test_interval seconds apart starting from now for testing purposes.
    if test_flag:
        print("Test mode is ON.")

    # Get discord channels where posts will go. Note: test and production channels are toggled directly in the .env file.
    load_dotenv()
    hour_post_channel = discord.Object(id=os.getenv('ANNOUNCE_CHANNEL'))
    other_post_channel = discord.Object(id=os.getenv('ENGAGE_CHANNEL'))

    autoposts: list[dict] = []
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
                raise "Encountered unexpected post_type when building autoposts."
            
    # Add autopost for "event_result" post
    autoposts.append(
        {'job_name': f"{job_name_template}FinalResults",
         # round to nearest 30 minutes and subtract 1 minute to get scoreboard close time
        'time': round_to_30_minutes(prix["time"] + timedelta(minutes=60)) - timedelta(minutes=1),
        'text': clean_post(post_struct[-1]["post_text"]),
        'channel': hour_post_channel,
        'pause': True
        })
            

    if test_flag:
        # Set all post times to be test_interval seconds apart starting from now for testing purposes.
        start_time = datetime.now(timezone.utc)
        for index, post in enumerate(autoposts):
            post['time'] = start_time + timedelta(seconds=test_interval * (index + 1))
    return autoposts

