"""
/user handler — управление доступом пользователей (только для администратора).
"""
import logging
import zlib

from aiogram.enums import ParseMode
from aiogram.filters import CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from hunttech_candidate_bot.application import get_app
from hunttech_bot_common.users.access import AccessManager
from hunttech_bot_common.telegram import escape_md_simple

logger = logging.getLogger(__name__)


def _invite_key(username: str) -> int:
    """Стабильный отрицательный ключ для приглашения по username."""
    return -zlib.crc32(username.strip().lower().encode("utf-8"))


async def cmd_user(message: Message, command: CommandObject = None):
    """Обработчик /user — управление доступом (только администратор)."""
    user_id = message.from_user.id
    app = get_app()
    if not app or not app.access_manager:
        await message.answer("❌ *Система управления доступом не настроена.*")
        return

    am: AccessManager = app.access_manager

    # Проверка прав: только администратор
    if not am.is_admin(user_id):
        await message.answer("❌ *Команда доступна только администратору.*")
        return

    # Разбор аргументов
    args = (command.args or "").strip().split(maxsplit=1) if command else []
    if not args:
        await _show_user_help(message, am)
        return

    action = args[0].lower()
    target_arg = args[1].strip() if len(args) > 1 else ""

    if action == "add":
        await _cmd_user_add(message, am, target_arg, user_id)
    elif action in ("delete", "del"):
        await _cmd_user_delete(message, am, target_arg)
    elif action == "list":
        await _cmd_user_list(message, am)
    else:
        await _show_user_help(message, am)


async def _show_user_help(message: Message, am: AccessManager):
    """Показать справку по /user."""
    await message.answer(
        "👤 *Управление доступом*\n\n"
        "Доступные команды:\n"
        "• `/user add <username>` — добавить пользователя\n"
        "• `/user delete <username>` — удалить пользователя\n"
        "• `/user list` — список разрешённых пользователей\n\n"
        f"👑 Ваш ID: `{message.from_user.id}`"
    )


async def _cmd_user_add(message: Message, am: AccessManager, target: str, added_by: int):
    """Добавить пользователя с нотификацией."""
    if not target:
        await message.answer("❌ *Укажите username.*\n\nПример: `/user add @ivanov`")
        return

    username = target.lstrip("@")

    # Проверяем, может быть это ID
    try:
        target_id = int(target)
        if am.is_allowed(target_id):
            await message.answer(
                f"ℹ️ *Пользователь `{target_id}` уже имеет доступ.*"
            )
            return

        # Добавляем по ID
        am.add_user(user_id=target_id, username="", added_by=added_by,
                    full_name=f"User#{target_id}")

        # Копируем глобальные настройки AI пользователю
        from hunttech_candidate_bot.telegram.handlers.start import _copy_global_ai_to_user
        _copy_global_ai_to_user(target_id)

        # Нотификация пользователю
        try:
            await message.bot.send_message(
                chat_id=target_id,
                text=(
                    "🎉 *Вам открыт доступ к HuntTech Candidate Bot!*\n\n"
                    "Администратор добавил вас в список пользователей.\n\n"
                    "Теперь вы можете:\n"
                    "• `/candidate create` — создать кандидата из резюме\n"
                    "• `/candidate check` — проверить дубли\n"
                    "• `/help` — все команды\n\n"
                    "Напишите `/start`, чтобы начать работу."
                ),
                parse_mode=ParseMode.MARKDOWN,
            )
            # Сразу после выдачи доступа — приветствие с /help (стандарт HuntTech)
            try:
                from hunttech_candidate_bot.telegram.handlers.start import WELCOME_TEXT

                await message.bot.send_message(
                    chat_id=target_id,
                    text=WELCOME_TEXT,
                    parse_mode=None,
                )
            except Exception:
                pass
            await message.answer(
                f"✅ *Пользователь добавлен!*\n\n"
                f"ID: `{target_id}`\n"
                f"🎉 Уведомление отправлено.\n\n"
                f"ℹ️ *Что дальше:* рекрутер получил уведомление о доступе. "
                f"Если он ещё не писал боту — попросите его открыть чат с ботом "
                f"и нажать `/start`: он увидит приветствие и сможет "
                f"самостоятельно создавать кандидатов (`/candidate create`, `/candidate check`).",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.warning("Failed to notify user %s: %s", target_id, e)
            await message.answer(
                f"✅ *Пользователь добавлен!*\n\n"
                f"ID: `{target_id}`\n"
                f"⚠️ Не удалось отправить уведомление (пользователь не запускал бота).\n\n"
                f"ℹ️ *Что дальше:* попросите рекрутера написать боту `/start` — "
                f"бот поприветствует его и выдаст доступ автоматически, после чего "
                f"он сможет создавать кандидатов.",
                parse_mode=ParseMode.MARKDOWN,
            )
        return
    except ValueError:
        pass

    # Добавляем по username: уникальный отрицательный ключ
    invite_id = _invite_key(username)
    am.add_user(user_id=invite_id, username=username, added_by=added_by,
                full_name=f"@{username}")
    await message.answer(
        f"✅ `@{username}` добавлен в список доступа.\n\n"
        f"После того как @{escape_md_simple(username)} впервые напишет боту, "
        f"бот активирует его автоматически.\n\n"
        f"ℹ️ *Что дальше:* попросите рекрутера написать боту `/start` — "
        f"он активируется в списке, получит приветствие и сможет "
        f"самостоятельно создавать кандидатов (`/candidate create`, `/candidate check`).\n\n"
        f"ℹ️ Если пользователь уже писал боту — уточните ID:\n"
        f"`/user add <числовой_id>`",
        parse_mode=ParseMode.MARKDOWN,
    )


async def _cmd_user_delete(message: Message, am: AccessManager, target: str):
    """Удалить пользователя."""
    if not target:
        await message.answer("❌ *Укажите username или ID.*\n\nПример: `/user delete @ivanov`")
        return

    username = target.lstrip("@")

    try:
        target_id = int(target)
        if am.remove_user(target_id):
            await message.answer(
                f"✅ *Пользователь `{target_id}` удалён из списка доступа.*\n\n"
                f"ℹ️ *Что дальше:* доступ рекрутера отозван. Если он напишет "
                f"боту `/start`, то увидит «🚫 Доступ запрещён» и сможет "
                f"отправить запрос на доступ — он придёт вам на подтверждение "
                f"(кнопки «Разрешить / Запретить»).",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await message.answer(f"❌ *Пользователь `{target_id}` не найден.*",
                                 parse_mode=ParseMode.MARKDOWN)
        return
    except ValueError:
        pass

    # Поиск по username
    found = None
    for u in am.get_allowed_users():
        if (u.get("username") or "").lower() == username.lower():
            found = u
            break
    if found:
        am.remove_user(found["user_id"])
        await message.answer(
            f"✅ `@{username}` удалён из списка доступа.\n\n"
            f"ℹ️ *Что дальше:* доступ рекрутера отозван. Если он напишет "
            f"боту `/start`, то увидит «🚫 Доступ запрещён» и сможет "
            f"отправить запрос на доступ — он придёт вам на подтверждение.",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await message.answer(f"❌ Пользователь `@{username}` не найден.",
                             parse_mode=ParseMode.MARKDOWN)


async def _cmd_user_list(message: Message, am: AccessManager):
    """Показать список разрешённых пользователей с кнопками удаления."""
    users = am.get_allowed_users()
    waiting = [r for r in am.get_pending_requests() if r.get("status") != "denied"]
    if not users and not waiting:
        await message.answer(
            "📭 *Список разрешённых пользователей пуст.*\n\n"
            "Добавьте первого рекрутера:\n"
            "`/user add @username` или `/user add <telegram_id>`\n\n"
            "ℹ️ После выдачи доступа рекрутер должен написать "
            "боту `/start` — он получит приветствие и сможет "
            "самостоятельно создавать кандидатов "
            "(`/candidate create`, `/candidate check`).",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    active = []
    pending = []
    for u in users:
        # Неактивированные приглашения имеют отрицательный ключ или 0
        if u.get("user_id", 0) <= 0:
            pending.append(u)
        else:
            active.append(u)

    lines = ["👥 *Разрешённые пользователи:*\n"]

    if active:
        lines.append("✅ *Активные:*")
        for u in active:
            name = u.get("full_name") or u.get("username") or ""
            try:
                chat = await message.bot.get_chat(u.get("user_id"))
                tg_name = chat.full_name or chat.first_name or ""
                if tg_name and tg_name != name:
                    name = tg_name
                    am.add_user(user_id=u.get("user_id"), username=u.get("username"),
                                full_name=tg_name, added_by=u.get("added_by"))
            except Exception:
                pass
            if not name:
                name = f"User#{u.get('user_id')}"
            lines.append(f"  • `{u.get('user_id')}` — `{name}`")
        lines.append("")

    if pending:
        lines.append("⏳ *Ожидают активации:*")
        for u in pending:
            lines.append(f"  • `@{u.get('username')}` (не написал(а) боту)")
        lines.append("")
        lines.append("ℹ️ После первого `/start` пользователь активируется автоматически.\n")

    lines.append(f"👑 *Администраторы:* ID {am.get_admin_ids()}")

    # Запросы на доступ, ожидающие одобрения администратора
    if waiting:
        lines.append("")
        lines.append("⏳ *Ожидают одобрения (запросы доступа):*")
        for r in waiting:
            uname = f" `@{r.get('username')}`" if r.get("username") else ""
            fname = escape_md_simple(r.get("first_name") or "?")
            lines.append(f"  • `{r.get('user_id')}`{uname} — {fname}")
        lines.append("")
        lines.append("Кнопки под списком: ✅ — выдать доступ, ❌ — отклонить запрос.")

    lines.append("")
    lines.append("ℹ️ Пользователи со статусом «активны» могут самостоятельно "
                 "создавать кандидатов (`/candidate create`, `/candidate check`). "
                 "«Ожидают активации» — ещё не писали боту: попросите их "
                 "нажать `/start`, и доступ активируется автоматически.")

    # Клавиатура: удаление активных + одобрение/отклонение запросов
    kb_buttons = []
    for u in active:
        name = u.get("full_name") or u.get("username") or f"User#{u.get('user_id')}"
        short_name = name[:30]
        kb_buttons.append([
            InlineKeyboardButton(
                text=f"❌ {short_name}",
                callback_data=f"userlist:del:{u.get('user_id')}",
            ),
        ])
    for r in waiting:
        uid = r.get("user_id")
        uname = r.get("username") or uid
        kb_buttons.append([
            InlineKeyboardButton(
                text=f"✅ {uname}",
                callback_data=f"userlist:approve:{uid}",
            ),
            InlineKeyboardButton(
                text=f"❌ {uname}",
                callback_data=f"userlist:deny:{uid}",
            ),
        ])

    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons) if kb_buttons else None
    await message.answer("\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


# ── Callback: удаление из списка ────────────────────────────────────────

async def userlist_callback(callback: CallbackQuery):
    """Обработчик userlist:del — удалить пользователя из списка и уведомить."""
    parts = callback.data.split(":")
    action = parts[1]
    target_user_id = int(parts[2])

    app = get_app()
    if not app or not app.access_manager:
        await callback.answer("❌ Система доступа не настроена.")
        return

    am = app.access_manager
    admin_id = callback.from_user.id

    # Проверка прав
    if not am.is_admin(admin_id):
        await callback.answer("❌ Только администратор может управлять доступом.", show_alert=True)
        return

    if action == "approve":
        if am.approve_request(target_user_id, approved_by=admin_id):
            # Уведомление пользователю о доступе
            try:
                await callback.bot.send_message(
                    chat_id=target_user_id,
                    text=("📨 *Вам предоставлен доступ к боту!*\n\n"
                          "Нажмите `/start` — бот поприветствует вас, и вы "
                          "сможете самостоятельно создавать кандидатов "
                          "(`/candidate create`, `/candidate check`)."),
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception:
                pass
            # Приветственное сообщение с /help
            try:
                from hunttech_candidate_bot.telegram.handlers.start import WELCOME_TEXT

                await callback.bot.send_message(
                    chat_id=target_user_id,
                    text=WELCOME_TEXT,
                    parse_mode=None,
                )
            except Exception:
                pass
            await callback.message.edit_text(
                f"✅ *Пользователь `{target_user_id}` получил доступ.*\n\n"
                f"ℹ️ *Что дальше:* уведомление отправлено. Если пользователь "
                f"ещё не писал боту — попросите его нажать `/start`: он "
                f"активируется и сможет создавать кандидатов "
                f"(`/candidate create`, `/candidate check`).\n\n"
                f"ℹ️ Обновите список: `/user list`",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await callback.message.edit_text(
                f"❌ *Запрос пользователя `{target_user_id}` не найден.*",
                parse_mode=ParseMode.MARKDOWN,
            )
        return

    if action == "deny":
        if am.deny_request(target_user_id):
            await callback.message.edit_text(
                f"❌ *Запрос пользователя `{target_user_id}` отклонён.*\n\n"
                f"ℹ️ *Что дальше:* доступ не выдан. Если пользователь напишет "
                f"боту `/start`, он увидит «🚫 Доступ запрещён».\n\n"
                f"ℹ️ Обновите список: `/user list`",
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await callback.message.edit_text(
                f"❌ *Запрос пользователя `{target_user_id}` не найден.*",
                parse_mode=ParseMode.MARKDOWN,
            )
        return

    if action == "del":
        if am.remove_user(target_user_id):
            # Уведомление удалённому пользователю
            try:
                await callback.bot.send_message(
                    chat_id=target_user_id,
                    text="🚫 *Доступ к боту отозван.*\n\n"
                         "Администратор отключил вас от HuntTech Candidate Bot.\n"
                         "Если это ошибка — обратитесь к @AlekseyAnanyev.",
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception:
                pass

            await callback.message.edit_text(
                f"✅ *Пользователь `{target_user_id}` удалён.*\n"
                f"Уведомление отправлено.\n\n"
                f"ℹ️ *Что дальше:* доступ рекрутера отозван. При попытке "
                f"`/start` он увидит «🚫 Доступ запрещён» и сможет отправить "
                f"запрос на доступ — он придёт вам на подтверждение.\n\n"
                f"ℹ️ Обновите список: `/user list`",
            )
        else:
            await callback.message.edit_text(
                f"❌ *Пользователь `{target_user_id}` не найден.*"
            )
        await callback.answer()