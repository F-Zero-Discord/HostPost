# This is the event_helper bot, developed to assist hosts in developing posts.

import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
from src.fzd_db import init_db_pool, get_db_connection, check_db_for_hosting_support
from src.utils.scheduler import init_scheduler

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = discord.Object(id=os.getenv('SERVER_ID'))
DATABASE = os.getenv('DB_NAME')

handler = logging.FileHandler(filename='hostbot.log', encoding='utf-8', mode='w')
handler.setLevel(logging.WARNING)
formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s')
handler.setFormatter(formatter)
logging.getLogger('discord').setLevel(logging.WARNING)
logging.getLogger('discord.gateway').setLevel(logging.WARNING)
logging.getLogger('discord.client').setLevel(logging.WARNING)
logging.getLogger('discord.http').setLevel(logging.WARNING)
logging.basicConfig(level=logging.WARNING, handlers=[handler], force=True)


intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class HostBot(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.job_stack = []

    async def setup_hook(self):
        """Called automatically at startup, safe for async setup."""
        # Load all cogs from /cogs folder
        try:
            self.db_pool = await init_db_pool()
            self.scheduler = await init_scheduler()
            await self.load_extension("src.cogs.autopost_commands")
            await self.load_extension("src.cogs.hostpost_commands")
            # Check to see if database configured to allow for hosting support. Only load cog if True.
            async with get_db_connection(self.db_pool) as db:
                if await check_db_for_hosting_support(db, DATABASE):
                    await self.load_extension("src.cogs.hosting_signup")
            print("✅ Loaded extensions")
        except Exception as e:
            print(f"Failed to load extensions: {e}")

        try:
            # Force sync so bot command changes will appear right away
            synced = await self.tree.sync(guild=GUILD_ID)
            print(f'Synced {len(synced)} commands to guild {GUILD_ID.id}')
        except Exception as e:
            print(f'Error syncing commands: {e}')

    async def on_ready(self) -> None:
        # await self.load_extension("a_pyfile")
        # await self.load_extension("a_pyfile")
        print(f'✅ {self.user} is now running!')

bot = HostBot(command_prefix='!', intents=intents)

def main():
    
    bot.run(TOKEN, log_handler=handler, log_level=logging.WARNING)
    
if __name__ == '__main__':
    main()