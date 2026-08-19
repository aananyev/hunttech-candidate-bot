"""
/start handler — приветствие с access gate (библиотечный flow hunttech-bot-common).
"""
import logging

from aiogram.types import Message

from hunttech_bot_common.users.telegram import start_access_gate
from hunttech_bot_common.media import send_logo

from hunttech_candidate_bot.telegram.commands.registry import get_all_commands
from hunttech_candidate_bot.telegram.menu.reply import _main_reply_keyboard

logger = logging.getLogger(__name__)

WELCOME_TEXT = (
    "🚀 HuntTech Candidate Bot\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "👋 Добро пожаловать!\n"
    "✅ Бот готов к работе!\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "📋 Назначение: заведение кандидатов в HRM HuntTech из резюме "
    "с проверкой дублей.\n"
    "\n"
    "Как это работает:\n"
    "1️⃣ /candidate create — мастер создания кандидата из резюме\n"
    "2️⃣ /candidate check — проверить дубли по ФИО/email/телефону/Telegram\n"
    "3️⃣ /candidate list — список недавно созданных кандидатов\n"
    "4️⃣ /help — все команды\n"
    "\n"
    "Напиши /help — покажу все команды."
)


async def cmd_start(message: Message):
    """Приветствие с access gate. Синхронизирует меню."""
    app = getattr(message.bot, "app", None)
    if app is None or app.access_manager is None:
        await message.answer("⚠️ Бот ещё не инициализирован. Попробуйте позже.")
        return

    # Приглашённый по username активируется при первом /start
    await _activate_invited_by_username(
        app.access_manager,
        message.from_user.id,
        message.from_user.username,
    )

    # Фото-логотип HuntTech перед приветствием (бренд; при ошибке — не мешаем)
    await send_logo(message.bot, message.from_user.id)

    result = await start_access_gate(
        event=message,
        user_id=message.from_user.id,
        access_manager=app.access_manager,
        bot=message.bot,
        commands=get_all_commands(),
        welcome_text=WELCOME_TEXT,
        parse_mode=None,
    )
    logger.info("start: user=%s -> %s", message.from_user.id, result)
    # Нижнее меню — только для авторизованных
    if result == "allowed":
        await message.answer("👇 Нижнее меню:", reply_markup=_main_reply_keyboard())


async def _activate_invited_by_username(am, user_id: int, username: str | None) -> bool:
    """Активировать приглашение по username: перенести запись на реальный ID."""
    if not username or am.is_admin(user_id) or am.is_allowed(user_id):
        return False
    for u in am.get_allowed_users():
        if u.get("user_id", 0) <= 0 and \
                (u.get("username") or "").lower() == username.lower():
            old_id = u["user_id"]
            am.add_user(
                user_id=user_id,
                username=username,
                full_name=u.get("full_name") or f"@{username}",
                added_by=u.get("added_by"),
            )
            am.remove_user(old_id)
            logger.info(
                "Invited user %s (@%s) activated by /start",
                user_id, username,
            )
            return True
    return False


def _copy_global_ai_to_user(user_id: int):
    """Скопировать глобальные настройки AI в per-user конфиг."""
    import os

    from hunttech_candidate_bot.services.ai_config import AIConfigService
    from pathlib import Path

    data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    ai_config_service = AIConfigService(data_dir)

    cfg = {
        "provider": "deepseek",
        "endpoint": os.getenv("AI_ENDPOINT", "https://api.deepseek.com/v1"),
        "api_key": os.getenv("AI_API_KEY", ""),
        "model": os.getenv("AI_MODEL", "deepseek-chat"),
    }
    if cfg["api_key"]:
        ai_config_service.save_config(user_id, cfg)
        logger.info("Global AI config copied to user %s", user_id)