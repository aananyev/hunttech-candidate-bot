#!/usr/bin/env python3
"""Bootstrap — загрузка настроек приложения."""
import os
from pathlib import Path

from hunttech_bot_common.config import AppSettings, AISettings, DatabaseSettings, TelegramSettings


def bootstrap() -> AppSettings:
    """Загрузить настройки из .env и переменных окружения."""
    # Корень проекта (для .env)
    project_root = Path(__file__).resolve().parents[2]
    env_path = project_root / ".env"
    
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path)
    
    # Telegram
    telegram = TelegramSettings(
        bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        admin_ids=[int(x.strip()) for x in os.getenv("ADMIN_IDS", "272980897").split(",") if x.strip()],
    )
    
    # AI
    ai = AISettings(
        endpoint=os.getenv("AI_ENDPOINT", "https://api.deepseek.com/v1"),
        api_key=os.getenv("AI_API_KEY", ""),
        model=os.getenv("AI_MODEL", "deepseek-chat"),
        provider="deepseek",
        default_timeout=int(os.getenv("AI_TIMEOUT", "120")),
    )
    
    # Database
    database_url = os.getenv("DATABASE_URL", "")
    database = DatabaseSettings(url=database_url) if database_url else None
    
    # Admin IDs
    master_admin_id = int(os.getenv("MASTER_ADMIN_ID", "272980897"))
    
    # App settings
    settings = AppSettings(
        telegram=telegram,
        ai=ai,
        database=database,
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_json_format=os.getenv("LOG_JSON_FORMAT", "false").lower() in ("1", "true", "yes", "on"),
    )
    
    # Добавляем master_admin_id как атрибут (не в датаклассе)
    settings.master_admin_id = master_admin_id
    settings.admin_ids = telegram.admin_ids
    settings.channel_id = os.getenv("CHANNEL_ID", "@hunttech_candidates")
    
    return settings