# This is the event_helper bot, developed to assist hosts in developing posts.

import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
from fzd_db import init_db_pool
from scheduler import init_scheduler

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = discord.Object(id=os.getenv('SERVER_ID'))

handler = logging.FileHandler(filename='hostbot.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True

class HostBot(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def setup_hook(self):
        """Called automatically at startup, safe for async setup."""
        # Load all cogs from /command_cogs folder
        try:
            self.db_pool = await init_db_pool()
            self.scheduler = await init_scheduler()
            await self.load_extension("autopost_commands")
            await self.load_extension("hostpost_commands")
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
    
    bot.run(TOKEN, log_handler=handler, log_level=logging.DEBUG)
    
if __name__ == '__main__':
    main()