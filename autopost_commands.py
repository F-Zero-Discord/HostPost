import os
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from autoposts_utils import build_autopost_dict
from event_post_text import access_roles


class PostScheduler(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.scheduler = bot.scheduler
        self.interaction: discord.Interaction | None = None
        self.post_channel = [] # Channel Id for test command. Takes integer.

    ''' Autocomplete methods '''
    async def eventpost_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        autopost_event_list = self.events_job_list(self.scheduler)
        if not autopost_event_list:
            options = ["No events scheduled for autoposting"]
        else:
            options = [autopost_event["event name"] for autopost_event in autopost_event_list if current.lower() in autopost_event["event name"].lower()]

        # Return up to 25 results (25=discord limit)
        return [app_commands.Choice(name=autopost_event, value=f"{autopost_event}") for autopost_event in options[:25]]
    ''' ---------------------------------------------- '''

    def events_job_list(self, scheduler: AsyncIOScheduler) -> list[dict]:
        job_list = scheduler.get_jobs()
        event_list: list[dict] = []
        for job in job_list:
            # Extract event name by removing the last part after the final underscore in the job name. 
            # This relies on the job naming convention used in build_autopost_dict.
            event_name: str = job.id.rsplit("_",1)[0]
            if event_name not in [event["event name"] for event in event_list]:
                event_list.append({"event name": event_name, "count": 1})
            else:
                # increment count for event in event_list
                for event_dict in event_list:
                    if event_name == event_dict["event name"]:
                        event_dict["count"] += 1
        return event_list


    def post_message(self, text: str, channel_id: int) -> None:
        print(f"self.interaction: {self.interaction}, channel_id: {channel_id}")
        #if self.interaction:
        channel = self.bot.get_channel(channel_id)
        asyncio.run_coroutine_threadsafe(
            channel.send(text), 
            self.bot.loop
        )

    async def schedule_job(self, post_job: dict) -> None:
        # post_job is a dict with keys "job_name" (str), "time" (datetime), "text" (str), and "channel" (discord.Object).

        self.scheduler.add_job(
            self.post_message,
            #trigger='date',
            id=post_job['job_name'],
            next_run_time=post_job['time'],
            max_instances=1,
            args=[post_job['text'], post_job['channel'].id]
        )

        print(f"Channel: {post_job['channel'].id}")

    async def post_scheduler(self, event: str, hour_post: list[str], go_posts: list[str], prix_info: list[dict]):
        # Entry point for scheduling autoposts for an event from hostpost_commands.py. 
        # Builds the autopost dict and then schedules the posts using the schedule_job method.
        autoposts = build_autopost_dict(event, hour_post, go_posts, prix_info)
        for index, post in enumerate(autoposts):
            print(f"Scheduling post #{index+1} for {event} named {post['job_name']}")
            await self.schedule_job(post)


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


    @app_commands.command(name="list_all_autoposts", description="Test command for seeing existing scheduled tasks.")
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
                output_text += f"{job.id}: Scheduled for {job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")} (UTC)\n"
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


    @app_commands.command(name="cancel_event_posts", description="Test command for cancelling existing scheduled tasks for a given event.")
    @discord.app_commands.checks.has_any_role(*access_roles)
    async def cancel_event_posts(self, interaction: discord.Interaction, event_name: str):
        self.interaction = interaction
        job_list = self.scheduler.get_jobs()
        for job in job_list:
            if job.id.startswith(event_name):
                self.scheduler.remove_job(job.id)
                print(f"Cancelled job {job.id} for event {event_name}.")
        if not job_list:
            await interaction.response.send_message("No scheduled events exist. No action taken.")
        else:
            await interaction.response.send_message(f"All scheduled posts for event {event_name} cancelled.")

    @list_all_autoposts.error
    @cancel_all_posts.error
    @list_autopost_events.error
    @cancel_event_posts.error
    async def role_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingAnyRole):
            await interaction.response.send_message(
                "This command is Circuit Crew only. Hit up a mod if you want to join Circuit Crew.",
                ephemeral=True
                )
        else: raise error

    async def cog_load(self):
            self.cancel_event_posts.autocomplete("event_name")(self.eventpost_autocomplete)

async def setup(bot: commands.Bot):
    GUILD_ID=discord.Object(id=os.getenv('SERVER_ID'))
    await bot.add_cog(PostScheduler(bot), guild=GUILD_ID)