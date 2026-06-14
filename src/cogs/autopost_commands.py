'''
Module for Class PostScheduler.
- Contains methods for scheduling posts using an APScheduler object.
- Contains slash commands for viewing and cancelling scheduled posts.
'''

import os, time
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.utils.hostpost_utils import discord_timestamp
from src.utils.autoposts_utils import build_autopost_dict, clean_post
from data.event_post_text import access_roles
from src.views.hostpost_views import EditTemplateWizardView
from src.fzd_db import get_db_connection, get_scheduled_event_id, get_event_scores


class PostScheduler(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.scheduler = bot.scheduler
        self.interaction: discord.Interaction | None = None

        load_dotenv()
        self.validation_channel_id = discord.Object(id=int(os.getenv('VALIDATION_CHANNEL'))).id


    ''' Autocomplete methods '''
    async def eventpost_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        autopost_event_list = self.events_job_list(self.scheduler)
        if not autopost_event_list:
            options = ["No events scheduled for autoposting"]
        else:
            options = [autopost_event["event name"] for autopost_event in autopost_event_list if current.lower() in autopost_event["event name"].lower()]

        # Return up to 25 results (25=discord limit)
        return [app_commands.Choice(name=autopost_event, value=f"{autopost_event}") for autopost_event in options[:25]]
    

    async def job_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        job_list = self.scheduler.get_jobs()
        job_name_list = []
        for job in job_list:
            job_name_list.append(job.id)

        if not job_name_list:
            options = ["No paused jobs pending."]
        else:
            options = [job_name for job_name in job_name_list if current.lower() in job_name.lower()]

        # Return up to 25 results (25=discord limit)
        return [app_commands.Choice(name=job, value=f"{job}") for job in options[:25]]


    async def paused_job_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        job_list = self.scheduler.get_jobs()
        job_name_list = []
        for job in job_list:
            if (job.next_run_time == None) and ("FinalResults" not in job.id):
                job_name_list.append(job.id)

        if not job_name_list:
            options = ["No paused jobs pending."]
        else:
            options = [job_name for job_name in job_name_list if current.lower() in job_name.lower()]

        # Return up to 25 results (25=discord limit)
        return [app_commands.Choice(name=job, value=f"{job}") for job in options[:25]]
    ''' ---------------------------------------------- '''


    async def add_user_to_message(
            self, 
            interaction: discord.Interaction, 
            job_name: str, 
            user_string: str
            ):
        
        # Find job_name in job stack
        if any(job.get("job_name") == job_name for job in self.bot.job_stack):
            message = [job["message"] for job in self.bot.job_stack if job["job_name"] == job_name]
            # Replace string "@[Player]" with user mention
            substring = "@[Player]"
            if substring in message[0]:
                new_message = message[0].replace(substring, user_string)
                for job in self.bot.job_stack:
                    if job["job_name"] == job_name:
                        job["message"] = new_message
                # await interaction.response.send_message(f"User {user.name} added to message.")
            else:
                # await interaction.response.send_message(f"Substring {substring} not found in message. Message unchanged.")
                print(f'Warning: "{substring}" not found in message. Message unchanged.')
    

    def events_job_list(self, scheduler: AsyncIOScheduler) -> list[dict]:
        ''' Looks at all the jobs and returns the event names associated with the existing jobs.
        '''
        job_list = scheduler.get_jobs()
        event_list: list[dict] = []
        for job in job_list:
            # Extract event name by removing the last part after the final underscore in the job name. 
            # This relies on the job naming convention used in build_autopost_dict.
            event_name: str = job.id.rsplit("_",1)[0]
            # Don't include the job that calls the user to validate the results
            if "getResults" not in event_name:
                if event_name not in [event["event name"] for event in event_list]:
                    event_list.append({"event name": event_name, "count": 1})
                else:
                    # increment count for event in event_list
                    for event_dict in event_list:
                        if event_name == event_dict["event name"]:
                            event_dict["count"] += 1
        return event_list
    

    def remove_event_jobs(self, event_name: str):
        ''' Removes jobs associated with event "event_name" from both scheduler and 
            self.bot.job_stack.
        '''  
        job_list = self.scheduler.get_jobs()
        for job in job_list:
            if event_name in job.id:
                self.scheduler.remove_job(job.id)
        stack = self.bot.job_stack
        for job in stack:
            if event_name in job["job_name"]:
                self.bot.job_stack = [j for j in self.bot.job_stack if j.get("job_name") != job["job_name"]]



    async def send_and_pop_message(self, channel, job_name, message):
        """Runs entirely on the bot's main async loop."""
        try:
            # 1. Send the message
            await channel.send(message)
            
            # 2. Remove job information from the stack
            self.bot.job_stack = [job for job in self.bot.job_stack if job.get("job_name") != job_name]  
            
        except Exception as e:
            # If error occurs, the item stays in the stack
            print(f"Failed to send scheduled message. Stack preserved. Error: {e}")


    def post_message(self, job_name: str, channel_id: int) -> None:
        ''' The method triggered when an event runs. Pulls the message from the 
            job stack (self.bot.job.stack). This allows for the user to modify the
            message after the job has been queued.
        '''
        channel = self.bot.get_channel(channel_id)

        # Confirm that job "job_name" is in the job stack
        if any(job.get("job_name") == job_name for job in self.bot.job_stack):
            message = [job["message"] for job in self.bot.job_stack if job["job_name"] == job_name]
            asyncio.run_coroutine_threadsafe(
                self.send_and_pop_message(channel, job_name, message[0]),
                self.bot.loop
            )  
        else:
            raise f"Error: job {job_name} is not in the job stack and so cannot be executed."
        

    async def schedule_job(self, post_job: dict) -> None:
        # post_job is a dict with keys 
        # "job_name" (str), 
        # "time" (datetime), 
        # "text" (str), and 
        # "channel" (discord.Object).
        # The act of scheduling is to add the job to the job stack ("self.bot.job_stack"). 
        # The job name and time will be added to the job and the message ("text") will be 
        # added to the job stack to allow for modification later.
        self.bot.job_stack.append({
            "job_name": post_job["job_name"], 
            "message": post_job["text"], 
            "time": post_job["time"]})
         
        self.scheduler.add_job(
            self.post_message,
            #trigger='date',
            id=post_job['job_name'],
            next_run_time=post_job['time'],
            misfire_grace_time=None,
            max_instances=1,
            args=[post_job['job_name'], post_job['channel'].id]
        )
        if post_job['pause'] == True:
            self.scheduler.pause_job(post_job['job_name'])


    async def prepare_results_post(self, 
                                   interaction: discord.Interaction, 
                                   event_name: str, 
                                   job_name: str, 
                                   channel_id: int
                                   ):
        ''' Takes database scores and updates the event results post with the 
            top three scores and the users associated with them. Also provides
            direction to the user to either update the post (/edit_)
        '''
        # Get scores from database
            # Get scheduled_event id from database
        async with get_db_connection(self.bot.db_pool) as db:
            event_id = await get_scheduled_event_id(db, event_name) # returns a dict
            # Get scores from database
        async with get_db_connection(self.bot.db_pool) as db:
            scores_dict = await get_event_scores(db, str(event_id))
        # scores_dict has the keys "name", "user_id", "discord_name", and "score"

        # Edit event_results post with final scores
            # Results placeholder strings are @[first], @[second], and @[third] for the 
            # top level and @(first). @(second), and @(third). Inline points placeholders 
            # are represented by [firstpoints], [secondpoints], and [thirdpoints].
        message = [job["message"] for job in self.bot.job_stack if job["job_name"] == job_name]
        results_message = message[0]
            # Make replacements
            # First Place
        if scores_dict:
            if len(scores_dict) >= 3:
                member = discord.utils.get(interaction.guild.members, name=scores_dict[0]["discord_name"])
                if not member:
                    results_message = results_message.replace("@[first]", scores_dict[0]["name"])
                else:
                    results_message = results_message.replace("@[first]", member.mention)
                results_message = results_message.replace("@(first)", scores_dict[0]["name"])
                results_message = results_message.replace("[firstpoints]", f"{int(scores_dict[0]["score"]):,}")
                
                    # Second Place
                member = discord.utils.get(interaction.guild.members, name=scores_dict[1]["discord_name"])
                if not member:
                    results_message = results_message.replace("@[second]", scores_dict[1]["name"])
                else:
                    results_message = results_message.replace("@[second]", member.mention)
                results_message = results_message.replace("@(second)", scores_dict[1]["name"])
                results_message = results_message.replace("[secondpoints]", f"{int(scores_dict[1]["score"]):,}")
                
                    # Third Place
                member = discord.utils.get(interaction.guild.members, name=scores_dict[2]["discord_name"])
                if not member:
                    results_message = results_message.replace("@[third]", scores_dict[2]["name"])
                else:
                    results_message = results_message.replace("@[third]", member.mention)
                results_message = results_message.replace("@(third)", scores_dict[2]["name"])
                results_message = results_message.replace("[thirdpoints]", f"{int(scores_dict[2]["score"]):,}")

        for job in self.bot.job_stack:
            if job["job_name"] == job_name:
                job["message"] = results_message

        # Post the event_results post in #playground with request to validate
        
        channel = self.bot.get_channel(self.validation_channel_id)
        await channel.send(clean_post(results_message), allowed_mentions=discord.AllowedMentions.none())
        host = None # Enter command to get host's discord.Member.mention here. Blank string until implemented.
        if not host == None:
            ping = host.mention
        else:
            ping = ""
        validation_directions = f"""## {ping} Review the above {event_name} Results post and either\n\
- Approve immediate posting using the `/validate_results` command\n\
- Edit the post using `/edit_pending_autopost` and then validate using `/validate_results`"""
        await channel.send(validation_directions)


    async def post_scheduler(self, 
                             interaction: discord.Interaction, 
                             event: str, 
                             post_struct: list[dict], 
                             prix_info: list[dict]
                             ):
        # Entry point for scheduling autoposts for an event from hostpost_commands.py.
        # Builds the autopost dict and then schedules the posts using the schedule_job method.
        autoposts = build_autopost_dict(event, post_struct, prix_info)
        scoreboard_close_time = autoposts[-1]['time']

        # Check to ensure that the event is not already scheduled.
        job_list = self.scheduler.get_jobs()
        for job in job_list:
            if event in job.id:
                error_text = f"## :bangbang: Posts are already scheduled for event {event}. If you would like to replace those scheduled posts use `/cancel_event_posts` to cancel the existing scheduled event posts first."
                await interaction.followup.send(error_text)
                return

        for index, post in enumerate(autoposts):
            print(f"Scheduling post #{index+1} for {event} named {post['job_name']}")
            await self.schedule_job(post)
        
        # Add job to pull scores from database and edit event results post
        event_name: str = autoposts[-1]['job_name'].rsplit("_",1)[0]
        self.scheduler.add_job(
            self.prepare_results_post,
            id=f"getResults_{event_name}",
            next_run_time=scoreboard_close_time,
            misfire_grace_time=None,
            max_instances=1,
            args=[interaction, event_name, autoposts[-1]['job_name'], autoposts[-1]['channel'].id]
        )


    # Simple testing command, if needed.
    # @app_commands.command(name="test_task", description="Test command for future task-setting.")
    # async def test_task(self, interaction: discord.Interaction):
    #     self.interaction = interaction
    #     next_iteration = datetime.now(timezone.utc) + timedelta(seconds=30)
    #     task_name = "task_1"

    #     self.scheduler.add_job(
    #         self.post_message,
    #         #trigger='date',
    #         id=task_name,
    #         next_run_time=next_iteration,
    #         max_instances=1,
    #         args=[f"This is a scheduled message for {interaction.user.mention}!", self.post_channel]
    #     )

    #     #self.scheduler.start()
    #     await interaction.response.send_message("Task Scheduled. (maybe???)")

    #-------------------------------------------------
    # Begin slash commands
    #-------------------------------------------------
    @app_commands.command(name="list_all_autoposts", description="Provides list of scheduled tasks.")
    @discord.app_commands.checks.has_any_role(*access_roles)
    async def list_all_autoposts(self, interaction: discord.Interaction):
        self.interaction = interaction
        self.scheduler.print_jobs()
        job_list = self.scheduler.get_jobs()
        if not job_list:
            output_text = "No autoposts scheduled."
        else:
            output_text = "Current scheduled posts:\n"
            for job in job_list:
                if job.next_run_time == None:
                    output_text += f"{job.id}: paused\n"
                else:
                    output_text += f"{job.id}: Scheduled for {discord_timestamp(job.next_run_time, "short")}\n"
        await interaction.response.send_message(output_text)


    @app_commands.command(name="cancel_all_posts", description="Test command for cancelling existing scheduled tasks.")
    @discord.app_commands.checks.has_any_role(*access_roles)
    async def cancel_all_posts(self, interaction: discord.Interaction):
        self.interaction = interaction
        self.scheduler.remove_all_jobs()
        await interaction.response.send_message("All tasks cancelled.")


    @app_commands.command(name="list_autopost_events", description="Test command for seeing existing scheduled events (grouped by event name).")
    @discord.app_commands.checks.has_any_role(*access_roles)
    async def list_autopost_events(self, interaction: discord.Interaction):
        self.interaction = interaction
        event_list = self.events_job_list(self.scheduler)
        if not event_list:
            output_text = "No events are currently scheduled for automatic posting."
        else:
            output_text = "Currently scheduled events:\n"
            for event in event_list:
                output_text += f"\t{event['event name']}: {event['count']} scheduled { 'post' if event['count'] == 1 else 'posts' }\n"
        await interaction.response.send_message(output_text)


    @app_commands.command(name="cancel_event_posts", description="Cancelling existing scheduled tasks for a given event.")
    @discord.app_commands.checks.has_any_role(*access_roles)
    async def cancel_event_posts(self, interaction: discord.Interaction, event_name: str):
        self.interaction = interaction
        job_list = self.scheduler.get_jobs()
        if not job_list:
            await interaction.response.send_message("No scheduled events exist. No action taken.")
        else:
            self.remove_event_jobs(event_name)
            await interaction.response.send_message(f"All scheduled posts for event {event_name} cancelled.")

    @app_commands.command(name="post_prix_winner", description="Select user who won prix and post result.")
    @discord.app_commands.checks.has_any_role(*access_roles)
    async def post_prix_winner(
        self, 
        interaction: discord.Interaction, 
        job_name: str, 
        winner_1: discord.Member | None = None,
        winner_2: discord.Member | None = None,
        winner_string: str | None = None
        ):
        ''' Accept one or more winners (two can be mentions, the third would be a string) and add them to
            the prix results post. All three winner parameters are optional, as the winner may be a 
            discord.Member mention or a plain old string.
        '''
        # Given that all three user parameters are optional, check to ensure at least one has data.
        if (not winner_1) and (not winner_2) and (not winner_string):
            await interaction.response.send_message(
                f"You must submit one of the optional winner parameters. No action taken", 
                ephemeral=True
                )
            return
        else:
            winner_concat = str()
            if winner_1:
                winner_concat += f"{winner_1.mention}"
                if winner_2:
                    winner_concat += f" and {winner_2.mention}"
                if winner_string:
                    winner_concat += f" and {winner_string}"
            elif winner_2:
                winner_concat += f"{winner_2.mention}"
                if winner_string:
                    winner_concat += f" and {winner_string}"
            else:
                winner_concat += f"{winner_string}"
            await self.add_user_to_message(interaction, job_name, winner_concat)
            self.scheduler.resume_job(job_name)
            await interaction.response.send_message(f"We have a winner!")


    @app_commands.command(name="edit_pending_autopost", description="Edit an event post.")
    @discord.app_commands.checks.has_any_role(*access_roles)
    async def edit_pending_autopost(self, interaction:discord.Interaction, job_name: str):
        # Get editor popup....
        message = [job["message"] for job in self.bot.job_stack if job["job_name"] == job_name]
        # Need to create a short version of the job name due to character limits in modal
        short_jobname = job_name.rsplit("_",1)[1]
        # Note template wizard view input requires list[dict]
        view = EditTemplateWizardView([{"name": short_jobname, "post_text": message[0], "post_type": ""}])
        next_template = message[0]
        view.edit_button.label = f"Edit Post"
        status_msg = f"## Modify {job_name} Message?"
        await interaction.response.send_message(content=status_msg, view=view)
        await view.wait()

        # Replace message in self.bot.job_stack with edited message
        for job in self.bot.job_stack:
            if job["job_name"] == job_name:
                job["message"] = view.drafts[0]["post_text"]
        await interaction.followup.send(content=f"{job_name} message updated.")


    @app_commands.command(name="validate_results", description="Validate an event's final results.")
    @discord.app_commands.checks.has_any_role(*access_roles)
    async def validate_results(self, interaction:discord.Interaction, event_name: str):
        job_list = self.scheduler.get_jobs()
        for job in job_list:
            if (event_name in job.id) and ("FinalResults" in job.id):
                self.scheduler.resume_job(job.id)
                # remove all jobs associated with the event from bot the scheduler and the job_stack
                await asyncio.sleep(1) # sleep to ensure results post made before job removed.
                self.remove_event_jobs(event_name)
                await interaction.response.send_message(f"Results posted. {event_name} has concluded.")
            

    @app_commands.command(name="push_job", description="Push a job. Mostly for testing.")
    @discord.app_commands.checks.has_any_role(*access_roles)
    async def push_job(self, interaction:discord.Interaction, job_name: str):
        job = self.scheduler.get_job(job_name)
        if job.next_run_time == None:
            self.scheduler.resume_job(job_name)
        else:
            # if job not paused, pause to clear out the trigger and trigger immediately with resume_job
            self.scheduler.pause_job(job_name)
            self.scheduler.resume_job(job_name)
        # Remove job information from the stack
        await asyncio.sleep(2) # sleep to ensure post made before job removed.
        self.bot.job_stack = [job for job in self.bot.job_stack if job.get("job_name") != job_name] 
        await interaction.response.send_message(f"{job_name} pushed.")


    # Error handling for if user does not have appropriate role
    @list_all_autoposts.error
    @cancel_all_posts.error
    @list_autopost_events.error
    @cancel_event_posts.error
    @post_prix_winner.error
    @edit_pending_autopost.error
    @validate_results.error
    @push_job.error
    async def role_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingAnyRole):
            await interaction.response.send_message(
                "This command is Circuit Crew only. Hit up a mod if you want to join Circuit Crew.",
                ephemeral=True
                )
        else: raise error

    async def cog_load(self):
            self.cancel_event_posts.autocomplete("event_name")(self.eventpost_autocomplete)
            self.post_prix_winner.autocomplete("job_name")(self.paused_job_autocomplete)
            self.edit_pending_autopost.autocomplete("job_name")(self.job_autocomplete)
            self.validate_results.autocomplete("event_name")(self.eventpost_autocomplete)
            self.push_job.autocomplete("job_name")(self.job_autocomplete)

async def setup(bot: commands.Bot):
    GUILD_ID=discord.Object(id=os.getenv('SERVER_ID'))
    await bot.add_cog(PostScheduler(bot), guild=GUILD_ID)