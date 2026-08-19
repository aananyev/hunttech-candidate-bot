"""
/usage handler — расходы на нейросеть (админ).
"""
import logging

from aiogram.filters import CommandObject
from aiogram.types import Message

from hunttech_candidate_bot.application import get_app
from hunttech_bot_common.ai import usage_period_from_args, format_usage_report

logger = logging.getLogger(__name__)


async def cmd_usage(message: Message, command: CommandObject = None):
    """Показать расходы на нейросеть за период."""
    # Проверка прав админа
    app = get_app()
    am = app.access_manager if app else None
    if am and not am.is_admin(message.from_user.id):
        await message.answer("❌ *Команда `/usage` доступна только администратору.*")
        return

    period = usage_period_from_args(command.args if command else None)
    if not period:
        await message.answer(
            "❓ *Неверный формат периода.*\n\n"
            "Примеры:\n"
            "  `/usage` — за сегодня\n"
            "  `/usage week` — за 7 дней\n"
            "  `/usage month` — за 30 дней\n"
            "  `/usage all` — за всё время\n"
            "  `/usage 14` — за 14 дней"
        )
        return

    try:
        report = format_usage_report(period)
        await message.answer(report + "\n\n✅ *Отчёт загружен.*")
    except Exception as e:
        logger.exception("Usage report failed: %s", e)
        await message.answer(f"❌ *Ошибка при формировании отчёта:*\n`{e}`")


async def cmd_usage_from_button(message: Message):
    """Хендлер кнопки '📊 Статистика (/usage)' из нижнего меню."""
    command = CommandObject(command="usage", args=None)
    await cmd_usage(message, command)