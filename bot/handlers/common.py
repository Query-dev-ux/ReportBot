import hmac
import logging
import re

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.db import repo
from bot.db.models import Role, User
from bot.keyboards import main_menu
from bot.utils import escape_text, normalize_chat_id

log = logging.getLogger(__name__)

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE)

fallback_router = Router()
fallback_router.message.filter(F.chat.type == ChatType.PRIVATE)

UNLOCK_HELP = "🔒 Доступ к боту закрыт\n\nОткрыть: /unlock КЛЮЧ"

ROLE_TITLES = {Role.BUYER: "баер", Role.TEAMLEAD: "ТимЛид", Role.ADMIN: "админ"}
_UNLOCK_ARG = re.compile(r"(-?\d+)(?:/(\d+))?")
_NOT_MEMBER = {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user: User | None) -> None:
    await state.clear()
    if user is None:
        await message.answer(UNLOCK_HELP)
        return
    await message.answer(
        f"Вы авторизованы как {ROLE_TITLES[user.role]}", reply_markup=main_menu(user.role)
    )


@router.message(Command("unlock"))
async def cmd_unlock(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    config: Settings,
) -> None:
    await state.clear()
    arg = (command.args or "").strip()
    if not arg:
        await message.answer(UNLOCK_HELP)
        return

    if hmac.compare_digest(arg.encode(), config.admin_key.get_secret_value().encode()):
        await repo.upsert_user(session, message.from_user, Role.ADMIN)
        await session.commit()
        await message.answer("✅ Вы авторизованы как админ", reply_markup=main_menu(Role.ADMIN))
        return

    match = _UNLOCK_ARG.fullmatch(arg)
    if not match:
        await message.answer("❌ Неверный ключ")
        return

    chat_id = normalize_chat_id(match[1])
    topic_id = int(match[2]) if match[2] else None

    try:
        chat = await bot.get_chat(chat_id)
        # Баеру состоять в группе не нужно, ТимЛиду — обязательно
        member = None if topic_id else await bot.get_chat_member(chat_id, message.from_user.id)
    except TelegramAPIError as e:
        log.info("unlock: chat %s unavailable: %s", chat_id, e)
        await message.answer(
            "Не удалось найти группу. Проверьте ID и убедитесь, что бот добавлен в группу"
        )
        return
    if member and member.status in _NOT_MEMBER:
        await message.answer("Вы не состоите в этой группе")
        return

    title = chat.title or str(chat.id)
    await repo.upsert_group(session, chat.id, title)

    if topic_id is None:
        await repo.upsert_user(session, message.from_user, Role.TEAMLEAD, group_id=chat.id)
        await session.commit()
        await message.answer(
            f"✅ Вы авторизованы как ТимЛид группы «{escape_text(title)}»",
            reply_markup=main_menu(Role.TEAMLEAD),
        )
        return

    if topic_id == config.general_topic_id:
        await message.answer("Тема General не может быть темой баера. Укажите ID своей темы")
        return

    # Проверяем, что бот может писать в тему, и заодно узнаем ее название
    try:
        sent = await bot.send_message(
            chat.id,
            f"✅ {escape_text(message.from_user.full_name)} привязан(а) к этой теме для отчетов",
            message_thread_id=topic_id,
        )
    except TelegramAPIError as e:
        log.info("unlock: topic %s/%s unavailable: %s", chat.id, topic_id, e)
        await message.answer(
            "Не удалось отправить сообщение в тему. Проверьте ID темы и права бота в группе"
        )
        return
    root = sent.reply_to_message
    if root and root.forum_topic_created:
        await repo.upsert_topic(session, chat.id, topic_id, root.forum_topic_created.name)

    user = await repo.upsert_user(
        session, message.from_user, Role.BUYER, group_id=chat.id, topic_id=topic_id
    )
    name = await repo.buyer_name(session, user)
    await session.commit()
    await message.answer(
        f"✅ Вы авторизованы как баер «{escape_text(name)}» в группе «{escape_text(title)}»",
        reply_markup=main_menu(Role.BUYER),
    )


@fallback_router.message()
async def fallback(message: Message, user: User | None) -> None:
    if user is None:
        await message.answer(UNLOCK_HELP)
    else:
        await message.answer("Выберите действие в меню", reply_markup=main_menu(user.role))
