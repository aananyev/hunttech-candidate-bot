#!/usr/bin/env python3
"""
HuntTech Candidate Bot — точка входа.
Запуск: python -m hunttech_candidate_bot
"""
import asyncio
import logging
import sys
from pathlib import Path

# Добавляем корень проекта в путь для импортов
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from aiogram import Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from hunttech_bot_common.logging import setup_logging
from hunttech_bot_common.services.startup import send_startup_changelog, bot_version
from hunttech_bot_common.media import send_logo

from hunttech_candidate_bot.application import Application, get_app, set_app
from hunttech_candidate_bot.bootstrap import bootstrap
from hunttech_candidate_bot.telegram.handlers import register_all_handlers
from hunttech_candidate_bot.telegram.menu.sync import setup_default_menu, sync_all_user_menus
from hunttech_candidate_bot.telegram.commands.registry import register_all_commands

logger = logging.getLogger(__name__)


async def on_startup(app: Application):
    """Действия при старте бота."""
    # 1. Регистрация команд
    register_all_commands()
    
    # 2. Регистрация хендлеров
    register_all_handlers(app.dp)
    
    # 3. Глобальное меню команд
    await setup_default_menu(app.bot)
    
    # 4. Синхронизация меню для всех пользователей
    await sync_all_user_menus(app.bot)
    
    # 5. Логотип и приветствие админу (startup changelog)
    repo_dir = project_root
    state_path = repo_dir / "data" / "startup_state.json"
    
    admin_ids = app.settings.admin_ids
    master_id = app.settings.master_admin_id
    
    # Логотип админу
    for admin_id in admin_ids:
        try:
            await send_logo(app.bot, admin_id)
        except Exception as e:
            logger.warning("Failed to send logo to admin %s: %s", admin_id, e)
    
    # Стартовое сообщение админу с версией
    version = bot_version(repo_dir)
    for admin_id in admin_ids:
        try:
            await app.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"🚀 HuntTech Candidate Bot\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🤖 Версия бота: {version}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"✅ Бот запущен и готов к работе!\n"
                    f"🤖 AI: {app.settings.ai.model or 'не настроен'}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━"
                ),
                parse_mode=None,
            )
        except Exception as e:
            logger.warning("Failed to send startup message to admin %s: %s", admin_id, e)
    
    # Сводка изменений (changelog) для master admin
    if master_id:
        try:
            await send_startup_changelog(app.bot, master_id, repo_dir=repo_dir, state_path=state_path)
        except Exception as e:
            logger.warning("Startup changelog failed: %s", e)
    
    logger.info("Bot startup complete")


async def main():
    """Главная функция запуска."""
    # Настройка логирования
    setup_logging(level="INFO", json_format=False)
    
    # Загрузка настроек
    settings = bootstrap()
    
    if not settings.telegram.bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set in .env")
        sys.exit(1)
    
    # Создание приложения
    app = Application(settings)
    set_app(app)
    
    try:
        # Инициализация
        await app.setup()
        
        # Startup actions
        await on_startup(app)
        
        logger.info("Starting polling...")
        
        # Запуск поллинга
        await app.dp.start_polling(app.bot)
        
    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.exception("Bot crashed: %s", e)
        raise
    finally:
        await app.shutdown()
        logger.info("Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass