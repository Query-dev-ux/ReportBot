import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.config import Settings
from bot.db import repo
from bot.db.models import Role, User
from bot.keyboards import main_menu
from bot.utils import escape_text, fmt_date, send_long

log = logging.getLogger(__name__)


async def remind_missing_reports(bot: Bot, sessionmaker: async_sessionmaker, config: Settings) -> None:
    """Напоминает баерам без отчета за вчера и шлет их список в тему General группы."""
    yesterday = datetime.now(config.tz).date() - timedelta(days=1)
    async with sessionmaker() as session:
        missing = await repo.buyers_without_report(session, yesterday)

    log.info("Reminder for %s: %d buyers without report", yesterday, len(missing))
    by_group: dict[int, list[tuple[User, str]]] = defaultdict(list)
    for buyer, name in missing:
        by_group[buyer.group_id].append((buyer, name))
        try:
            await bot.send_message(
                buyer.tg_id,
                f"⏰ Вы не заполнили отчет за {fmt_date(yesterday)}. "
                "Пожалуйста, создайте его через кнопку «Создать новый отчет»",
                reply_markup=main_menu(Role.BUYER),
            )
        except TelegramAPIError as e:
            log.warning("Failed to remind %s: %s", buyer.tg_id, e)
        await asyncio.sleep(0.05)  # не упираемся в лимиты Telegram

    # General в форуме принимает сообщения только без message_thread_id
    thread_id = None if config.general_topic_id == 1 else config.general_topic_id
    for chat_id, buyers in by_group.items():
        lines = [
            f"• {escape_text(name)}" + (f" (@{buyer.username})" if buyer.username else "")
            for buyer, name in sorted(buyers, key=lambda item: item[1].lower())
        ]
        text = f"📋 Не заполнили отчет за {fmt_date(yesterday)}:\n" + "\n".join(lines)
        try:
            await send_long(bot, chat_id, text, thread_id=thread_id)
        except TelegramAPIError as e:
            log.warning("Failed to send missing list to %s: %s", chat_id, e)
