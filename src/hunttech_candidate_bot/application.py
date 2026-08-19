"""
Application — DI-контейнер и жизненный цикл приложения.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from hunttech_bot_common.ai import UsageTracker
from hunttech_bot_common.config import AppSettings
from hunttech_bot_common.database import DatabasePool, PoolConfig
from hunttech_bot_common.services.db_config_service import DbConfigService
from hunttech_bot_common.users import AccessManager, get_bot_access_path

from hunttech_candidate_bot.ai.service import AIService
from hunttech_candidate_bot.database.migrations import run_candidate_bot_migrations

logger = logging.getLogger(__name__)

# ── Глобальный доступ к Application ────────────────────────────────

_app_instance: "Application | None" = None


def get_app() -> "Application | None":
    return _app_instance


def set_app(app: "Application"):
    global _app_instance
    _app_instance = app


class Application:
    """Application container."""

    def __init__(self, settings: AppSettings):
        self.settings = settings
        self.bot: Optional[Bot] = None
        self.dp: Optional[Dispatcher] = None
        self.db: Optional[DatabasePool] = None
        self.ai_service: Optional[AIService] = None
        self.access_manager: Optional[AccessManager] = None
        self.db_config_service: Optional[DbConfigService] = None
        self.channel_id: str = settings.channel_id
        # Учёт обращений к нейросети: общий реестр всех HuntTech-ботов
        self.usage_tracker = UsageTracker()
        set_app(self)

    async def setup(self):
        """Initialize Telegram bot and services."""
        self.bot = Bot(
            token=self.settings.telegram.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
        )
        # Хендлеры получают контейнер через message.bot.app
        self.bot.app = self
        storage = MemoryStorage()
        self.dp = Dispatcher(storage=storage)

        # AI Service
        ai = self.settings.ai
        if ai.api_key:
            self.ai_service = AIService(
                endpoint=ai.endpoint or "https://api.deepseek.com/v1",
                api_key=ai.api_key,
                model=ai.model or "deepseek-chat",
                timeout=ai.default_timeout,
                usage_tracker=self.usage_tracker,
            )
            logger.info("AI service initialized with model: %s", ai.model or "deepseek-chat")
        else:
            logger.warning("AI not configured — set AI_API_KEY in .env")

        # Database (PostgreSQL) — приоритет /setup db, потом .env
        data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        self.db_config_service = DbConfigService(data_path=data_dir / "db_config.json")
        db_pool_config = self.db_config_service.to_pool_config()

        if db_pool_config is None and self.settings.database and self.settings.database.url:
            db_pool_config = PoolConfig.from_url(self.settings.database.url)
            logger.info("Using DB config from .env")
        elif db_pool_config:
            logger.info("Using DB config from /setup db (%s)", data_dir / "db_config.json")

        if db_pool_config:
            self.db = DatabasePool(db_pool_config)
            try:
                await self.db.connect()
                logger.info("PostgreSQL pool connected: %s",
                            db_pool_config.dsn.split("@")[-1].split("?")[0])
                
                # Запуск миграций бота
                try:
                    await run_candidate_bot_migrations(self.db)
                    logger.info("Bot migrations completed")
                except Exception as e:
                    logger.warning("Bot migrations failed: %s", e)
                    
            except Exception as e:
                logger.warning("PostgreSQL connection failed: %s", e)
                self.db = None
        else:
            logger.info("Database not configured — run /setup db or set DATABASE_URL in .env")

        # Access control (per-bot база пользователей)
        admin_ids = getattr(self.settings, "admin_ids", []) or []
        master_id = getattr(self.settings, "master_admin_id", None) or (admin_ids[0] if admin_ids else 0)
        if master_id:
            self.access_manager = AccessManager(
                data_path=get_bot_access_path("hunttech_candidate"),
                master_admin_id=master_id,
                bot_name="HuntTech Candidate Bot",
            )
            logger.info("AccessManager initialized (master=%s, users=%d)",
                        master_id, self.access_manager.get_user_count())
        else:
            logger.warning("MASTER_ADMIN_ID not set — access control disabled")

        logger.info("Application setup complete (channel: %s)", self.channel_id)

    async def shutdown(self):
        """Graceful shutdown."""
        if self.db:
            await self.db.close()
        if self.bot:
            await self.bot.session.close()
        logger.info("Application shutdown complete")