from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from bot.db.models import Group, Role, User

BTN_NEW_REPORT = "Создать новый отчет"
BTN_LAST_REPORT = "Посмотреть последний отчет"
BTN_VIEW_REPORTS = "Посмотреть отчеты баеров"
BTN_ASK = "Разослать вопрос"


class EditReportCb(CallbackData, prefix="edit"):
    report_id: int


class GroupCb(CallbackData, prefix="grp"):
    chat_id: int


class BuyerCb(CallbackData, prefix="buyer"):
    user_id: int


class BackToGroupsCb(CallbackData, prefix="groups"):
    pass


class AskToggleCb(CallbackData, prefix="ask_pick"):
    user_id: int


class AskAllCb(CallbackData, prefix="ask_all"):
    select: bool


class AskDoneCb(CallbackData, prefix="ask_done"):
    pass


class AskCancelCb(CallbackData, prefix="ask_cancel"):
    pass


class AnswerCb(CallbackData, prefix="answer"):
    delivery_id: int


def main_menu(role: Role) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    if role == Role.BUYER:
        kb.button(text=BTN_NEW_REPORT)
        kb.button(text=BTN_LAST_REPORT)
    else:
        kb.button(text=BTN_VIEW_REPORTS)
        kb.button(text=BTN_ASK)
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


def ask_buyers_kb(buyers: list[tuple[User, str]], selected: set[int]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for user, name in buyers:
        mark = "✅" if user.tg_id in selected else "◻️"
        kb.button(text=f"{mark} {name}", callback_data=AskToggleCb(user_id=user.tg_id))
    kb.adjust(1)
    all_selected = len(selected) == len(buyers)
    kb.row(
        InlineKeyboardButton(
            text="Снять выбор" if all_selected else "Выбрать всех",
            callback_data=AskAllCb(select=not all_selected).pack(),
        )
    )
    kb.row(
        InlineKeyboardButton(text=f"Готово ({len(selected)})", callback_data=AskDoneCb().pack()),
        InlineKeyboardButton(text="Отмена", callback_data=AskCancelCb().pack()),
    )
    return kb.as_markup()


def answer_kb(delivery_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Ответить", callback_data=AnswerCb(delivery_id=delivery_id))
    return kb.as_markup()
