"""
/help handler — многоуровневая справка с фильтрацией по правам.
"""
import logging

from aiogram.enums import ParseMode
from aiogram.filters import CommandObject
from aiogram.types import Message

from hunttech_candidate_bot.application import get_app
from hunttech_candidate_bot.telegram.menu.reply import _main_reply_keyboard
from hunttech_candidate_bot.telegram.help import render_help_overview, render_help_group, render_command_help

logger = logging.getLogger(__name__)


async def cmd_help(message: Message, command: CommandObject = None):
    """Обработчик /help. Фильтрует админ-команды по правам."""
    section = command.args.strip().lower() if command and command.args else None

    # Определяем, админ ли пользователь
    app = get_app()
    am = app.access_manager if app else None
    is_admin = am.is_admin(message.from_user.id) if am else True

    if section:
        cmd_text = render_command_help(section)
        if cmd_text:
            # Проверка: если команда admin, но пользователь не админ — скрываем
            from hunttech_candidate_bot.telegram.commands.registry import get_command
            cmd_def = get_command(section)
            if cmd_def and cmd_def.admin and not is_admin:
                await message.answer(
                    f"❌ Раздел «{section}» не найден. Доступно: system, candidate, setup",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            await message.answer(cmd_text + "\n\n✅ *Справка загружена.*", parse_mode=ParseMode.MARKDOWN)
            return
        group_text = render_help_group(section, is_admin=is_admin)
        if group_text:
            await message.answer(group_text + "\n\n✅ *Справка загружена.*", parse_mode=ParseMode.MARKDOWN)
            return
        await message.answer(
            f"❓ Раздел или команда «{section}» не найдены.\n\n"
            f"Доступные разделы: system, candidate, setup",
            parse_mode=None
        )
        return

    await message.answer(
        render_help_overview(is_admin=is_admin),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_main_reply_keyboard()
    )