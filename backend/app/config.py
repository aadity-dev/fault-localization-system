"""
backend/app/config.py

Centralised settings, read from environment variables (matches
docker-compose.yml and .env.example). Keep this thin -- add fields here as
later phases need them (Redis URL, geocoding API key, etc.) rather than
scattering os.getenv() calls across the codebase.
"""

import os


class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql://admin:admin@localhost:5432/gridfault"
    )
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    DATA_DIR: str = os.getenv("DATA_DIR", "data")
    ENV: str = os.getenv("ENV", "development")


settings = Settings()