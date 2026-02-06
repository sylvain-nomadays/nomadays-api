"""
Application configuration using pydantic-settings.
All settings are loaded from environment variables.
"""

from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # App
    app_name: str = "Nomadays SaaS API"
    debug: bool = False
    cors_origins: List[str] = ["http://localhost:3000"]

    # Database
    database_url: str

    # Supabase
    supabase_url: str
    supabase_key: str
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""  # JWT secret for verifying Supabase tokens

    # JWT Auth (internal tokens)
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Anthropic Claude
    anthropic_api_key: str = ""

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [origin.strip() for origin in v.split(",")]
        return v


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
