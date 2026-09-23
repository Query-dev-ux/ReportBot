import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import repo
from bot.db.models import Role, User
from bot.keyboards import (
    BTN_ASK,
    AskAllCb,
    AskCancelCb,
    AskDoneCb,
    AskToggleCb,
    answer_kb,
    ask_buyers_kb,
    main_menu,
)
from bot.middlewares import RoleFilter
from bot.utils import escape_text, question_dm

log = logging.getLogger(__name__)

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE, RoleFilter(Role.ADMIN, Role.TEAMLEAD))
router.callback_query.filter(RoleFilter(Role.ADMIN, Role.TEAMLEAD))


class AskForm(StatesGroup):
    selecting = State()
    question = State()


async def _buyers_for(session: AsyncSession, user: User) -> list[tuple[User, str]]:
    """Админ видит всех баеров (с группой в подписи), ТимЛид — только свою группу."""
    if user.role == Role.ADMIN:
        rows = await repo.list_all_buyers(session)
        return [(buyer, f"{name} · {group_title}") for buyer, name, group_title in rows]
    if user.group_id is None:
        return []
    return await repo.list_buyers(session, user.group_id)


async def _selected(state: FSMContext) -> set[int]:
    data = await state.get_data()
    return set(data.get("selected", []))


@router.message(F.text == BTN_ASK)
async def start_ask(message: Message, state: FSMContext, session: AsyncSession, user: User) -> None:
    buyers = await _buyers_for(session, user)
    if not buyers:
        await state.clear()
        await message.answer("Пока нет ни одного баера")
        return
    await state.set_state(AskForm.selecting)
    await state.update_data(selected=[])
    await message.answer(
        "Выбери, кому отправить вопрос:", reply_markup=ask_buyers_kb(buyers, set())
    )


@router.callback_query(AskToggleCb.filter(), AskForm.selecting)
async def toggle_buyer(
    call: CallbackQuery,
    callback_data: AskToggleCb,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    buyers = await _buyers_for(session, user)
    if callback_data.user_id not in {buyer.tg_id for buyer, _ in buyers}:
        await call.answer("Баер не найден", show_alert=True)
        return
    selected = await _selected(state) ^ {callback_data.user_id}
    await state.update_data(selected=sorted(selected))
    await call.message.edit_reply_markup(reply_markup=ask_buyers_kb(buyers, selected))
    await call.answer()


@router.callback_query(AskAllCb.filter(), AskForm.selecting)
async def toggle_all(
    call: CallbackQuery,
    callback_data: AskAllCb,
    state: FSMContext,
    session: AsyncSession,
    user: User,
) -> None:
    buyers = await _buyers_for(session, user)
    selected = {buyer.tg_id for buyer, _ in buyers} if callback_data.select else set()
    await state.update_data(selected=sorted(selected))
    await call.message.edit_reply_markup(reply_markup=ask_buyers_kb(buyers, selected))
    await call.answer()


@router.callback_query(AskCancelCb.filter(), AskForm.selecting)
async def cancel_ask(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text("Отменено")
    await call.answer()


@router.callback_query(AskDoneCb.filter(), AskForm.selecting)
async def finish_selection(
    call: CallbackQuery, state: FSMContext, session: AsyncSession, user: User
) -> None:
    selected = await _selected(state)
    if not selected:
        await call.answer("Выбери хотя бы одного баера", show_alert=True)
        return
    buyers = await _buyers_for(session, user)
    names = [name for buyer, name in buyers if buyer.tg_id in selected]
    await state.set_state(AskForm.question)
    await call.message.edit_text(
        f"Получатели: {escape_text(', '.join(names))}\n\n"
        "Напиши вопрос одним сообщением или /cancel для отмены"
    )
    await call.answer()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    await message.answer("Отменено", reply_markup=main_menu(user.role))


@router.message(AskForm.question, F.text)
async def send_question(
    message: Message, state: FSMContext, session: AsyncSession, user: User, bot: Bot
) -> None:
    selected = await _selected(state)
    await state.clear()
    buyers = {buyer.tg_id: name for buyer, name in await _buyers_for(session, user)}

    question = await repo.create_question(session, user.tg_id, message.text)
    delivered: list[str] = []
    failed: list[str] = []
    for buyer_id in sorted(selected & buyers.keys()):
        delivery = await repo.create_delivery(session, question.id, buyer_id)
        try:
            sent = await bot.send_message(
                buyer_id, question_dm(message.text), reply_markup=answer_kb(delivery.id)
            )
        except TelegramAPIError as e:
            log.warning("Failed to send question to %s: %s", buyer_id, e)
            await session.delete(delivery)
            failed.append(buyers[buyer_id])
        else:
            delivery.message_id = sent.message_id
            delivered.append(buyers[buyer_id])
        await asyncio.sleep(0.05)  # не упираемся в лимиты Telegram
    await session.commit()

    lines = [f"✅ Вопрос отправлен: {escape_text(', '.join(delivered))}" if delivered else "❌ Никому не удалось отправить вопрос"]
    if failed:
        lines.append(f"⚠️ Не доставлен: {escape_text(', '.join(failed))} (баер не запускал бота)")
    await message.answer("\n".join(lines), reply_markup=main_menu(user.role))


@router.message(AskForm.question)
async def question_not_text(message: Message) -> None:
    await message.answer("Отправь вопрос текстовым сообщением или /cancel для отмены")
