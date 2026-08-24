# This is the event_helper bot, developed to assist hosts in developing posts.

import os
import sys

import discord
from discord import app_commands
from discord.ext import commands
import logging

from src.error_alerts import send_error_alert
from src.settings import configure_logging, get_settings

from src.fzd_api import FzdApi
from src.fzd_db import init_db_pool, get_db_connection, check_db_for_hosting_support
from src.utils.scheduler import init_scheduler

logger = logging.getLogger(__name__)


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class HostBot(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.job_stack = []


    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        original_error = getattr(error, "original", error)
        logger.error(
            "Unhandled app command error for command=%s user=%s",
            getattr(interaction.command, "qualified_name", None),
            interaction.user,
            exc_info=(type(original_error), original_error, original_error.__traceback__),
        )
        await send_error_alert(
            self,
            where="app command",
            error=original_error,
            interaction=interaction,
        )

        if interaction.response.is_done():
            await interaction.followup.send(
                "ERROR! Something went wrong, contact FZD staff for help!",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "ERROR! Something went wrong, contact FZD staff for help!",
                ephemeral=True,
            )

    
    async def setup_hook(self):
        """Called automatically at startup, safe for async setup."""
        # Load all cogs from /cogs folder
        settings = get_settings()
        try:
            self.db_pool = await init_db_pool()
            self.scheduler = await init_scheduler()
            # The FZD API. Built unconditionally: when it is not configured the
            # two commands that use it say so, and the other eleven never ask.
            self.api = FzdApi(
                base_url=settings.fzd_api_base_url,
                api_key=settings.fzd_api_key.get_secret_value(),
                timeout_seconds=settings.fzd_api_timeout_seconds,
            )
            if not self.api.configured:
                logger.warning(
                    "FZD_API_BASE_URL / FZD_API_KEY are not set: /update_host_for_event "
                    "and /remove_host_from_event will refuse until they are."
                )
            await self.load_extension("src.cogs.autopost_commands")
            await self.load_extension("src.cogs.hostpost_commands")
            # Check to see if database configured to allow for hosting support. Only load cog if True.
            async with get_db_connection(self.db_pool) as db:
                if await check_db_for_hosting_support(db, settings.db_name):
                    await self.load_extension("src.cogs.hosting_signup")
            print("✅ Loaded extensions")
        except Exception as error:
            logger.exception("Failed to load extensions")
            await send_error_alert(
                self,
                where="setup_hook load extensions",
                error=error,
            )
            raise

        try:
            guild_id = discord.Object(id=settings.server_id)
            # Force sync so bot command changes will appear right away
            synced = await self.tree.sync(guild=guild_id)
            logger.info("Synced %s commands to guild %s", len(synced), guild_id.id)
        except Exception as error:
            logger.exception("Error syncing commands")
            await send_error_alert(
                self,
                where="setup_hook sync commands",
                error=error,
                details={"guild_id": settings.server_id},
            )


    async def close(self) -> None:
        """Shut the API session down with the bot.

        An unclosed `aiohttp.ClientSession` logs a warning on interpreter exit
        and is one of the few things in this bot that leaks across a restart.
        """
        api = getattr(self, "api", None)
        if api is not None:
            await api.close()
        await super().close()


    async def on_ready(self) -> None:
        logger.info("%s is now running", self.user)

    async def on_error(self, event_method: str, /, *args, **kwargs) -> None:
        error = sys.exc_info()[1]
        if error is None:
            logger.error("Unhandled exception in event %s without exception info", event_method)
            return

        logger.error(
            "Unhandled exception in event %s",
            event_method,
            exc_info=(type(error), error, error.__traceback__),
        )
        await send_error_alert(
            self,
            where=f"event {event_method}",
            error=error,
        )


def main() -> None:
    settings = get_settings()
    configure_logging()
    intents = discord.Intents.default()
    intents.message_content = True  # Required to read message content
    intents.guilds = True
    intents.messages = True

    client = HostBot(command_prefix="!", intents=intents)
    client.run(token=settings.discord_token)
    
if __name__ == '__main__':
    main()