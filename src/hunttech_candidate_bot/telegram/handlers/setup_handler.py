"""
/setup handler — настройка AI-провайдера, БД, пользователей и просмотр статуса.
"""
import logging

from aiogram.filters import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from hunttech_bot_common.telegram.setup_db import (
    cmd_setup_db as common_cmd_setup_db,
    _cmd_db_show,
    _cmd_db_test,
)
from hunttech_bot_common.services.db_config_service import DbConfigService
from hunttech_bot_common.telegram import escape_md_simple

from hunttech_candidate_bot.ai.service import thinking_disabled_extra
from hunttech_candidate_bot.services import get_stats, format_status_for_admin
from hunttech_candidate_bot.services.ai_config import (
    get_user_ai_config, save_user_ai_config, clear_user_ai_config,
    format_user_ai_config, get_ai_providers, get_provider_keyboard,
)

logger = logging.getLogger(__name__)


# ── FSM состояния для настройки AI ─────────────────────────────────────────

class AiSetupState(StatesGroup):
    provider = State()   # ждём выбора провайдера (callback)
    api_key = State()    # ждём API-ключ
    model = State()      # ждём название модели


# ── Подсказки моделей для каждого провайдера ──────────────────────────────

AI_MODEL_HINTS = {
    "deepseek": ["deepseek-chat", "deepseek-reasoner", "deepseek-v3"],
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
    "openrouter": ["anthropic/claude-sonnet-4", "google/gemini-2.0-flash-001"],
    "gemini": ["gemini-2.0-flash-001", "gemini-2.0-pro", "gemini-1.5-pro"],
    "qwen": ["qwen-max", "qwen-plus", "qwen2.5-72b-instruct"],
    "custom": [],
}


# ── Команда /setup ────────────────────────────────────────────────────────

async def cmd_setup(message: Message, state: FSMContext, command: CommandObject = None):
    """Обработчик /setup (только для администратора)."""
    # Проверка прав
    from hunttech_candidate_bot.application import get_app
    app = get_app()
    am = app.access_manager if app else None
    if am and not am.is_admin(message.from_user.id):
        await message.answer("❌ *Команда `/setup` доступна только администратору.*")
        return

    if command and command.args:
        arg = command.args.strip().lower()
        # Составные подкоманды проверяем первыми
        if arg == "ai test":
            await _test_ai_connection(message)
            return
        if arg == "ai show":
            await _show_ai_config(message)
            return
        if arg == "ai":
            await _start_ai_setup(message, state)
            return
        if arg == "db show":
            try:
                await _cmd_db_show(message, DbConfigService())
            except Exception as e:
                logger.exception("DB show failed: %s", e)
                await message.answer(f"❌ *Ошибка:* `{e}`")
            return
        if arg == "db test":
            try:
                await _cmd_db_test(message, DbConfigService())
            except Exception as e:
                logger.exception("DB test failed: %s", e)
                await message.answer(f"❌ *Ошибка:* `{e}`")
            return
        if arg == "db":
            # Перенаправляем в общий FSM-мастер настройки БД
            from hunttech_candidate_bot.application import get_app
            app = get_app()
            am = app.access_manager if app else None
            try:
                await message.answer("🗄️ *Загружаю мастер настройки PostgreSQL...*")
                await common_cmd_setup_db(message, command, state, am, DbConfigService())
            except Exception as e:
                logger.exception("DB setup failed: %s", e)
                await message.answer(
                    f"❌ *Ошибка при запуске мастера БД:*\n`{e}`\n\n"
                    f"Попробуйте ещё раз или проверьте логи."
                )
            return
        if arg == "status":
            await _show_status(message)
            return
        if arg == "show":
            await _show_config(message)
            return
        if arg == "user" or arg.startswith("user "):
            # /setup user — управление доступом рекрутеров (только админ)
            await _cmd_setup_user(message, command.args)
            return
        await message.answer(
            f"❓ Неизвестная подкоманда: `{arg}`\n"
            "Доступно: `/setup ai`, `/setup ai test`, `/setup ai show`, "
            "`/setup db`, `/setup db test`, `/setup db show`, "
            "`/setup user`, `/setup status`, `/setup show`"
        )
        return

    await message.answer(
        "🔧 *Настройки*\n\n"
        "Выберите раздел:\n"
        "• `/setup ai` — настроить AI-провайдера\n"
        "• `/setup ai test` — проверить подключение к AI\n"
        "• `/setup ai show` — показать настройки AI\n"
        "• `/setup db` — настроить подключение к PostgreSQL\n"
        "• `/setup db test` — проверить подключение к БД\n"
        "• `/setup db show` — показать конфигурацию БД\n"
        "• `/setup user` — доступ рекрутеров (выдать/отозвать)\n"
        "• `/setup status` — статистика работы бота\n"
        "• `/setup show` — текущие настройки"
    )


# ── /setup user: доступ рекрутеров ────────────────────────────────────────

async def _cmd_setup_user(message: Message, args: str | None = None):
    """/setup user — предоставление доступа рекрутерам (только администратор)."""
    from hunttech_candidate_bot.application import get_app
    app = get_app()
    am = app.access_manager if app else None
    if not am:
        await message.answer("❌ *Система управления доступом не настроена.*")
        return
    if not am.is_admin(message.from_user.id):
        await message.answer("❌ *Команда доступна только администратору.*")
        return

    rest = (args or "").strip()
    if rest.lower().startswith("user"):
        rest = rest[4:].strip()
    sub = rest.split(maxsplit=1)
    action = sub[0].lower() if sub else ""

    from hunttech_candidate_bot.telegram.handlers.user_handler import (
        _cmd_user_add,
        _cmd_user_delete,
        _cmd_user_list,
    )

    if action == "add":
        target = sub[1].strip() if len(sub) > 1 else ""
        await _cmd_user_add(message, am, target, message.from_user.id)
        return
    if action in ("delete", "del", "remove"):
        target = sub[1].strip() if len(sub) > 1 else ""
        await _cmd_user_delete(message, am, target)
        return

    # default: list + справка
    await _cmd_user_list(message, am)
    await message.answer(
        "👥 *Управление доступом рекрутеров*\n\n"
        "• `/setup user add @username` — выдать доступ\n"
        "• `/setup user add <id>` — выдать доступ по Telegram ID\n"
        "• `/setup user delete @username` — отозвать доступ\n"
        "• `/setup user list` — список пользователей\n\n"
        "Рекрутер с доступом может самостоятельно создавать кандидатов "
        "(`/candidate create`), проверять дубли (`/candidate check`).\n"
        "Получить Telegram ID можно через `/user list` или попросив "
        "пользователя написать боту `/start`."
    )


# ── /setup ai: FSM-мастер ─────────────────────────────────────────────────

async def _start_ai_setup(message: Message, state: FSMContext):
    """Шаг 1: выбор провайдера."""
    await state.set_state(AiSetupState.provider)
    await message.answer(
        "🧠 *Настройка AI-провайдера*\n\n"
        "Выберите провайдера:",
        reply_markup=get_provider_keyboard(),
    )


async def ai_provider_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора провайдера (callback)."""
    provider_key = callback.data.split(":")[1]
    user_id = callback.from_user.id
    await callback.answer()

    providers = get_ai_providers()
    info = providers.get(provider_key, {})
    endpoint = info.get("endpoint", "")

    if provider_key == "custom":
        # Custom: сначала спросим endpoint
        await state.update_data(ai_provider="custom", ai_endpoint="")
        await state.set_state(AiSetupState.api_key)
        await callback.message.edit_text(
            "🔗 *Введите API Endpoint URL*\n\n"
            "Например: `https://your-provider.com/v1`"
        )
        return

    # Built-in: сохраняем endpoint, спрашиваем API-ключ
    await state.update_data(ai_provider=provider_key, ai_endpoint=endpoint)
    await state.set_state(AiSetupState.api_key)
    await callback.message.edit_text(
        f"🔑 *Введите API-ключ* для {info['label']}\n\n"
        "Отправьте API-ключ одной строкой.\n"
        "Или `/cancel` для отмены."
    )


async def ai_api_key_handler(message: Message, state: FSMContext):
    """Шаг 2: получение API-ключа."""
    api_key = message.text.strip()
    if not api_key:
        await message.answer("❌ API-ключ не может быть пустым. Попробуйте ещё раз.")
        return

    data = await state.get_data()
    provider = data.get("ai_provider", "")
    endpoint = data.get("ai_endpoint", "")

    if provider == "custom" and not endpoint:
        # Для custom: это был endpoint, а не api_key
        await state.update_data(ai_endpoint=api_key)
        await state.set_state(AiSetupState.model)
        await message.answer("🔑 *Теперь введите API-ключ* для вашего провайдера.")
        return

    # Сохраняем api_key, переходим к модели
    await state.update_data(ai_api_key=api_key)
    await state.set_state(AiSetupState.model)

    # Показываем подсказки по моделям
    hints = AI_MODEL_HINTS.get(provider, [])
    hints_section = ""
    if hints:
        items = "\n".join(f"  • `{m}`" for m in hints)
        hints_section = f"\n📋 *Популярные модели:*\n{items}\n"

    await message.answer(
        f"📝 *Введите название модели*{hints_section}\n\n"
        "Например: `deepseek-chat`"
    )


async def ai_model_handler(message: Message, state: FSMContext):
    """Шаг 3 (или 2 для custom): получение модели."""
    model = message.text.strip().lower()
    if not model:
        await message.answer("❌ Название модели не может быть пустым. Попробуйте ещё раз.")
        return

    data = await state.get_data()
    user_id = message.from_user.id

    # Если custom и ещё нет endpoint — это был api-key (2-й шаг custom)
    if data.get("ai_provider") == "custom" and not data.get("ai_endpoint"):
        # Сохраняем как api_key
        await state.update_data(ai_api_key=model)
        await message.answer("🔗 *Введите API Endpoint URL*")
        # Остаёмся в том же состоянии
        return

    # Сохраняем всё
    cfg = {
        "provider": data.get("ai_provider", "custom"),
        "endpoint": data.get("ai_endpoint", ""),
        "api_key": data.get("ai_api_key", ""),
        "model": model,
    }
    save_user_ai_config(user_id, cfg)
    await state.clear()

    # Тестируем подключение (короткий тест)
    from hunttech_bot_common.ai import AIClient
    test_msg = await message.answer("⏳ *Тестирую подключение...*")
    try:
        client = AIClient(endpoint=cfg["endpoint"], api_key=cfg["api_key"], model=model)
        response = await client.complete(
            system_prompt="Ответь одним словом.",
            user_prompt="Скажи 'OK'",
            temperature=0.1, max_tokens=50, timeout=15.0,
            extra_body=thinking_disabled_extra(client),
        )
        await test_msg.edit_text(
            f"✅ *AI-провайдер настроен!*\n\n"
            f"• Провайдер: {escape_md_simple(cfg['provider'])}\n"
            f"• Модель: `{escape_md_simple(model)}`\n"
            f"• Тест: OK («{escape_md_simple(response.content.strip())}»)"
        )
    except Exception as e:
        await test_msg.edit_text(
            f"⚠️ *Настройки сохранены*, но тест не прошёл:\n`{e}`\n\n"
            "Вы можете проверить позже через `/setup ai`."
        )


# ── /setup status ────────────────────────────────────────────────────────

async def _show_status(message: Message):
    """Показать статистику."""
    stats = get_stats()
    await message.answer(format_status_for_admin(stats) + "\n\n✅ *Статистика загружена.*")


# ── /setup show ──────────────────────────────────────────────────────────

async def _show_config(message: Message):
    """Показать текущие настройки (глобальные + пользовательские)."""
    app = getattr(message.bot, "app", None)
    user_id = message.from_user.id

    if not app:
        await message.answer("❌ Приложение не инициализировано.")
        return

    settings = app.settings
    ai_global = settings.ai
    user_ai = get_user_ai_config(user_id)

    channel_display = settings.channel_id.replace("_", "\\_")

    lines = [
        "📋 *Настройки*\n",
        f"📌 *Бот:* {settings.app_name}",
        f"📡 *Канал:* {channel_display}",
        "",
    ]

    if user_ai:
        key_status = "✅ задан" if user_ai.get("api_key") else "❌ не задан"
        lines.append(f"🧠 *Ваш AI-провайдер:* {user_ai.get('provider', '?')}")
        lines.append(f"   • Endpoint: `{user_ai.get('endpoint', '')}`")
        lines.append(f"   • API-ключ: {key_status}")
        lines.append(f"   • Модель: `{user_ai.get('model', '')}`")
    else:
        lines.append(f"🧠 *Глобальный AI:* {'✅ настроен' if ai_global.api_key else '❌ не настроен'}")
        lines.append(f"   • Endpoint: `{ai_global.endpoint or 'не указан'}`")
        lines.append(f"   • Модель: `{ai_global.model or 'не указана'}`")
        lines.append("")
        lines.append("💡 Настройте свой AI через `/setup ai` — будет использован ваш ключ.")

    await message.answer("\n".join(lines) + "\n\n✅ *Настройки загружены.*")


# ── /setup ai test ────────────────────────────────────────────────────────

async def _test_ai_connection(message: Message):
    """Проверить подключение к AI с текущими настройками."""
    from hunttech_bot_common.ai import AIClient

    user_id = message.from_user.id
    user_cfg = get_user_ai_config(user_id)

    if user_cfg and user_cfg.get("api_key"):
        endpoint = user_cfg["endpoint"]
        api_key = user_cfg["api_key"]
        model = user_cfg["model"]
        source = f"пользовательский ({user_cfg.get('provider', 'custom')})"
    else:
        app = getattr(message.bot, "app", None)
        ai = app.settings.ai if app else None
        if not ai or not ai.api_key:
            await message.answer(
                "❌ *AI не настроен.*\n\n"
                "Глобальный AI: нет API-ключа в .env\n"
                "Пользовательский AI: не настроен через `/setup ai`\n\n"
                "Настройте AI: `/setup ai`"
            )
            return
        endpoint = ai.endpoint
        api_key = ai.api_key
        model = ai.model
        source = "глобальный (.env)"

    test_msg = await message.answer(
        f"🔌 *Тест подключения к AI*\n\n"
        f"• Источник: {source}\n"
        f"• Endpoint: `{endpoint}`\n"
        f"• Модель: `{model}`\n\n"
        f"⏳ Проверяю..."
    )

    try:
        client = AIClient(endpoint=endpoint, api_key=api_key, model=model)
        response = await client.complete(
            system_prompt="Ответь одним словом.",
            user_prompt="Скажи 'OK'",
            temperature=0.1, max_tokens=50, timeout=15.0,
            extra_body=thinking_disabled_extra(client),
        )
        duration = response.duration_ms
        await test_msg.edit_text(
            f"✅ *Подключение работает!*\n\n"
            f"• Модель: `{escape_md_simple(response.model)}`\n"
            f"• Ответ: «{escape_md_simple(response.content.strip())}»\n"
            f"• Задержка: {duration} мс\n"
            f"• Провайдер: {escape_md_simple(source)}"
        )
    except Exception as e:
        await test_msg.edit_text(
            f"❌ *Тест не пройден*\n\n"
            f"`{str(e)[:300]}`\n\n"
            f"Проверьте настройки: `/setup ai show`\n"
            f"Настроить заново: `/setup ai`"
        )


# ── /setup ai show ────────────────────────────────────────────────────────

async def _show_ai_config(message: Message):
    """Показать только настройки AI."""
    user_id = message.from_user.id
    user_cfg = get_user_ai_config(user_id)
    app = getattr(message.bot, "app", None)
    ai_global = app.settings.ai if app else None

    lines = ["🧠 *Настройки AI*\n"]
    sep = "" if user_cfg else ""

    if user_cfg:
        key_status = "✅ задан" if user_cfg.get("api_key") else "❌ не задан"
        lines.append(f"📌 *Ваш AI* ({user_cfg.get('provider', 'custom')})")
        lines.append(f"   • Endpoint: `{user_cfg.get('endpoint', '')}`")
        lines.append(f"   • API-ключ: {key_status}")
        lines.append(f"   • Модель: `{user_cfg.get('model', '')}`")
        lines.append("")

    lines.append("📌 *Глобальный AI* (.env)")
    if ai_global and ai_global.api_key:
        lines.append(f"   • Endpoint: `{ai_global.endpoint or 'не указан'}`")
        lines.append(f"   • API-ключ: ✅ задан")
        lines.append(f"   • Модель: `{ai_global.model or 'не указана'}`")
    else:
        lines.append("   ❌ Не настроен")

    lines.append("")
    lines.append("🔧 `/setup ai` — изменить настройки")
    lines.append("🔌 `/setup ai test` — проверить подключение")

    await message.answer("\n".join(lines) + "\n\n✅ *Настройки загружены.*")