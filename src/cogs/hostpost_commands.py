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

from src.data.event_post_text import ROLE_REFUSAL, access_roles, help_text_1, help_text_2
from src.fzd_api import FzdApiError
from src.fzd_db import get_db_connection, get_event_host_name
from src.main import HostBot
from src.settings import get_settings
from src.utils.build_hostposts import build_posts
from src.utils.hostpost_exports import prepare_post_outputs
from src.views.event_setup import EventSetupView, parse_instant

TEST_MODE_NOTICE = (
    "## NOTE: HostPost is in test mode.\nPost times are overridden to begin immediately and be approximately "
    "30 seconds apart. Check /list_all_autoposts for the trigger times.\nNo roles will be pinged."
)

logger = logging.getLogger(__name__)

# A rolling week: the events a host sets up next. The API writes the weeklies further out than this.
CALENDAR_DAYS = 7
# Discord's limits on a choice: `events.name` is `varchar(120)`, so the label can pass the first.
MAX_CHOICE_NAME = 100
MAX_CHOICES = 25


class EventBuilder(commands.Cog):
    def __init__(self, bot: HostBot) -> None:
        self.bot = bot

    async def event_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
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
            if needle not in event["event"].lower():
                continue
            starts_at = parse_instant(event["starts_at"])
            label = f"{event['event']} ({starts_at:%a %d %b %H:%M} UTC)"
            choices.append(app_commands.Choice(name=label[:MAX_CHOICE_NAME], value=str(event["scheduled_event_id"])))
        return choices[:MAX_CHOICES]

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
        # The event's detail does not carry its host.
        async with get_db_connection(self.bot.db_pool) as db:
            host = await get_event_host_name(db, detail["scheduled_event_id"])

        view = EventSetupView(self.bot, interaction, detail, host)
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
            await interaction.response.send_message(ROLE_REFUSAL, ephemeral=True)
        else:
            raise error

    async def cog_load(self):
        self.event_setup.autocomplete("event")(self.event_autocomplete)


async def setup(bot: HostBot):
    await bot.add_cog(EventBuilder(bot), guild=discord.Object(id=get_settings().server_id))
