from datetime import date, datetime, timezone

from aiogram.types import User as TgUser
from sqlalchemy import and_, exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Group, Report, Role, Template, Topic, User


async def get_user(session: AsyncSession, tg_id: int) -> User | None:
    return await session.get(User, tg_id)


async def upsert_user(
    session: AsyncSession,
    tg_user: TgUser,
    role: Role,
    group_id: int | None = None,
    topic_id: int | None = None,
) -> User:
    values = dict(
        full_name=tg_user.full_name,
        username=tg_user.username,
        role=role,
        group_id=group_id,
        topic_id=topic_id,
    )
    stmt = insert(User).values(tg_id=tg_user.id, **values)
    stmt = stmt.on_conflict_do_update(index_elements=[User.tg_id], set_=values)
    await session.execute(stmt)
    return await session.get(User, tg_user.id, populate_existing=True)


async def upsert_group(session: AsyncSession, chat_id: int, title: str) -> None:
    stmt = insert(Group).values(chat_id=chat_id, title=title)
    stmt = stmt.on_conflict_do_update(index_elements=[Group.chat_id], set_={"title": title})
    await session.execute(stmt)


async def get_group(session: AsyncSession, chat_id: int) -> Group | None:
    return await session.get(Group, chat_id)


async def update_group_title(session: AsyncSession, chat_id: int, title: str) -> None:
    group = await session.get(Group, chat_id)
    if group:
        group.title = title


async def upsert_topic(session: AsyncSession, chat_id: int, thread_id: int, name: str) -> None:
    stmt = insert(Topic).values(chat_id=chat_id, thread_id=thread_id, name=name)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Topic.chat_id, Topic.thread_id], set_={"name": name}
    )
    await session.execute(stmt)


async def get_template(session: AsyncSession, chat_id: int) -> str | None:
    template = await session.get(Template, chat_id)
    return template.text if template else None


async def set_template(session: AsyncSession, chat_id: int, text: str) -> None:
    stmt = insert(Template).values(chat_id=chat_id, text=text)
    stmt = stmt.on_conflict_do_update(index_elements=[Template.chat_id], set_={"text": text})
    await session.execute(stmt)


async def list_admins(session: AsyncSession) -> list[User]:
    result = await session.scalars(select(User).where(User.role == Role.ADMIN))
    return list(result)


async def list_groups(session: AsyncSession) -> list[Group]:
    result = await session.scalars(select(Group).order_by(Group.title))
    return list(result)


def _buyers_query():
    return (
        select(User, Topic.name)
        .outerjoin(Topic, and_(Topic.chat_id == User.group_id, Topic.thread_id == User.topic_id))
        .where(User.role == Role.BUYER)
    )


def _with_names(rows) -> list[tuple[User, str]]:
    return [(user, topic_name or user.full_name) for user, topic_name in rows]


async def list_buyers(session: AsyncSession, group_id: int) -> list[tuple[User, str]]:
    rows = await session.execute(_buyers_query().where(User.group_id == group_id))
    return sorted(_with_names(rows), key=lambda item: item[1].lower())


async def buyer_name(session: AsyncSession, user: User) -> str:
    if user.group_id is not None and user.topic_id is not None:
        topic = await session.get(Topic, (user.group_id, user.topic_id))
        if topic:
            return topic.name
    return user.full_name


async def buyers_without_report(session: AsyncSession, report_date: date) -> list[tuple[User, str]]:
    has_report = exists().where(Report.user_id == User.tg_id, Report.report_date == report_date)
    rows = await session.execute(
        _buyers_query().where(User.group_id.is_not(None), ~has_report)
    )
    return _with_names(rows)


async def create_report(session: AsyncSession, user_id: int, report_date: date, text: str) -> Report:
    report = Report(user_id=user_id, report_date=report_date, text=text)
    session.add(report)
    await session.flush()
    return report


async def get_report(session: AsyncSession, report_id: int) -> Report | None:
    return await session.get(Report, report_id)


async def last_reports(session: AsyncSession, user_id: int, limit: int) -> list[Report]:
    result = await session.scalars(
        select(Report)
        .where(Report.user_id == user_id)
        .order_by(Report.created_at.desc(), Report.id.desc())
        .limit(limit)
    )
    return list(result)


async def last_report(session: AsyncSession, user_id: int) -> Report | None:
    reports = await last_reports(session, user_id, 1)
    return reports[0] if reports else None


def mark_updated(report: Report, text: str) -> None:
    report.updated_text = text
    report.updated_at = datetime.now(timezone.utc)
