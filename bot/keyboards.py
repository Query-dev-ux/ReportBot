from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from bot.db.models import Group, Role, User

BTN_NEW_REPORT = "Создать новый отчет"
BTN_LAST_REPORT = "Посмотреть последний отчет"
BTN_VIEW_REPORTS = "Посмотреть отчеты баеров"


class EditReportCb(CallbackData, prefix="edit"):
    report_id: int


class GroupCb(CallbackData, prefix="grp"):
    chat_id: int


class BuyerCb(CallbackData, prefix="buyer"):
    user_id: int


class BackToGroupsCb(CallbackData, prefix="groups"):
    pass


def main_menu(role: Role) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    if role == Role.BUYER:
        kb.button(text=BTN_NEW_REPORT)
        kb.button(text=BTN_LAST_REPORT)
    else:
        kb.button(text=BTN_VIEW_REPORTS)
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True, is_persistent=True)


def edit_report_kb(report_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Изменить", callback_data=EditReportCb(report_id=report_id))
    return kb.as_markup()


def groups_kb(groups: list[Group]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for group in groups:
        kb.button(text=group.title, callback_data=GroupCb(chat_id=group.chat_id))
    kb.adjust(1)
    return kb.as_markup()


def buyers_kb(buyers: list[tuple[User, str]], with_back: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for user, name in buyers:
        kb.button(text=name, callback_data=BuyerCb(user_id=user.tg_id))
    if with_back:
        kb.button(text="« К группам", callback_data=BackToGroupsCb())
    kb.adjust(1)
    return kb.as_markup()
