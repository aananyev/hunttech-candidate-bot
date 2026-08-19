"""
Menu sync — синхронизация бокового меню (BotCommandScopeChat).
"""
import logging

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeChat

from hunttech_candidate_bot.application import get_app
from hunttech_candidate_bot.telegram.commands.registry import get_commands_by_group

logger = logging.getLogger(__name__)


# Команды для обычного пользователя (рекрутера)
USER_COMMANDS = [
    BotCommand(command="start", description="🚀 Начать работу"),
    BotCommand(command="help", description="❓ Справка"),
    BotCommand(command="candidate", description="👤 Кандидаты: создать/проверить/список"),
    BotCommand(command="cancel", description="❌ Отменить операцию"),
]

# Команды для админа (добавляются к USER_COMMANDS)
ADMIN_COMMANDS = [
    BotCommand(command="setup", description="🔧 Настройки (AI, БД, пользователи)"),
    BotCommand(command="usage", description="💰 Расходы на нейросеть"),
    BotCommand(command="user", description="👤 Управление доступом"),
]


async def setup_default_menu(bot: Bot):
    """Настроить меню команд по умолчанию (глобальное)."""
    # Глобальное меню — только базовые команды для всех
    commands = [
        BotCommand(command="start", description="🚀 Начать работу"),
        BotCommand(command="help", description="❓ Справка"),
    ]
    await bot.set_my_commands(commands)
    logger.info("Default bot commands menu set")


async def sync_user_menu(bot: Bot, user_id: int, is_admin: bool):
    """Синхронизировать меню для конкретного пользователя (per-chat scope)."""
    commands = USER_COMMANDS.copy()
    if is_admin:
        commands.extend(ADMIN_COMMANDS)

    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=user_id))
        logger.debug("Menu synced for user %s (admin=%s)", user_id, is_admin)
    except Exception as e:
        logger.warning("Failed to sync menu for user %s: %s", user_id, e)


async def sync_all_user_menus(bot: Bot):
    """Синхронизировать меню для всех авторизованных пользователей."""
    app = get_app()
    if not app or not app.access_manager:
        return

    am = app.access_manager
    for user in am.get_allowed_users():
        user_id = user.get("user_id")
        if user_id and user_id > 0:  # только активированных
            is_admin = am.is_admin(user_id)
            await sync_user_menu(bot, user_id, is_admin)

    # Также для админов
    for admin_id in am.get_admin_ids():
        await sync_user_menu(bot, admin_id, True)

    logger.info("All user menus synced")