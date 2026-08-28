from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).with_name(".env")


class Settings(BaseSettings):
    vision_provider: str = Field(default="openrouter", pattern="^(none|openrouter|openai)$")
    openrouter_api_key: str | None = None
    openrouter_vision_model: str = "google/gemini-2.5-pro"
    openrouter_max_tokens: int = 1200
    openai_api_key: str | None = None
    openai_vision_model: str = "gpt-4.1-mini"
    ocr_provider: str = Field(default="google", pattern="^(none|google)$")
    google_application_credentials: str | None = None
    google_application_credentials_json: str | None = None
    google_vision_features: str = "text,landmark,logo,label,web"
    max_image_bytes: int = 10 * 1024 * 1024
    allowed_origins: str = "http://localhost:8080"

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
