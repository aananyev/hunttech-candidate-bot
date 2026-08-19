"""
/candidate handler — создание кандидата, проверка дублей, список.
"""
import logging
import uuid
from pathlib import Path
from typing import Optional

from aiogram import F
from aiogram.filters import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.enums import ParseMode

from hunttech_candidate_bot.application import get_app
from hunttech_candidate_bot.ai.service import AIService, ParsedResume
from hunttech_candidate_bot.services.candidate_service import CandidateService
from hunttech_candidate_bot.services.duplicate_check import DuplicateCheckService
from hunttech_candidate_bot.services.file_storage import FileStorageService
from hunttech_candidate_bot.utils.cv_parser import extract_text_from_file, sanitize_text_for_cv
from hunttech_candidate_bot.telegram.handlers.fsm_candidate import CandidateCreateState, CandidateCheckState
from hunttech_candidate_bot.telegram.menu.reply import _main_reply_keyboard

logger = logging.getLogger(__name__)

# Константы
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".docx", ".pdf"}
TEMP_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "temp_cv"


async def cmd_candidate(message: Message, command: CommandObject = None, state: FSMContext = None):
    """Обработчик /candidate — главная команда работы с кандидатами."""
    subcommand = command.args.strip().lower() if command and command.args else None

    if not subcommand or subcommand == "create":
        await _start_candidate_create(message, state)
    elif subcommand == "check":
        await _start_candidate_check(message, state)
    elif subcommand == "list":
        await _show_candidate_list(message)
    else:
        await message.answer(
            "❓ *Неизвестная подкоманда.*\n\n"
            "Доступно:\n"
            "• `/candidate create` — мастер создания кандидата из резюме\n"
            "• `/candidate check` — проверить дубли по ФИО/контактам\n"
            "• `/candidate list` — список недавно созданных кандидатов",
            parse_mode=ParseMode.MARKDOWN
        )


# ===== СОЗДАНИЕ КАНДИДАТА =====


async def _build_step1_view(tg_user, recruiters: list[dict]) -> tuple[list[list[InlineKeyboardButton]], str]:
    """Общая логика: поиск рекрутера + построение клавиатуры и текста для Шага 1.
    Возвращает (kb_buttons, info_text)."""
    matched_recruiter = None

    # Сначала ищем по username (без @)
    if tg_user.username:
        for r in recruiters:
            if r.get('login') and r['login'].lower() == tg_user.username.lower():
                matched_recruiter = r
                break

    # Если не нашли по username, пробуем найти по имени (first_name + last_name)
    if not matched_recruiter and tg_user.first_name:
        tg_full_name = f"{tg_user.first_name} {tg_user.last_name or ''}".strip()
        for r in recruiters:
            if r.get('name') and r['name'].lower() == tg_full_name.lower():
                matched_recruiter = r
                break

    # Формируем клавиатуру
    if matched_recruiter:
        # Пользователь найден в HRM — показываем 2 кнопки
        # Защита от NULL в name/login
        display_name = matched_recruiter.get('name') or matched_recruiter.get('login') or 'Без имени'
        display_login = matched_recruiter.get('login') or ''
        login_suffix = f" (@{display_login})" if display_login else ""
        kb_buttons = [
            [InlineKeyboardButton(
                text=f"✅ {display_name}{login_suffix} — это я",
                callback_data=f"candidate_owner:{matched_recruiter['id']}"
            )],
            [InlineKeyboardButton(text="🔄 Изменить", callback_data="candidate_owner:change")]
        ]
        info_text = f"👤 *Шаг 1/5: Владелец кандидата*\n\nАвтоматически определен: *{display_name}{login_suffix}*\n\nНажмите \"Это я\" для подтверждения или \"Изменить\" для выбора другого рекрутера."
    else:
        # Пользователь не найден в HRM — показываем кнопку "Изменить" и подсказку
        kb_buttons = [
            [InlineKeyboardButton(
                text=f"👤 {tg_user.first_name or 'Пользователь'} (@{tg_user.username or 'без username'}) — не в HRM",
                callback_data="candidate_owner:manual"
            )],
            [InlineKeyboardButton(text="🔄 Выбрать рекрутера из списка", callback_data="candidate_owner:change")]
        ]
        info_text = f"👤 *Шаг 1/5: Выберите владельца кандидата (рекрутера)*\n\nВаш аккаунт ({tg_user.first_name or 'Пользователь'} @{tg_user.username or 'без username'}) не найден в HRM.\n\nНажмите \"Выбрать рекрутера из списка\"."

    return kb_buttons, info_text


async def _send_step1(message: Message, state: FSMContext, kb_buttons: list, info_text: str):
    """Отправляет Шаг 1 как новое сообщение (для /candidate create)."""
    await state.set_state(CandidateCreateState.owner)
    await message.answer(
        info_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons),
    )


async def _edit_step1(callback: CallbackQuery, state: FSMContext, kb_buttons: list, info_text: str):
    """Редактирует текущее сообщение на Шаг 1 (для кнопки Назад)."""
    await state.set_state(CandidateCreateState.owner)
    await callback.message.edit_text(
        info_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons),
    )


async def _start_candidate_create_with_user(message: Message, state: FSMContext, tg_user):
    """Шаг 1: выбор владельца-рекрутера (с автоопределением по переданному пользователю)."""
    app = get_app()
    if not app or not app.db:
        await message.answer("❌ База данных не подключена. Настройте через `/setup db`.")
        return

    recruiters = await _get_recruiters(app.db)
    if not recruiters:
        await message.answer("❌ В системе не найдено активных рекрутеров (sec_user).")
        return

    kb_buttons, info_text = await _build_step1_view(tg_user, recruiters)
    await _send_step1(message, state, kb_buttons, info_text)


async def _start_candidate_create_with_user_edit(callback: CallbackQuery, state: FSMContext, tg_user):
    """Шаг 1: выбор владельца-рекрутера (с автоопределением по переданному пользователю) — редактирует сообщение."""
    app = get_app()
    if not app or not app.db:
        await callback.message.edit_text("❌ База данных не подключена. Настройте через `/setup db`.")
        return

    recruiters = await _get_recruiters(app.db)
    if not recruiters:
        await callback.message.edit_text("❌ В системе не найдено активных рекрутеров (sec_user).")
        return

    kb_buttons, info_text = await _build_step1_view(tg_user, recruiters)
    await _edit_step1(callback, state, kb_buttons, info_text)


async def _start_candidate_create(message: Message, state: FSMContext):
    """Шаг 1: выбор владельца-рекрутера (с автоопределением текущего пользователя)."""
    await _start_candidate_create_with_user(message, state, message.from_user)


async def candidate_owner_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора владельца."""
    logger.info("candidate_owner_callback CALLED: data=%s, user=%s, state=%s", callback.data, callback.from_user.id, await state.get_state())
    data = callback.data.split(":")[1]
    await callback.answer()

    if data == "change":
        # Показываем полный список рекрутеров
        logger.info("candidate_owner_callback: CHANGE branch triggered")
        app = get_app()
        if not app or not app.db:
            await callback.message.edit_text("❌ База данных не подключена.")
            return
        
        recruiters = await _get_recruiters(app.db)
        if not recruiters:
            await callback.message.edit_text("❌ В системе не найдено активных рекрутеров (sec_user).")
            return
        
        logger.info("candidate_owner_callback: Found %d recruiters", len(recruiters))

        kb_buttons = []
        for r in recruiters:
            display_name = r.get('name') or r.get('login') or 'Без имени'
            display_login = r.get('login') or ''
            login_suffix = f" (@{display_login})" if display_login else ""
            kb_buttons.append([
                InlineKeyboardButton(
                    text=f"👤 {display_name}{login_suffix}",
                    callback_data=f"candidate_owner:{r['id']}",
                )
            ])
        kb_buttons.append([
            InlineKeyboardButton(text="✏️ Другой... (ввести ID вручную)", callback_data="candidate_owner:manual")
        ])
        kb_buttons.append([
            InlineKeyboardButton(text="⬅️ Назад", callback_data="candidate_owner:back")
        ])

        await callback.message.edit_text(
            "👤 *Шаг 1/5: Выберите владельца кандидата (рекрутера)*\n\n"
            "Кандидат будет заведён на этого рекрутера. "
            "После создания будет автоматически создано взаимодействие \"Новый контакт\" на него.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_buttons),
        )
        return

    if data == "back":
        # Возвращаемся к начальному экрану с автоопределением (используем пользователя callback) — редактируем сообщение
        await _start_candidate_create_with_user_edit(callback, state, callback.from_user)
        return

    if data == "manual":
        await state.set_state(CandidateCreateState.owner)
        await callback.message.edit_text(
            "✏️ *Введите Telegram ID или username рекрутера вручную:*\n\n"
            "Например: `123456789` или `@username`"
        )
        return

    # Сохраняем владельца (выбран из списка)
    owner_id = data
    app = get_app()
    recruiter_name = await _get_recruiter_name(app.db, owner_id) if app and app.db else owner_id
    await state.update_data(owner_id=owner_id, owner_name=recruiter_name)

    # Переходим к загрузке резюме
    await state.set_state(CandidateCreateState.resume_file)
    await callback.message.edit_text(
        f"📄 *Шаг 2/5: Загрузите файл резюме*\n\n"
        f"Владелец: {recruiter_name} (ID: {owner_id})\n\n"
        f"Пришлите файл резюме кандидата:\n"
        f"• Форматы: .docx, .pdf\n"
        f"• Макс. размер: 10 МБ\n\n"
        f"Или нажмите `/cancel` для отмены."
    )


async def candidate_resume_file_handler(message: Message, state: FSMContext):
    """Обработчик загрузки файла резюме."""
    logger.info("candidate_resume_file_handler called: user=%s, state=%s", message.from_user.id, await state.get_state())
    if not message.document:
        await message.answer("❌ Пришлите файл резюме (документ).")
        return

    doc = message.document
    if doc.file_size > MAX_FILE_SIZE:
        await message.answer(f"❌ Файл слишком большой ({doc.file_size / 1024 / 1024:.1f} МБ). Макс. 10 МБ.")
        return

    ext = Path(doc.file_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        await message.answer(f"❌ Неподдерживаемый формат: {ext}. Поддерживаются: .docx, .pdf")
        return

    # Скачиваем файл
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    file_id = str(uuid.uuid4())
    file_path = TEMP_DIR / f"{file_id}{ext}"

    try:
        await message.bot.download(doc, destination=file_path)
    except Exception as e:
        logger.error("Failed to download file: %s", e)
        await message.answer("❌ Не удалось скачать файл. Попробуйте ещё раз.")
        return

    await state.update_data(
        resume_file_path=str(file_path),
        resume_file_name=doc.file_name,
        resume_file_id=file_id,
    )

    # Спрашиваем про файл в формате Hunttech
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📎 Есть файл в формате Hunttech — загрузить", callback_data="candidate_format:yes")],
        [InlineKeyboardButton(text="⏭️ Нет / Пропустить", callback_data="candidate_format:no")],
    ])

    await state.set_state(CandidateCreateState.resume_format_file)
    await message.answer(
        "📎 *Шаг 3/5: Файл в формате Hunttech (опционально)*\n\n"
        "Есть ли у вас резюме кандидата в стандарте hh/HuntTech "
        "(файл для поля fileCV в CandidateCVEdit)?\n\n"
        "Если да — загрузите его. Если нет — нажмите \"Пропустить\".",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=kb,
    )


async def candidate_format_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора про файл в формате Hunttech."""
    logger.debug("candidate_format_callback called: data=%s, user=%s, state=%s", callback.data, callback.from_user.id, await state.get_state())
    action = callback.data.split(":")[1]
    await callback.answer()

    if action == "yes":
        await state.set_state(CandidateCreateState.resume_format_file)
        await callback.message.edit_text(
            "📎 *Загрузите файл резюме в формате Hunttech:*\n\n"
            "Пришлите .doc или .docx файл.\n"
            "Или `/cancel` для отмены."
        )
    else:
        # Пропускаем, переходим к AI парсингу
        await _process_ai_parse(callback.message, state)


async def candidate_format_file_handler(message: Message, state: FSMContext):
    """Обработчик загрузки файла в формате Hunttech."""
    if not message.document:
        await message.answer("❌ Пришлите файл (документ).")
        return

    doc = message.document
    if doc.file_size > MAX_FILE_SIZE:
        await message.answer(f"❌ Файл слишком большой. Макс. 10 МБ.")
        return

    ext = Path(doc.file_name).suffix.lower()
    if ext not in {".doc", ".docx"}:
        await message.answer("❌ Формат должен быть .doc или .docx")
        return

    file_id = str(uuid.uuid4())
    file_path = TEMP_DIR / f"{file_id}{ext}"

    try:
        await message.bot.download(doc, destination=file_path)
    except Exception as e:
        logger.error("Failed to download format file: %s", e)
        await message.answer("❌ Не удалось скачать файл.")
        return

    await state.update_data(
        format_file_path=str(file_path),
        format_file_name=doc.file_name,
        format_file_id=file_id,
    )

    await _process_ai_parse(message, state)


async def _process_ai_parse(message: Message, state: FSMContext):
    """Шаг 4: Парсинг резюме через AI."""
    data = await state.get_data()
    resume_path = Path(data["resume_file_path"])

    await message.answer("🤖 *Шаг 4/5: Парсинг резюме через AI...*\n\nИзвлекаю текст и анализирую...")

    try:
        # Извлекаем текст
        resume_text = extract_text_from_file(resume_path)
        if not resume_text.strip():
            await message.answer("❌ Не удалось извлечь текст из файла. Попробуйте другой файл.")
            return

        # Парсим через AI
        app = get_app()
        if not app or not app.ai_service:
            await message.answer("❌ AI сервис не настроен. Настройте через `/setup ai`.")
            return

        parsed = await app.ai_service.parse_resume(
            resume_text,
            user_id=message.from_user.id,
            username=message.from_user.username or "",
        )

        await state.update_data(parsed_resume=parsed.to_dict())

        # Шаг 5: Подтверждение
        await _show_confirmation(message, state, parsed)

    except Exception as e:
        logger.exception("AI parse failed: %s", e)
        await message.answer(f"❌ Ошибка при парсинге резюме:\n`{e}`\n\nПопробуйте ещё раз или `/cancel`.")


async def _show_confirmation(message: Message, state: FSMContext, parsed: ParsedResume):
    """Шаг 5: Показать подтверждение данных."""
    data = await state.get_data()
    owner_name = data.get("owner_name", "?")

    lines = [
        "✅ *Шаг 5/5: Подтвердите данные*\n",
        f"👤 Владелец: {owner_name}",
        f"👤 Кандидат: {parsed.full_name()}",
    ]

    if parsed.email:
        lines.append(f"📧 Email: {parsed.email}")
    if parsed.phone:
        lines.append(f"📞 Телефон: {parsed.phone}")
    if parsed.mobile_phone:
        lines.append(f"📱 Моб.: {parsed.mobile_phone}")
    if parsed.telegram_name:
        lines.append(f"💬 Telegram: @{parsed.telegram_name}")
    if parsed.city:
        lines.append(f"🏙 Город: {parsed.city}")
    if parsed.current_company:
        lines.append(f"🏢 Компания: {parsed.current_company}")
    if parsed.position:
        lines.append(f"💼 Должность: {parsed.position}")
    if parsed.salary_expectations:
        lines.append(f"💰 ЗП: {parsed.salary_expectations}")
    if parsed.skills:
        lines.append(f"🛠 Навыки: {', '.join(parsed.skills[:10])}{'...' if len(parsed.skills) > 10 else ''}")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Создать кандидата", callback_data="candidate_confirm:create")],
        [InlineKeyboardButton(text="✏️ Исправить поле", callback_data="candidate_confirm:edit")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="candidate_confirm:cancel")],
    ])

    await state.set_state(CandidateCreateState.confirm)
    await message.answer("\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


async def candidate_confirm_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик подтверждения."""
    action = callback.data.split(":")[1]
    await callback.answer()

    if action == "cancel":
        await state.clear()
        await callback.message.edit_text("❌ *Создание кандидата отменено.*")
        return

    if action == "edit":
        # TODO: реализовать редактирование отдельных полей
        await callback.message.edit_text(
            "✏️ *Редактирование полей пока не реализовано.*\n\n"
            "Нажмите `/candidate create` для начала заново."
        )
        return

    if action == "create":
        await _create_candidate_final(callback.message, state)


async def _create_candidate_final(message: Message, state: FSMContext):
    """Шаг 6: Создание кандидата в БД."""
    data = await state.get_data()

    parsed_dict = data.get("parsed_resume", {})
    parsed = ParsedResume(**parsed_dict)

    owner_id = data.get("owner_id")
    owner_name = data.get("owner_name")
    resume_path = Path(data["resume_file_path"])
    resume_name = data["resume_file_name"]
    format_path = Path(data["format_file_path"]) if data.get("format_file_path") else None
    format_name = data.get("format_file_name")

    await message.edit_text("⏳ *Создаю кандидата в БД...*\n\nПроверка дублей...")

    try:
        app = get_app()
        if not app or not app.db:
            await message.edit_text("❌ База данных не подключена.")
            return

        # Проверка дублей
        duplicate_check = DuplicateCheckService(app.db)
        duplicates = await duplicate_check.check_duplicates(parsed)

        if duplicates:
            report = duplicate_check.format_duplicates_report(duplicates)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⚠️ Создать всё равно", callback_data="candidate_dup:force")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="candidate_dup:cancel")],
            ])
            await state.update_data(force_create=True)
            await message.edit_text(report, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
            return

        # Создаём кандидата
        await message.edit_text("⏳ *Создаю кандидата в БД...*\n\nЗапись в базу...")

        candidate_service = CandidateService(app.db, TEMP_DIR.parent)
        result = await candidate_service.create_candidate(
            resume=parsed,
            owner_id=owner_id,
            owner_name=owner_name,
            original_file_path=resume_path,
            original_file_name=resume_name,
            format_file_path=format_path,
            format_file_name=format_name,
        )

        # Успех
        await message.edit_text(
            f"✅ *Кандидат успешно создан!*\n\n"
            f"👤 Кандидат: {parsed.full_name()}\n"
            f"🆔 ID: `{result.candidate_id}`\n"
            f"👤 Владелец: {owner_name}\n"
            f"📄 CV ID: `{result.cv_id}`\n"
            f"📎 Оригинал: {'✅' if result.original_file_id else '—'}\n"
            f"📎 Формат Hunttech: {'✅' if result.format_file_id else '—'}\n"
            f"🤝 Взаимодействие: \"Новый контакт\" (ID: `{result.iteraction_id}`)\n\n"
            f"ℹ️ Автовзаимодействие создано с рейтингом 4 (максимум).",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_main_reply_keyboard()
        )

        # Чистим временные файлы
        _cleanup_temp_files(data)

        await state.clear()

    except Exception as e:
        logger.exception("Candidate creation failed: %s", e)
        await message.edit_text(
            f"❌ *Ошибка при создании кандидата:*\n`{e}`\n\n"
            f"Проверьте логи и попробуйте ещё раз."
        )


async def candidate_dup_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик решения по дублю."""
    action = callback.data.split(":")[1]
    await callback.answer()

    if action == "cancel":
        await state.clear()
        await callback.message.edit_text("❌ *Создание отменено из-за возможного дубля.*")
        return

    if action == "force":
        # Принудительное создание
        data = await state.get_data()
        data["force_create"] = True
        await state.set_data(data)
        await _create_candidate_final(callback.message, state)


# ===== ПРОВЕРКА ДУБЛЕЙ =====

async def _start_candidate_check(message: Message, state: FSMContext):
    """Начать проверку дублей."""
    await state.set_state(CandidateCheckState.resume_file)
    await message.answer(
        "🔍 *Проверка дублей*\n\n"
        "Пришлите файл резюме (.docx или .pdf) для проверки дублей по ФИО, email, телефону и Telegram.\n\n"
        "Или `/cancel` для отмены."
    )


async def candidate_check_file_handler(message: Message, state: FSMContext):
    """Обработчик файла для проверки дублей."""
    if not message.document:
        await message.answer("❌ Пришлите файл резюме (документ).")
        return

    doc = message.document
    if doc.file_size > MAX_FILE_SIZE:
        await message.answer(f"❌ Файл слишком большой. Макс. 10 МБ.")
        return

    ext = Path(doc.file_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        await message.answer(f"❌ Неподдерживаемый формат: {ext}. Поддерживаются: .docx, .pdf")
        return

    file_id = str(uuid.uuid4())
    file_path = TEMP_DIR / f"{file_id}{ext}"

    try:
        await message.bot.download(doc, destination=file_path)
    except Exception as e:
        logger.error("Failed to download file: %s", e)
        await message.answer("❌ Не удалось скачать файл.")
        return

    await state.update_data(check_file_path=str(file_path))

    await message.answer("🤖 *Парсинг и проверка дублей...*")
    await _process_check(message, state)


async def _process_check(message: Message, state: FSMContext):
    """Обработка проверки дублей."""
    data = await state.get_data()
    file_path = Path(data["check_file_path"])

    try:
        resume_text = extract_text_from_file(file_path)
        if not resume_text.strip():
            await message.answer("❌ Не удалось извлечь текст из файла.")
            return

        app = get_app()
        if not app or not app.ai_service:
            await message.answer("❌ AI сервис не настроен. Настройте через `/setup ai`.")
            return

        parsed = await app.ai_service.parse_resume(
            resume_text,
            user_id=message.from_user.id,
            username=message.from_user.username or "",
        )

        if not app.db:
            await message.answer("❌ База данных не подключена.")
            return

        duplicate_check = DuplicateCheckService(app.db)
        duplicates = await duplicate_check.check_duplicates(parsed)

        report = duplicate_check.format_duplicates_report(duplicates)
        await message.answer(report, parse_mode=ParseMode.MARKDOWN, reply_markup=_main_reply_keyboard())

        _cleanup_temp_files(data)
        await state.clear()

    except Exception as e:
        logger.exception("Duplicate check failed: %s", e)
        await message.answer(f"❌ Ошибка при проверке дублей:\n`{e}`")


# ===== СПИСОК КАНДИДАТОВ =====

async def _show_candidate_list(message: Message):
    """Показать список недавно созданных кандидатов."""
    app = get_app()
    if not app or not app.db:
        await message.answer("❌ База данных не подключена.")
        return

    try:
        async with app.db.acquire() as conn:
            rows = await conn.fetch("""
                SELECT jc.id, jc.first_name, jc.middle_name, jc.second_name, jc.full_name,
                       jc.email, jc.phone, jc.create_ts,
                       cv.id as cv_id, cv.original_file_cv_id, cv.file_cv_id
                FROM hunttech_job_candidate jc
                LEFT JOIN hunttech_candidate_cv cv ON cv.candidate_id = jc.id
                WHERE jc.delete_ts IS NULL
                ORDER BY jc.create_ts DESC
                LIMIT 20
            """)

        if not rows:
            await message.answer("📭 Кандидаты не найдены.")
            return

        lines = ["📋 *Последние кандидаты (до 20):*\n"]
        for row in rows:
            name = row["full_name"] or f"{row['second_name']} {row['first_name']} {row['middle_name'] or ''}".strip()
            lines.append(f"• *{name}* (ID: `{row['id']}`)")
            if row["email"]:
                lines.append(f"  📧 {row['email']}")
            if row["phone"]:
                lines.append(f"  📞 {row['phone']}")
            lines.append(f"  📅 {row['create_ts'].strftime('%d.%m.%Y %H:%M')}")
            lines.append("")

        await message.answer("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logger.exception("Candidate list failed: %s", e)
        await message.answer(f"❌ Ошибка при загрузке списка:\n`{e}`")


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

async def _get_recruiters(db_pool) -> list[dict]:
    """Получить список активных рекрутеров из sec_user."""
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, login, name
                FROM sec_user
                WHERE delete_ts IS NULL AND active = true
                ORDER BY name
            """)
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error("Failed to get recruiters: %s", e)
        return []


async def _get_recruiter_name(db_pool, user_id: str) -> str:
    """Получить имя рекрутера по ID."""
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT name FROM sec_user WHERE id = $1", user_id
            )
            return row["name"] if row else user_id
    except Exception:
        return user_id


def _cleanup_temp_files(data: dict):
    """Удалить временные файлы."""
    for key in ["resume_file_path", "format_file_path", "check_file_path"]:
        path_str = data.get(key)
        if path_str:
            path = Path(path_str)
            if path.exists():
                try:
                    path.unlink()
                except Exception:
                    pass


# ===== ХЕНДЛЕРЫ ДЛЯ КНОПОК НИЖНЕГО МЕНЮ (ReplyKeyboard) =====

async def cmd_candidate_create_from_button(message: Message, state: FSMContext):
    """Хендлер кнопки '👤 Создать кандидата' из нижнего меню."""
    await _start_candidate_create(message, state)


async def cmd_candidate_check_from_button(message: Message, state: FSMContext):
    """Хендлер кнопки '🔍 Проверить дубли' из нижнего меню."""
    await _start_candidate_check(message, state)


async def cmd_candidate_list_from_button(message: Message):
    """Хендлер кнопки '📋 Мои кандидаты' из нижнего меню."""
    await _show_candidate_list(message)