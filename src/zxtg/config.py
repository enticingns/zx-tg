import os
from pydantic import BaseModel, Field


class Config(BaseModel):
    TELEGRAM_TOKEN: str = Field(default_factory=lambda: os.getenv("TELEGRAM_TOKEN", ""))
    DB_PATH: str = Field(default_factory=lambda: os.getenv("DB_PATH", "data/zxtg.db"))
    LOG_LEVEL: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    @classmethod
    def load(cls) -> "Config":
        return cls()


config = Config.load()
