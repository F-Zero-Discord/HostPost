"""
Contains slash commands and associated views to allow users to view which events are hosted and 
sign up for events.
"""
from datetime import datetime, UTC
import discord
from discord import app_commands
from discord.ext import commands
from src.settings import get_settings
from src.fzd_db import (get_db_connection, 
                        get_hosting_schedule, 
                        add_new_user, 
                        get_user_id, 
                        update_host_in_db,
                        remove_host_from_event_db
                    )
from src.data.event_post_text import access_roles
from src.utils.hostpost_utils import discord_timestamp


class HostingSchedule(commands.Cog):
    def __init__(self, bot: commands.Bot, event_list) -> None:
        self.bot: commands.Bot = bot
        self.event_list: list[str] | None = event_list

    ''' Autocomplete methods '''
    async def event_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        options = [event for event in self.event_list if current.lower() in event.lower()]

        # Return up to 25 results (25=discord limit)
        return [app_commands.Choice(name=event, value=f"{event}") for event in options[:25]]
    

    ''' Helper Methods '''
    @staticmethod
    def format_events_for_schedule_board(event_dict):
        schedule_text = ''
        for i, event in enumerate(event_dict):
            if not event['host']:
                host_name = "🔴 None"
            else:
                host_name = f"🟢 {event['host']}"
            if event['active'] == 1:
                status = "🟢 Scheduled"
            else:
                status = "🔴 Cancelled"
                # taking naive datetime and making UTC aware
            time = discord_timestamp(event['start'].replace(tzinfo=UTC), "long")
            schedule_text += f"**{event['event_name']} | {time}**\n> Host: {host_name} | {status}"
            if i != len(event_dict) - 1:
                schedule_text += "\n"
        return schedule_text


    @staticmethod
    def build_schedule_embed(event_dict: list[dict]) -> discord.Embed:
        schedule_board = discord.Embed(
                            title="🏁 Host Signups for Scheduled Events", 
                            description=f"*As of {discord_timestamp(datetime.now(), 'long')}*", 
                            color=discord.Color.orange()
                            )
                        
        schedule_text = HostingSchedule.format_events_for_schedule_board(event_dict)
        schedule_board.add_field(name="", value=schedule_text, inline=False)

        return schedule_board


    async def update_live_board(self, interaction: discord.Interaction, event_dict: list[dict]):
        """
        """
        try:
            channel_id = get_settings().hosting_schedule_channel
            schedule_board = self.build_schedule_embed(event_dict)
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                # Fallback if the channel is not in the bot's internal cache
                channel = await self.bot.fetch_channel(channel_id)
            
            message = await channel.fetch_message(get_settings().hosting_schedule_message_id)
            await message.edit(embed=schedule_board)

        except discord.NotFound:
            await interaction.response.send_message("Error: The message or channel could not be found.")
        except discord.Forbidden:
            await interaction.response.send_message("Error: The bot does not have permissions to edit or view this.")
        except discord.HTTPException as e:
            await interaction.response.send_message(f"An error occurred: {e}")

    
    async def get_or_create_db_user(self, db, discord_user):
        """ Gets the user id from the database given a discord user. If the user is not in the database, creates a new user and returns the id.
        """
        db_user_id = await get_user_id(db, discord_user.name)
        if db_user_id is None:
            await add_new_user(db, discord_user, display_name=discord_user.nick[0:10])
            db_user_id = await get_user_id(db, discord_user.name)
            if db_user_id is None:
                raise TypeError(f"Could not add new user {discord_user}")
        return db_user_id


    ''' Slash Commands '''
    @app_commands.command(name="hosting_schedule", description="View upcoming schedule and hosts")
    @discord.app_commands.checks.has_any_role(*access_roles)
    async def hosting_schedule(self, interaction: discord.Interaction):
        try:
            async with get_db_connection(self.bot.db_pool) as db:
                event_dict = await get_hosting_schedule(db)
            # Create event list for autocomplete
            self.event_list = [s['event_name'] for s in event_dict if 'event_name' in s]

            if not event_dict:
                await interaction.response.send_message("No events are currently scheduled.", ephemeral=True)
                return
            else:
                schedule_board = HostingSchedule.build_schedule_embed(event_dict=event_dict)
                await interaction.response.send_message(embed=schedule_board, ephemeral=False)

        except Exception as e:
            print(f"Error occurred while fetching hosting schedule: {e}")
            await interaction.response.send_message("An error occurred while fetching the hosting schedule.", ephemeral=True)


    @app_commands.command(name="update_host_for_event", description="Add or modify a host to a scheduled event")
    @discord.app_commands.checks.has_any_role(*access_roles)
    async def update_host_for_event(self, interaction: discord.Interaction, event: str, host: discord.Member):
        try:
            async with get_db_connection(self.bot.db_pool) as db:
                event_dict = await get_hosting_schedule(db)
            # Create event list for autocomplete
            self.event_list = [s['event_name'] for s in event_dict if 'event_name' in s]

            if not event_dict:
                await interaction.response.send_message("No events are currently scheduled.", ephemeral=True)
                return
            if not event in [e['event_name'] for e in event_dict if 'event_name' in e]:
                await interaction.response.send_message(f"Event {event} not found.", ephemeral=True)
                return
            
            # Get event dictionary based on user input to get the event_id for database update
            event_info = next((e for e in event_dict if e['event_name'] == event), None)
            if event_info == None:
                await interaction.response.send_message(f"Event {event} not found.", ephemeral=True)
                return
            
            # Updated host in database
            # Get user id first, or add user if not registered in database
            async with get_db_connection(self.bot.db_pool) as db:
                db_user_id = await self.get_or_create_db_user(db, host)
                await update_host_in_db(db, event_info['event_id'], db_user_id)
                event_dict = await get_hosting_schedule(db)
                await self.update_live_board(interaction, event_dict)
            await interaction.response.send_message(f"Host for {event} updated to {host.display_name}.", ephemeral=False)                

        except Exception as e:
            print(f"Error occurred while fetching hosting schedule: {e}")
            await interaction.response.send_message("An error occurred while fetching the hosting schedule.", ephemeral=True)


    @app_commands.command(name="remove_host_from_event", description="Remove the host from a scheduled event")
    @discord.app_commands.checks.has_any_role(*access_roles)
    async def remove_host_from_event(self, interaction: discord.Interaction, event: str):
        try:
            async with get_db_connection(self.bot.db_pool) as db:
                event_dict = await get_hosting_schedule(db)
            # Create event list for autocomplete
            self.event_list = [s['event_name'] for s in event_dict if 'event_name' in s]

            if not event_dict:
                await interaction.response.send_message("No events are currently scheduled.", ephemeral=True)
                return
            if not event in [e['event_name'] for e in event_dict if 'event_name' in e]:
                await interaction.response.send_message(f"Event {event} not found.", ephemeral=True)
                return
            
            # Get event dictionary based on user input to get the event_id for database update
            event_info = next((e for e in event_dict if e['event_name'] == event), None)
            if event_info == None:
                await interaction.response.send_message(f"Event {event} not found.", ephemeral=True)
                return
            
            # Updated host in database to None
            print(f'Scheduled event id: {event_info['event_id']}')
            async with get_db_connection(self.bot.db_pool) as db:
                await remove_host_from_event_db(db, event_info['event_id'])
                event_dict = await get_hosting_schedule(db)
                await self.update_live_board(interaction, event_dict)
            await interaction.response.send_message(f"{event} updated to have no host.", ephemeral=False)                    

        except Exception as e:
            print(f"Error occurred while fetching hosting schedule: {e}")
            await interaction.response.send_message("An error occurred while fetching the hosting schedule.", ephemeral=True)


    @app_commands.command(name="anchor_post", description="create anchor post")
    @discord.app_commands.checks.has_any_role(*access_roles)
    async def anchor_post(self, interaction: discord.Interaction):
        """ Temporary command to create a message for the bot to update the schedule in.
        """
        async with get_db_connection(self.bot.db_pool) as db:
            event_dict = await get_hosting_schedule(db)
        schedule_board = HostingSchedule.build_schedule_embed(event_dict=event_dict)
        post_channel = self.bot.get_channel(
            discord.Object(id=int(get_settings().hosting_schedule_channel)).id)
        await post_channel.send(embed=schedule_board)
        await interaction.response.send_message("Anchor message sent.")
            

    @hosting_schedule.error
    @update_host_for_event.error
    @remove_host_from_event.error
    @anchor_post.error
    async def role_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingAnyRole):
            await interaction.response.send_message(
                "This command is Circuit Crew only. Hit up a mod if you want to join Circuit Crew.",
                ephemeral=True
                )
        else: raise error


    async def cog_load(self):
        self.update_host_for_event.autocomplete("event")(self.event_autocomplete)
        self.remove_host_from_event.autocomplete("event")(self.event_autocomplete)


async def setup(bot: commands.Bot):
    server_id = get_settings().server_id
    GUILD_ID = discord.Object(id=server_id)
    # Initialize list of events. This is updated during slash command. Initialization and 
    # update are necessary to not have to continually pull from the database during autocomplete.
    async with get_db_connection(bot.db_pool) as db:
        event_dict = await get_hosting_schedule(db)
        event_list = [s['event_name'] for s in event_dict if 'event_name' in s]
        await bot.add_cog(HostingSchedule(bot, event_list), guild=GUILD_ID)