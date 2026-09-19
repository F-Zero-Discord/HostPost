import logging
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False
        )

    discord_token: str
    server_id: int

    db_user: str
    db_password: str
    db_name: str
    db_host: str = "localhost"
    db_port: int = 3306

    # The FZD API (`src/fzd_api.py`). Both default to empty and both are
    # deliberately optional: the commands that need them are /event_setup,
    # /update_host_for_event and /remove_host_from_event, and a bot that pulls
    # this change without editing its .env should lose those three with an
    # explanation rather than refuse to start. Required settings would take
    # every command down, the job-management ones included.
    fzd_api_base_url: str = ""
    fzd_api_key: SecretStr = SecretStr("")
    fzd_api_timeout_seconds: float = 10.0

    log_level: str = "INFO"

    event_announce_channel: int | None
    engage_channel: int | None
    validation_channel: int | None
    error_alert_channel_id: int | None
    test_flag: int | None = 0
    hosting_schedule_channel: int | None
    hosting_schedule_message_id: int | None


    # An empty value in .env is None, not a startup failure: alerts are then
    # off, and the hosting board says it is not configured when a host command
    # would refresh it. The other settings stay required.
    @field_validator(
        "error_alert_channel_id", "hosting_schedule_channel", "hosting_schedule_message_id", mode="before"
    )
    @classmethod
    def empty_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        valid_levels = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
        normalized = value.upper()
        if normalized not in valid_levels:
            raise ValueError(f"Invalid log level: {value}")
        return normalized

    @property
    def db_config(self) -> dict[str, object]:
        return {
            "user": self.db_user,
            "password": self.db_password,
            "host": self.db_host,
            "db": self.db_name,
            "port": self.db_port,
            "autocommit": False,
        }


_env_file = ".env"


def use_env(name: str) -> None:
    """Read `.env.<name>` in place of `.env`, not on top of it: a setting the
    named file leaves out fails validation rather than being taken from `.env`.
    pydantic-settings skips an env file that does not exist, so a mistyped
    name is refused here.
    """
    global _env_file
    path = Path(f".env.{name}")
    if not path.is_file():
        raise FileNotFoundError(f"{path} does not exist in {Path.cwd()}")
    _env_file = str(path)
    get_settings.cache_clear()


@lru_cache
def get_settings() -> Settings:
    return Settings(_env_file=_env_file)  # type: ignore


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
