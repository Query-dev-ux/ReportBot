import re
from datetime import date, datetime
from html import escape
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, Message, ReplyParameters

from bot.db.models import Report

MESSAGE_LIMIT = 4096

_FULL_DATE = re.compile(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{4}|\d{2})(?!\d)")
_SHORT_DATE = re.compile(r"(?<!\w)за\s+(\d{1,2})\.(\d{1,2})(?![\d.])", re.IGNORECASE)


def escape_text(text: str) -> str:
    return escape(text, quote=False)


def normalize_chat_id(raw: str) -> int:
    """3944138604 -> -1003944138604 (id супергруппы в Bot API)."""
    if raw.startswith("-"):
        return int(raw)
    if raw.startswith("100") and len(raw) > 12:
        return int(f"-{raw}")
    return int(f"-100{raw}")


def _make_date(day: str, month: str, year: int) -> date | None:
    try:
        return date(year, int(month), int(day))
    except ValueError:
        return None


def parse_report_date(text: str, today: date) -> date | None:
    """Ищет дату отчета: сначала в первой строке, потом во всем тексте."""
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    for chunk in (first_line, text):
        for m in _FULL_DATE.finditer(chunk):
            year = int(m[3])
            if year < 100:
                year += 2000
            if parsed := _make_date(m[1], m[2], year):
                return parsed
    # "Отчет за 14.03" — без года, только после "за" в первой строке
    for m in _SHORT_DATE.finditer(first_line):
        if parsed := _make_date(m[1], m[2], today.year):
            return parsed
    return None


def fmt_date(value: date) -> str:
    return value.strftime("%d.%m.%y")


def fmt_dt(value: datetime, tz: ZoneInfo) -> str:
    return value.astimezone(tz).strftime("%d.%m.%y %H:%M")


def report_card(report: Report, tz: ZoneInfo) -> str:
    """Отчет для просмотра в личке."""
    parts = [
        f"<b>Отчет за {fmt_date(report.report_date)}</b>",
        f"<i>Создан: {fmt_dt(report.created_at, tz)}</i>",
        "",
        escape_text(report.text),
    ]
    if report.updated_text:
        updated = f" <i>({fmt_dt(report.updated_at, tz)})</i>" if report.updated_at else ""
        parts += ["", f"<b>Обновлен</b>{updated}:", escape_text(report.updated_text)]
    return "\n".join(parts)


def updated_report_post(report: Report) -> str:
    """Обновленный отчет для публикации в группе."""
    return (
        f"<b>Отчет за {fmt_date(report.report_date)}</b>\n\n"
        f"{escape_text(report.text)}\n\n"
        f"<b>Обновлен:</b>\n"
        f"{escape_text(report.updated_text or '')}"
    )


def _cut(line: str, limit: int) -> tuple[str, str]:
    head = line[:limit]
    # не разрезаем HTML-сущность вида &amp;
    amp = head.rfind("&")
    if amp != -1 and ";" not in head[amp:]:
        head = head[:amp]
    return head, line[len(head):]


def split_html(text: str, limit: int = MESSAGE_LIMIT) -> list[str]:
    """Режет текст на куски по строкам. Теги должны не пересекать границы строк."""
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            head, line = _cut(line, limit)
            chunks.append(head)
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current or not chunks:
        chunks.append(current)
    return chunks


async def send_long(
    bot: Bot,
    chat_id: int,
    text: str,
    *,
    thread_id: int | None = None,
    reply_to: int | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Message:
    """Отправляет длинный текст частями. Возвращает первое сообщение."""
    chunks = split_html(text)
    first: Message | None = None
    for i, chunk in enumerate(chunks):
        sent = await bot.send_message(
            chat_id,
            chunk,
            message_thread_id=thread_id,
            reply_parameters=(
                ReplyParameters(message_id=reply_to, allow_sending_without_reply=True)
                if reply_to and i == 0
                else None
            ),
            reply_markup=reply_markup if i == len(chunks) - 1 else None,
        )
        first = first or sent
    return first
