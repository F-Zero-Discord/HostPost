'''
Autopost logic
'''
import os
import discord
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta


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


def build_autopost_dict(event: str, hour_post: list[str], go_posts: list[str], prix_info: list[dict]) -> list[dict]:
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
    job_name_template = f"{event.replace(' ', '_')}_{start_time.strftime('%Y-%m-%d')}_"
    # 1 hour post
    autoposts.append(
        {'job_name': f"{job_name_template}1hr",
        'time': start_time - timedelta(minutes=60),
        'text': clean_post(hour_post[0]),
        'channel': hour_post_channel
        })

    # 10 minute post
    autoposts.append(
        {'job_name': f"{job_name_template}10min",
        'time': start_time - timedelta(minutes=10),
        'text': clean_post(hour_post[0]),
        'channel': other_post_channel
        })

    # Public lobby posts will occur one minute before the prix opens. Private lobby posts will occur at lobby opening.
    for index, prix in enumerate(prix_info):
        if prix["prix_type"] == "public":
            autoposts.append(
                {'job_name': f"{job_name_template}Prix#{index+1}",
                'time': prix["time"] - timedelta(minutes=1),
                'text': clean_post(go_posts[index]),
                'channel': other_post_channel
                })
        else:
            autoposts.append(
                {'job_name': f"{job_name_template}Prix#{index+1}",
                 'time': prix["time"] + timedelta(seconds=4),
                'text': clean_post(go_posts[index]),
                'channel': other_post_channel
                })

    if test_flag:
        # Set all post times to be test_interval seconds apart starting from now for testing purposes.
        start_time = datetime.now(timezone.utc)
        for index, post in enumerate(autoposts):
            post['time'] = start_time + timedelta(seconds=test_interval * (index + 1))
    return autoposts

