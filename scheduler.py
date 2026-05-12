import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler


async def init_scheduler():
    global scheduler
    scheduler = AsyncIOScheduler()
    scheduler.start()
    return scheduler