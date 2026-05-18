import io
import discord
from discord.ext import commands
from datetime import datetime
from hostpost_views import EditTemplateWizardView
from autopost_commands import PostScheduler
from autoposts_utils import clean_post, insert_new_message_contents
from event_post_text import automatable_posts


''' Output for Draft Posts '''
async def post_draft_posts_to_discord(
    interaction: discord.Interaction, 
    # hour_post: list[str], 
    # go_posts: list[str], 
    # results_posts: list[str], 
    # event_results_post: list[str],
    post_struct: list[dict]
    ):
    # # Send hour posts
    # await interaction.followup.send(hour_post[0], ephemeral=False)
    # if len(go_posts) == len(results_posts):
    #     # interlace posts
    #     for index, post in enumerate(go_posts):
    #         await interaction.followup.send(post, ephemeral=False)
    #         await interaction.followup.send(results_posts[index], ephemeral=False)
    # else:
    #     raise Exception(
    #         f"Internal error: lists of prix initiation (length = {len(go_posts)}) and results posts (length = {len(results_posts)})are different lengths."
    #         )
    # await interaction.followup.send(event_results_post[0], ephemeral=False)
    for post in post_struct:
        await interaction.followup.send(post["post_text"], ephemeral=False)

async def post_post_textfile(
    interaction: discord.Interaction, 
    event: str, 
    event_start_time: datetime, 
    # hour_post: list[str], 
    # go_posts: list[str], 
    # results_posts: list[str], 
    # event_results_post: list[str]
    post_struct: list[dict]
    ):
    # Create the large string object for writing to file.
    # post_text = hour_post[0] + "\n\n"
    # for index, post in enumerate(go_posts):
    #     post_text += post + "\n\n"
    #     post_text += results_posts[index] + "\n\n"
    # post_text += event_results_post[0]
    post_text = ""
    for index, post in enumerate(post_struct):
        post_text += post["post_text"]
        if index != len(post_struct):
            post_text += "\n\n"
    
    ''' Write to text file '''
    filename = event + "_" + event_start_time.strftime("%Y-%m-%d %H:%M:%S") + "_posts.txt"
    # Convert text into a byte stream
    buffer = io.BytesIO(post_text.encode('utf-8'))
    # Send it directly
    await interaction.followup.send(
        f"Posts written to attached file {filename} for your records.", 
        file=discord.File(fp=buffer, filename=filename)
        )


async def edit_posts(interaction: discord.Interaction, post_struct: list[dict]) -> list[dict]:
    # post_struct schema:
    #   name: str
    #   post_text: str
    #   post_type: str enum("1hr", "10min", "go_post", "results_post", "event_results")

    drafts = []
    for post in post_struct:
        # Allow for editing of the 1hr and 10min posts priot to scheduling
        if (post["post_type"] in automatable_posts) and (post["post_type"] != "go_post"):
            drafts.append(post)

    view = EditTemplateWizardView(drafts)
    next_template = drafts[0]
    view.edit_button.label = f"Edit: {next_template['name']}"

    status_msg = f"## Customize your post? (1/{len(drafts)})\n" \
                f"Click the button below to review/modify the **{next_template['name']}** template post language."

    # 3. Send the initial message with the view attached
    await interaction.followup.send(content=status_msg, view=view)

    # 4. (Optional) Wait for the wizard to complete before moving on to your scheduling logic
    await view.wait()

    # Assign the updated message text to the post_struct
    for draft in view.drafts:
        for post in post_struct:
            if draft["name"] == post["name"]:
                post["post_text"] = draft["post_text"]
    return post_struct



async def prepare_post_outputs(
    bot: commands.Bot,
    interaction: discord.Interaction,
    event: str,
    post_struct: list[dict],
    event_prix_info: list[dict],
    autopost: bool 
    ) -> None:
    event_start_time = event_prix_info[0]["time"]
    print(f"The user selected autopost?: {autopost}.")

    if autopost:
        # Run the scheduler module.
        #   v1 only posts hour_post and go_posts
        #   v2 allows user interaction on results posts through slash commands.
        # We are currently in v1.
        post_struct = await edit_posts(interaction, post_struct)
        ps = PostScheduler(bot)
        await ps.post_scheduler(interaction, event, post_struct, event_prix_info)

    # To the interaction channel as separate posts
    await post_draft_posts_to_discord(interaction, post_struct)
    # To the interaction channel as a text file
    await post_post_textfile(interaction, event, event_start_time, post_struct)