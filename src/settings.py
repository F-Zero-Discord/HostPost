import logging
import sys
from functools import lru_cache

from pydantic import field_validator, SecretStr
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

    log_level: str = "INFO"
    error_alert_channel_id: int | None


    @field_validator("error_alert_channel_id", mode="before")
    @classmethod
    def empty_error_alert_channel_id_to_none(cls, value: object) -> object:
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


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
