from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.db import repo
from bot.db.models import Role, User
from bot.keyboards import BTN_VIEW_REPORTS, BackToGroupsCb, BuyerCb, GroupCb, buyers_kb, groups_kb
from bot.middlewares import RoleFilter
from bot.utils import escape_text, report_card, send_long

REPORTS_TO_SHOW = 3

router = Router()
router.message.filter(F.chat.type == ChatType.PRIVATE, RoleFilter(Role.ADMIN, Role.TEAMLEAD))
router.callback_query.filter(RoleFilter(Role.ADMIN, Role.TEAMLEAD))


@router.message(F.text == BTN_VIEW_REPORTS)
async def view_reports(message: Message, state: FSMContext, session: AsyncSession, user: User) -> None:
    await state.clear()
    if user.role == Role.ADMIN:
        groups = await repo.list_groups(session)
        if not groups:
            await message.answer("Пока нет ни одной группы")
            return
        await message.answer("Выбери группу", reply_markup=groups_kb(groups))
        return

    buyers = await repo.list_buyers(session, user.group_id)
    if not buyers:
        await message.answer("В твоей группе пока нет баеров")
        return
    await message.answer("Выбери баера", reply_markup=buyers_kb(buyers, with_back=False))


@router.callback_query(GroupCb.filter(), RoleFilter(Role.ADMIN))
async def choose_group(call: CallbackQuery, callback_data: GroupCb, session: AsyncSession) -> None:
    buyers = await repo.list_buyers(session, callback_data.chat_id)
    text = "Выбери баера" if buyers else "В этой группе пока нет баеров"
    await call.message.edit_text(text, reply_markup=buyers_kb(buyers, with_back=True))
    await call.answer()


@router.callback_query(BackToGroupsCb.filter(), RoleFilter(Role.ADMIN))
async def back_to_groups(call: CallbackQuery, session: AsyncSession) -> None:
    groups = await repo.list_groups(session)
    await call.message.edit_text("Выбери группу", reply_markup=groups_kb(groups))
    await call.answer()


@router.callback_query(BuyerCb.filter())
async def choose_buyer(
    call: CallbackQuery,
    callback_data: BuyerCb,
    session: AsyncSession,
    user: User,
    bot: Bot,
    config: Settings,
) -> None:
    buyer = await repo.get_user(session, callback_data.user_id)
    if buyer is None or buyer.role != Role.BUYER:
        await call.answer("Баер не найден", show_alert=True)
        return
    if user.role == Role.TEAMLEAD and buyer.group_id != user.group_id:
        await call.answer("Нет доступа к этому баеру", show_alert=True)
        return

    name = escape_text(await repo.buyer_name(session, buyer))
    reports = await repo.last_reports(session, buyer.tg_id, REPORTS_TO_SHOW)
    await call.answer()
    if not reports:
        await call.message.answer(f"У баера <b>{name}</b> пока нет отчетов")
        return

    await call.message.answer(f"Последние отчеты баера <b>{name}</b>:")
    for report in reversed(reports):  # от старых к новым, самый свежий — внизу
        await send_long(bot, call.message.chat.id, report_card(report, config.tz))
