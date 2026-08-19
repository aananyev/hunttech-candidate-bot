"""
/cancel handler — отмена текущей FSM-операции.
"""
import logging

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from hunttech_candidate_bot.application import get_app
from hunttech_candidate_bot.telegram.menu.reply import _main_reply_keyboard

logger = logging.getLogger(__name__)


async def cmd_cancel(message: Message, state: FSMContext):
    """Отменить текущую операцию и сбросить FSM."""
    current_state = await state.get_state()
    if current_state:
        await state.clear()
        await message.answer(
            "❌ *Операция отменена.*\n\n"
            "Все введённые данные очищены.",
            parse_mode=None,
            reply_markup=_main_reply_keyboard()
        )
        logger.info("User %s cancelled state: %s", message.from_user.id, current_state)
    else:
        await message.answer(
            "ℹ️ Нет активной операции для отмены.",
            parse_mode=None,
            reply_markup=_main_reply_keyboard()
        )