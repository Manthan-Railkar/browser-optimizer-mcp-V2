"""
Configuration settings module for the Browser Optimizer MCP.
Loads environment variables from .env file and sets defaults.
"""

from dotenv import load_dotenv
import os

load_dotenv()


class Settings:
    """
    Settings container managing settings values loaded from env.
    Provides sane defaults for logging, browser execution, caching, and timeouts.
    """
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    HEADLESS = os.getenv("HEADLESS", "True") == "True"
    CACHE_ENABLED = os.getenv("CACHE_ENABLED", "True") == "True"
    CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))
    CACHE_MAX_SIZE = int(os.getenv("CACHE_MAX_SIZE", "100"))
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    BROWSER_TIMEOUT = int(os.getenv("BROWSER_TIMEOUT", "30000"))


# Instantiated settings for export
settings = Settings()