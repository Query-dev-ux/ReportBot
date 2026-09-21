from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import repo

router = Router()
router.message.filter(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))


@router.message()
async def track_group_changes(message: Message, session: AsyncSession) -> None:
    """Запоминает названия тем (= имена баеров) и групп по сообщениям в группе."""
    thread_id = message.message_thread_id
    name = None
    if message.forum_topic_created:
        name = message.forum_topic_created.name
    elif message.forum_topic_edited and message.forum_topic_edited.name:
        name = message.forum_topic_edited.name
    elif message.reply_to_message and message.reply_to_message.forum_topic_created:
        # обычное сообщение в теме ссылается на сервисное сообщение о создании темы
        name = message.reply_to_message.forum_topic_created.name

    changed = False
    if name and thread_id:
        await repo.upsert_topic(session, message.chat.id, thread_id, name)
        changed = True
    if message.new_chat_title:
        await repo.update_group_title(session, message.chat.id, message.new_chat_title)
        changed = True
    if changed:
        await session.commit()
