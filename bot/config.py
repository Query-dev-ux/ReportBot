from datetime import time
from functools import cached_property
from zoneinfo import ZoneInfo

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: SecretStr
    admin_key: SecretStr

    postgres_user: str = "reportbot"
    postgres_password: SecretStr = SecretStr("reportbot")
    postgres_db: str = "reportbot"
    postgres_host: str = "db"
    postgres_port: int = 5432

    timezone: str = "Europe/Moscow"
    reminder_time: time = time(14, 0)
    general_topic_id: int = 1

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password.get_secret_value()}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @cached_property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)
