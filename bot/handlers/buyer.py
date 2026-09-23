import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.db import repo
from bot.db.models import QuestionDelivery, Report, Role, User
from bot.keyboards import (
    BTN_LAST_REPORT,
    BTN_NEW_REPORT,
    AnswerCb,
    EditReportCb,
    edit_report_kb,
    main_menu,
)
from bot.middlewares import RoleFilter
from bot.utils import (
    answer_post,
    escape_text,
    fmt_date,
    new_report_post,
    report_card,
    send_long,
    updated_report_post,
)

log = logging.getLogger(__name__)

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE, RoleFilter(Role.BUYER))
router.callback_query.filter(RoleFilter(Role.BUYER))

DEFAULT_TEMPLATE = (
    "Напиши отчет одним сообщением:\n\n"
    "1. Какие задачи у тебя на сегодняшний день?\n"
    "2. Какие есть сейчас проблемы? Какие есть вопросы?"
)


class ReportForm(StatesGroup):
    new = State()
    edit = State()


class QuestionForm(StatesGroup):
    answer = State()


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
async def new_report(message: Message, state: FSMContext, session: AsyncSession, user: User) -> None:
    await state.set_state(ReportForm.new)
    template = await repo.get_template(session, user.group_id) if user.group_id else None
    await message.answer(escape_text(template or DEFAULT_TEMPLATE))


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
        await message.answer("У тебя пока нет отчетов")
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
    # Дата отчета — день отправки сообщения по МСК
    report_date = message.date.astimezone(config.tz).date()
    report = await repo.create_report(session, user.tg_id, report_date, message.text)
    message_id = await _publish(bot, user, new_report_post(report))
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
        f"Отправь обновленный отчет за {fmt_date(report.report_date)} одним сообщением"
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
    await message.answer("Отправь отчет текстовым сообщением")


async def _save_answer(
    message: Message, session: AsyncSession, user: User, bot: Bot, delivery: QuestionDelivery
) -> None:
    question = await repo.get_question(session, delivery.question_id)
    repo.mark_answered(delivery, message.text)
    name = await repo.buyer_name(session, user)
    published = await _publish(
        bot, user, answer_post(question.text if question else "", name, message.text)
    )
    await session.commit()
    status = "отправлен в твою тему" if published else "сохранен, но не отправлен в группу"
    await message.answer(f"✅ Ответ {status}", reply_markup=main_menu(Role.BUYER))


@router.callback_query(AnswerCb.filter())
async def answer_start(
    call: CallbackQuery,
    callback_data: AnswerCb,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    delivery = await repo.get_delivery(session, callback_data.delivery_id)
    if delivery is None or delivery.buyer_id != user.tg_id:
        await call.answer("Вопрос не найден", show_alert=True)
        return
    await state.set_state(QuestionForm.answer)
    await state.update_data(delivery_id=delivery.id)
    await call.message.answer("Напиши ответ одним сообщением")
    await call.answer()


@router.message(QuestionForm.answer, F.text)
async def save_answer(
    message: Message, state: FSMContext, session: AsyncSession, user: User, bot: Bot
) -> None:
    data = await state.get_data()
    await state.clear()
    delivery = await repo.get_delivery(session, data.get("delivery_id", 0))
    if delivery is None or delivery.buyer_id != user.tg_id:
        await message.answer("Вопрос не найден", reply_markup=main_menu(Role.BUYER))
        return
    await _save_answer(message, session, user, bot, delivery)


@router.message(QuestionForm.answer)
async def answer_not_text(message: Message) -> None:
    await message.answer("Отправь ответ текстовым сообщением")


@router.message(F.reply_to_message, F.text)
async def answer_by_reply(
    message: Message, state: FSMContext, session: AsyncSession, user: User, bot: Bot
) -> None:
    """Ответ реплаем на сообщение с вопросом."""
    delivery = await repo.delivery_by_message(
        session, user.tg_id, message.reply_to_message.message_id
    )
    if delivery is None:
        await message.answer("Выбери действие в меню", reply_markup=main_menu(Role.BUYER))
        return
    await state.clear()
    await _save_answer(message, session, user, bot, delivery)
