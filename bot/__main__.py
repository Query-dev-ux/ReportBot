import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot.commands import set_admin_commands, set_default_commands
from bot.config import Settings
from bot.db import repo
from bot.db.models import Base
from bot.handlers import admin, buyer, common, groups, viewer
from bot.middlewares import DbMiddleware
from bot.scheduler import remind_missing_reports


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    config = Settings()

    engine = create_async_engine(config.database_url, pool_pre_ping=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    bot = Bot(config.bot_token.get_secret_value(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage(), config=config)
    dp.update.outer_middleware(DbMiddleware(sessionmaker))
    dp.include_routers(
        common.router,
        buyer.router,
        viewer.router,
        admin.router,
        groups.router,
        common.fallback_router,
    )

    await set_default_commands(bot)
    async with sessionmaker() as session:
        for admin_user in await repo.list_admins(session):
            await set_admin_commands(bot, admin_user.tg_id)

    scheduler = AsyncIOScheduler(timezone=config.tz)
    scheduler.add_job(
        remind_missing_reports,
        CronTrigger(
            hour=config.reminder_time.hour, minute=config.reminder_time.minute, timezone=config.tz
        ),
        kwargs={"bot": bot, "sessionmaker": sessionmaker, "config": config},
        misfire_grace_time=600,
    )
    scheduler.start()

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
