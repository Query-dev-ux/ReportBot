import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat

log = logging.getLogger(__name__)

USER_COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="unlock", description="Авторизация"),
]

ADMIN_COMMANDS = USER_COMMANDS + [
    BotCommand(command="template", description="Шаблон отчета группы"),
    BotCommand(command="cancel", description="Отменить действие"),
]


async def set_default_commands(bot: Bot) -> None:
    await bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeAllPrivateChats())


async def set_admin_commands(bot: Bot, chat_id: int) -> None:
    """Меню команд с админскими командами — только в личке конкретного админа."""
    try:
        await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=chat_id))
    except TelegramAPIError as e:
        log.warning("Failed to set admin commands for %s: %s", chat_id, e)


async def reset_commands(bot: Bot, chat_id: int) -> None:
    """Убирает админское меню, если пользователь перелогинился в другую роль."""
    try:
        await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=chat_id))
    except TelegramAPIError as e:
        log.warning("Failed to reset commands for %s: %s", chat_id, e)
