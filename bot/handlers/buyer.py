import logging
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.db import repo
from bot.db.models import Report, Role, User
from bot.keyboards import BTN_LAST_REPORT, BTN_NEW_REPORT, EditReportCb, edit_report_kb, main_menu
from bot.middlewares import RoleFilter
from bot.utils import (
    escape_text,
    fmt_date,
    parse_report_date,
    report_card,
    send_long,
    updated_report_post,
)

log = logging.getLogger(__name__)

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE, RoleFilter(Role.BUYER))
router.callback_query.filter(RoleFilter(Role.BUYER))

TEMPLATE = (
    "Создайте отчет по следующему шаблону:\n\n"
    "1. Напишите дату отчета (Например, отчёт за 14.03.26)\n"
    "2. Какие задачи у тебя на сегодняшний день?\n"
    "3. Какие есть сейчас проблемы? Какие есть вопросы?"
)


class ReportForm(StatesGroup):
    new = State()
    edit = State()


async def _publish(bot: Bot, user: User, text: str, reply_to: Report | None = None) -> int | None:
    """Отправляет текст в группу/тему баера. Возвращает id сообщения или None при ошибке."""
    if user.group_id is None:
        return None
    reply_id = None
    if reply_to and reply_to.chat_id == user.group_id and reply_to.thread_id == user.topic_id:
        reply_id = reply_to.message_id
    try:
        sent = await send_long(bot, user.group_id, text, thread_id=user.topic_id, reply_to=reply_id)
    except TelegramAPIError as e:
        log.warning("Failed to publish report of %s: %s", user.tg_id, e)
        return None
    return sent.message_id


@router.message(F.text == BTN_NEW_REPORT)
async def new_report(message: Message, state: FSMContext) -> None:
    await state.set_state(ReportForm.new)
    await message.answer(TEMPLATE)


@router.message(F.text == BTN_LAST_REPORT)
async def show_last_report(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
    config: Settings,
) -> None:
    await state.clear()
    report = await repo.last_report(session, user.tg_id)
    if report is None:
        await message.answer("У вас пока нет отчетов")
        return
    await send_long(
        bot, message.chat.id, report_card(report, config.tz), reply_markup=edit_report_kb(report.id)
    )


@router.message(ReportForm.new, F.text)
async def save_new_report(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    user: User,
    bot: Bot,
    config: Settings,
) -> None:
    report_date = parse_report_date(message.text, datetime.now(config.tz).date())
    if report_date is None:
        await message.answer(
            "Не нашел дату отчета. Укажите ее в первой строке, например: «Отчёт за 14.03.26»"
        )
        return

    report = await repo.create_report(session, user.tg_id, report_date, message.text)
    message_id = await _publish(bot, user, escape_text(message.text))
    if message_id is not None:
        report.chat_id, report.thread_id, report.message_id = user.group_id, user.topic_id, message_id
    await session.commit()
    await state.clear()

    status = "сохранен и отправлен в группу" if message_id else "сохранен, но не отправлен в группу"
    await message.answer(
        f"✅ Отчет за {fmt_date(report_date)} {status}", reply_markup=main_menu(Role.BUYER)
    )


@router.callback_query(EditReportCb.filter())
async def edit_report_start(
    call: CallbackQuery,
    callback_data: EditReportCb,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    report = await repo.get_report(session, callback_data.report_id)
    if report is None or report.user_id != user.tg_id:
        await call.answer("Отчет не найден", show_alert=True)
        return
    await state.set_state(ReportForm.edit)
    await state.update_data(report_id=report.id)
    await call.message.answer(
        f"Отправьте обновленный отчет за {fmt_date(report.report_date)} одним сообщением"
    )
    await call.answer()


@router.message(ReportForm.edit, F.text)
async def save_edited_report(
    message: Message, state: FSMContext, session: AsyncSession, user: User, bot: Bot
) -> None:
    data = await state.get_data()
    report = await repo.get_report(session, data.get("report_id", 0))
    await state.clear()
    if report is None or report.user_id != user.tg_id:
        await message.answer("Отчет не найден", reply_markup=main_menu(Role.BUYER))
        return

    repo.mark_updated(report, message.text)
    message_id = await _publish(bot, user, updated_report_post(report), reply_to=report)
    await session.commit()

    status = "обновлен и отправлен в группу" if message_id else "обновлен, но не отправлен в группу"
    await message.answer(
        f"✅ Отчет за {fmt_date(report.report_date)} {status}", reply_markup=main_menu(Role.BUYER)
    )


@router.message(ReportForm.new)
@router.message(ReportForm.edit)
async def not_text(message: Message) -> None:
    await message.answer("Отправьте отчет текстовым сообщением")
