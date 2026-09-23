"""
/event_setup and /help.

/event_setup writes an event's scoring and schedule through the FZD API, then
hands the written schedule to the post pipeline (`build_posts`,
`prepare_post_outputs`).
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from src.data.event_post_text import access_roles, help_text_1, help_text_2
from src.fzd_api import FzdApiError
from src.settings import get_settings
from src.utils.build_hostposts import build_posts
from src.utils.hostpost_exports import prepare_post_outputs
from src.views.event_setup import EventSetupView, parse_instant

TEST_MODE_NOTICE = (
    "## NOTE: HostPost is in test mode.\nPost times are overridden to begin immediately and be approximately "
    "30 seconds apart. Check /list_all_autoposts for the trigger times.\nNo roles will be pinged."
)

logger = logging.getLogger(__name__)

CALENDAR_DAYS = 14


class EventBuilder(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def event_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """The calendar, read on every keystroke. Nothing is held on the cog;
        the read is cheaper than the Discord round trip that follows it, and a
        failure is an empty list rather than an error the host cannot act on."""
        if not self.bot.api.configured:
            return []
        try:
            events = await self.bot.api.calendar(days=CALENDAR_DAYS)
        except FzdApiError as error:
            logger.warning("event autocomplete: %s", error)
            return []
        needle = current.lower()
        choices = []
        for event in events:
            name = event["display_name"] or event["event"]
            if needle not in name.lower() and needle not in event["event"].lower():
                continue
            starts_at = parse_instant(event["starts_at"])
            choices.append(
                app_commands.Choice(
                    name=f"{name} ({starts_at:%a %d %b %H:%M} UTC)"[:100],
                    value=str(event["scheduled_event_id"]),
                )
            )
        return choices[:25]

    @app_commands.command(name="event_setup", description="Set up an event's slots and scoring.")
    @discord.app_commands.checks.has_any_role(*access_roles)
    async def event_setup(self, interaction: discord.Interaction, event: str):
        api = self.bot.api
        if not api.configured:
            await interaction.response.send_message(
                "This command needs the FZD API, and FZD_API_BASE_URL / FZD_API_KEY are not set in this bot's .env.",
                ephemeral=True,
            )
            return
        if not event.isdigit():
            await interaction.response.send_message("Pick an event from the list.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            detail = await api.event_detail(int(event))
        except FzdApiError as error:
            await interaction.followup.send(str(error), ephemeral=True)
            return

        view = EventSetupView(self.bot, interaction, detail)
        await interaction.followup.send(view=view, ephemeral=True)
        await view.wait()
        if view.prix_list is None or view.autopost is None:
            return

        # The wizard's last click, not the command: the command's token can
        # expire while the wizard runs, and every post below is a followup.
        followup_to = view.last_interaction
        post_struct = await build_posts(self.bot, view.event_name, view.event_id, view.prix_list)
        await prepare_post_outputs(
            self.bot, followup_to, view.event_name, post_struct, view.prix_list, view.autopost, view.validate
        )
        if get_settings().test_flag == 1 and view.autopost:
            await followup_to.followup.send(TEST_MODE_NOTICE)

    @app_commands.command(name="help", description="Information about the HostPost bot.")
    async def help(self, interaction: discord.Interaction):
        await interaction.response.send_message(help_text_1, ephemeral=True)
        await interaction.followup.send(help_text_2, ephemeral=True)

    @event_setup.error
    async def role_error(self, interaction: discord.Interaction, error):
        if isinstance(error, app_commands.MissingAnyRole):
            await interaction.response.send_message(
                "This command is Circuit Crew only. Hit up a mod if you want to join Circuit Crew.",
                ephemeral=True,
            )
        else:
            raise error

    async def cog_load(self):
        self.event_setup.autocomplete("event")(self.event_autocomplete)


async def setup(bot: commands.Bot):
    await bot.add_cog(EventBuilder(bot), guild=discord.Object(id=get_settings().server_id))
