"""
Handlers package — регистрация всех хендлеров.
"""
import logging
from aiogram import Dispatcher, F
from aiogram.filters import Command

from hunttech_candidate_bot.telegram.handlers import (
    start,
    help_handler,
    cancel_handler,
    user_handler,
    setup_handler,
    usage_handler,
    candidate_handler,
)
from hunttech_candidate_bot.telegram.handlers.fsm_candidate import CandidateCreateState, CandidateCheckState
from hunttech_candidate_bot.telegram.handlers.setup_handler import AiSetupState

logger = logging.getLogger(__name__)


def register_all_handlers(dp: Dispatcher):
    """Регистрация всех хендлеров бота."""

    # ── Команды ──
    dp.message.register(start.cmd_start, Command("start"))
    dp.message.register(help_handler.cmd_help, Command("help"))
    dp.message.register(cancel_handler.cmd_cancel, Command("cancel"))
    dp.message.register(user_handler.cmd_user, Command("user"))
    dp.message.register(setup_handler.cmd_setup, Command("setup"))
    dp.message.register(usage_handler.cmd_usage, Command("usage"))
    dp.message.register(candidate_handler.cmd_candidate, Command("candidate"))

    # ── Reply Keyboard buttons (текстовые сообщения от кнопок меню) ──
    dp.message.register(candidate_handler.cmd_candidate_create_from_button, F.text == "👤 Создать кандидата")
    dp.message.register(candidate_handler.cmd_candidate_check_from_button, F.text == "🔍 Проверить дубли")
    dp.message.register(candidate_handler.cmd_candidate_list_from_button, F.text == "📋 Мои кандидаты")
    dp.message.register(help_handler.cmd_help_from_button, F.text == "❓ Справка")
    # Админские кнопки
    dp.message.register(setup_handler.cmd_setup_from_button, F.text == "⚙️ Настройки (/setup)")
    dp.message.register(usage_handler.cmd_usage_from_button, F.text == "📊 Статистика (/usage)")

    # ── Callbacks ──
    # user: userlist callbacks
    dp.callback_query.register(user_handler.userlist_callback, F.data.startswith("userlist:"))

    # setup: AI FSM callbacks
    dp.callback_query.register(setup_handler.ai_provider_callback, F.data.startswith("ai_provider:"), F.state == AiSetupState.provider)

    # candidate: FSM callbacks
    dp.callback_query.register(candidate_handler.candidate_owner_callback, F.data.startswith("candidate_owner:"))
    dp.callback_query.register(candidate_handler.candidate_format_callback, F.data.startswith("candidate_format:"), F.state == CandidateCreateState.resume_format_file)
    dp.callback_query.register(candidate_handler.candidate_confirm_callback, F.data.startswith("candidate_confirm:"), F.state == CandidateCreateState.confirm)
    dp.callback_query.register(candidate_handler.candidate_dup_callback, F.data.startswith("candidate_dup:"), F.state == CandidateCreateState.confirm)

    # ── FSM message handlers ──
    # setup AI FSM
    dp.message.register(setup_handler.ai_api_key_handler, F.state == AiSetupState.api_key)
    dp.message.register(setup_handler.ai_model_handler, F.state == AiSetupState.model)

    # candidate create FSM
    dp.message.register(candidate_handler.candidate_resume_file_handler, F.document, F.state == CandidateCreateState.resume_file)
    dp.message.register(candidate_handler.candidate_format_file_handler, F.document, F.state == CandidateCreateState.resume_format_file)

    # candidate check FSM
    dp.message.register(candidate_handler.candidate_check_file_handler, F.document, F.state == CandidateCheckState.resume_file)

    logger.info("All handlers registered")