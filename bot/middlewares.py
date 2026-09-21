from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import async_sessionmaker

from bot.db import repo
from bot.db.models import Role, User


class DbMiddleware(BaseMiddleware):
    """Открывает сессию на апдейт и подгружает пользователя из БД."""

    def __init__(self, sessionmaker: async_sessionmaker) -> None:
        self.sessionmaker = sessionmaker

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.sessionmaker() as session:
            data["session"] = session
            tg_user = data.get("event_from_user")
            data["user"] = await repo.get_user(session, tg_user.id) if tg_user else None
            return await handler(event, data)


class RoleFilter(BaseFilter):
    def __init__(self, *roles: Role) -> None:
        self.roles = roles

    async def __call__(self, event: TelegramObject, user: User | None = None) -> bool:
        return user is not None and user.role in self.roles
