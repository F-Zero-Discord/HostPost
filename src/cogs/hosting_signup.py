"""
Contains slash commands and associated views to allow users to view which events are hosted and 
sign up for events.
"""
from datetime import datetime, UTC
import logging

import discord
from discord import app_commands
from discord.ext import commands
from src.settings import get_settings
from src.fzd_api import FzdApiError
from src.fzd_db import get_db_connection, get_hosting_schedule
from src.data.event_post_text import access_roles
from src.utils.hostpost_utils import discord_timestamp

logger = logging.getLogger(__name__)

TAG_MAX_LENGTH = 10
"""`users.tag` is `varchar(10)`, matching F-Zero 99's in-game name limit. The API
rejects a longer one rather than truncating it, so the trim happens here."""


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


    @staticmethod
    async def respond(interaction: discord.Interaction, content: str, *, ephemeral: bool = False) -> None:
        """ Replies whether or not the interaction has already been deferred.

            The two host commands defer before calling the API — an HTTP hop from a
            Raspberry Pi to the VPS plus a board refresh can outrun Discord's
            three-second window, and a missed window shows the host "The
            application did not respond" while the write has in fact happened.
            After a defer the only way to answer is a followup, so anything that
            can be reached from both paths has to go through here. Same shape
            `main.HostBot.on_app_command_error` already uses.
        """
        if interaction.response.is_done():
            await interaction.followup.send(content, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(content, ephemeral=ephemeral)


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
            await self.respond(interaction, "Error: The message or channel could not be found.")
        except discord.Forbidden:
            await self.respond(interaction, "Error: The bot does not have permissions to edit or view this.")
        except discord.HTTPException as e:
            await self.respond(interaction, f"An error occurred: {e}")


    async def resolve_event(self, interaction: discord.Interaction, event: str) -> dict | None:
        """ Finds the scheduled event the host named, refreshing the autocomplete list on the way.

        Replies and returns None if there is nothing to act on, so a caller can
        `if event_info is None: return`. The schedule read is still this bot's own
        SQL — the hosting schedule belongs to Plan 10, not to this port.
        """
        async with get_db_connection(self.bot.db_pool) as db:
            event_dict = await get_hosting_schedule(db)
        # Create event list for autocomplete
        self.event_list = [s['event_name'] for s in event_dict if 'event_name' in s]

        if not event_dict:
            await self.respond(interaction, "No events are currently scheduled.", ephemeral=True)
            return None

        event_info = next((e for e in event_dict if e.get('event_name') == event), None)
        if event_info is None:
            await self.respond(interaction, f"Event {event} not found.", ephemeral=True)
            return None
        return event_info


    async def refresh_live_board(self, interaction: discord.Interaction) -> None:
        """ Re-reads the schedule and edits the anchor message to match.
        """
        async with get_db_connection(self.bot.db_pool) as db:
            event_dict = await get_hosting_schedule(db)
        await self.update_live_board(interaction, event_dict)


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
        """ Assigns a host to a scheduled event, through the FZD API (task 15-04).

            The API resolves the Discord account to a row in `users` and writes
            `events_scheduled.host_id` itself. This command sends a snowflake and a
            username and holds no database id of its own — which is the whole point
            of the port: the "which row is this person" rule lives in one place,
            and it is not here.
        """
        event_info = await self.resolve_event(interaction, event)
        if event_info is None:
            return

        # Deferred here rather than at the top of the command so the two
        # "nothing to do" replies above stay ephemeral: Discord ignores
        # `ephemeral` on the first followup after a public defer.
        await interaction.response.defer()

        try:
            await self.bot.api.assign_host(
                int(event_info['event_id']),
                # `host.id` is the immutable snowflake and `host.name` the mutable
                # username. Both come off the same interaction, which is what makes
                # this bot's pairing of the two authoritative.
                discord_user_id=host.id,
                discord_user_name=host.name,
                # Only used if this account has no row yet. `display_name` is the
                # nickname, the global name or the username, in that order, and is
                # never None — unlike `host.nick`, which was indexed directly here
                # and raised TypeError for any host without a server nickname.
                tag=host.display_name[:TAG_MAX_LENGTH],
            )
        except FzdApiError as error:
            logger.error("update_host_for_event failed for event=%s host=%s: %s", event, host, error)
            await self.respond(interaction, f"Could not set the host for {event}. {error}")
            return

        await self.refresh_live_board(interaction)
        await self.respond(interaction, f"Host for {event} updated to {host.display_name}.")


    @app_commands.command(name="remove_host_from_event", description="Remove the host from a scheduled event")
    @discord.app_commands.checks.has_any_role(*access_roles)
    async def remove_host_from_event(self, interaction: discord.Interaction, event: str):
        """ Leaves a scheduled event with no host, through the FZD API (task 15-04).

            The other half of the same command. It resolves nobody — removing a host
            needs no identity at all.
        """
        event_info = await self.resolve_event(interaction, event)
        if event_info is None:
            return

        await interaction.response.defer()

        try:
            await self.bot.api.remove_host(int(event_info['event_id']))
        except FzdApiError as error:
            logger.error("remove_host_from_event failed for event=%s: %s", event, error)
            await self.respond(interaction, f"Could not remove the host from {event}. {error}")
            return

        await self.refresh_live_board(interaction)
        await self.respond(interaction, f"{event} updated to have no host.")


    # @app_commands.command(name="anchor_post", description="create anchor post")
    # @discord.app_commands.checks.has_any_role(*access_roles)
    # async def anchor_post(self, interaction: discord.Interaction):
    #     """ Temporary command to create a message for the bot to update the schedule in.
    #     """
    #     async with get_db_connection(self.bot.db_pool) as db:
    #         event_dict = await get_hosting_schedule(db)
    #     schedule_board = HostingSchedule.build_schedule_embed(event_dict=event_dict)
    #     post_channel = self.bot.get_channel(
    #         discord.Object(id=int(get_settings().hosting_schedule_channel)).id)
    #     await post_channel.send(embed=schedule_board)
    #     await interaction.response.send_message("Anchor message sent.")
            

    @hosting_schedule.error
    @update_host_for_event.error
    @remove_host_from_event.error
    # @anchor_post.error
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