"""
Application configuration using pydantic-settings.
All settings are loaded from environment variables.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Get the directory containing this file (app/)
APP_DIR = Path(__file__).resolve().parent
# Project root is one level up
PROJECT_ROOT = APP_DIR.parent
# .env file path
ENV_FILE = PROJECT_ROOT / ".env"

# Load .env file into environment variables BEFORE pydantic-settings reads them
if ENV_FILE.exists():
    load_dotenv(ENV_FILE, override=True)


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # App
    app_name: str = "Nomadays SaaS API"
    debug: bool = False
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:3001"]

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

    # Google Cloud (Vertex AI — Imagen 3)
    google_application_credentials: str = ""
    google_cloud_project: str = ""
    google_cloud_location: str = "us-central1"

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
