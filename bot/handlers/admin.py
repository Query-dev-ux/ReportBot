import re

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import repo
from bot.db.models import Group, Role
from bot.handlers.buyer import DEFAULT_TEMPLATE
from bot.keyboards import main_menu
from bot.middlewares import RoleFilter
from bot.utils import escape_text, normalize_chat_id, short_chat_id

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE, RoleFilter(Role.ADMIN))

TEMPLATE_HELP = (
    "Шаблон отчета задается для группы:\n\n"
    "<code>/template ID_группы</code> — показать текущий шаблон и задать новый\n"
    "<code>/template ID_группы текст шаблона</code> — сразу задать новый шаблон"
)

_TEMPLATE_ARGS = re.compile(r"(-?\d+)(?:\s+(.+))?", re.DOTALL)


class TemplateForm(StatesGroup):
    text = State()


async def _resolve_group(session: AsyncSession, bot: Bot, chat_id: int) -> Group | None:
    """Группа из БД, а если ее там нет — из Telegram (бот должен быть в группе)."""
    group = await repo.get_group(session, chat_id)
    if group:
        return group
    try:
        chat = await bot.get_chat(chat_id)
    except TelegramAPIError:
        return None
    await repo.upsert_group(session, chat.id, chat.title or str(chat.id))
    return await repo.get_group(session, chat.id)


async def _save_template(message: Message, session: AsyncSession, group: Group, text: str) -> None:
    await repo.set_template(session, group.chat_id, text)
    await session.commit()
    await message.answer(
        f"✅ Шаблон группы «{escape_text(group.title)}» сохранен:\n\n{escape_text(text)}",
        reply_markup=main_menu(Role.ADMIN),
    )


@router.message(Command("template"))
async def cmd_template(
    message: Message, command: CommandObject, state: FSMContext, session: AsyncSession, bot: Bot
) -> None:
    await state.clear()
    match = _TEMPLATE_ARGS.fullmatch((command.args or "").strip())
    if not match:
        groups = await repo.list_groups(session)
        lines = [
            f"• {escape_text(group.title)} — <code>{short_chat_id(group.chat_id)}</code>"
            for group in groups
        ]
        await message.answer(TEMPLATE_HELP + ("\n\nГруппы:\n" + "\n".join(lines) if lines else ""))
        return

    group = await _resolve_group(session, bot, normalize_chat_id(match[1]))
    if group is None:
        await message.answer("Группа не найдена. Проверь ID и убедись, что бот добавлен в группу")
        return

    if match[2] and match[2].strip():
        await _save_template(message, session, group, match[2].strip())
        return

    current = await repo.get_template(session, group.chat_id)
    await session.commit()  # группа могла быть добавлена в _resolve_group
    await state.set_state(TemplateForm.text)
    await state.update_data(chat_id=group.chat_id)
    label = "Текущий шаблон" if current else "Сейчас используется шаблон по умолчанию"
    await message.answer(
        f"{label} группы «{escape_text(group.title)}»:\n\n"
        f"{escape_text(current or DEFAULT_TEMPLATE)}\n\n"
        "Отправь новый шаблон одним сообщением или /cancel для отмены"
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменено", reply_markup=main_menu(Role.ADMIN))


@router.message(TemplateForm.text, F.text)
async def save_template(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    await state.clear()
    group = await repo.get_group(session, data.get("chat_id", 0))
    if group is None:
        await message.answer("Группа не найдена", reply_markup=main_menu(Role.ADMIN))
        return
    await _save_template(message, session, group, message.text.strip())


@router.message(TemplateForm.text)
async def template_not_text(message: Message) -> None:
    await message.answer("Отправь шаблон текстовым сообщением или /cancel для отмены")
