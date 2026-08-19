"""
Reply keyboard — нижнее меню (ReplyKeyboardMarkup).
"""
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def _main_reply_keyboard() -> ReplyKeyboardMarkup:
    """Основное нижнее меню для авторизованных пользователей."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="👤 Создать кандидата"),
                KeyboardButton(text="🔍 Проверить дубли"),
            ],
            [
                KeyboardButton(text="📋 Мои кандидаты"),
                KeyboardButton(text="❓ Справка"),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие или напишите команду...",
    )


def _admin_reply_keyboard() -> ReplyKeyboardMarkup:
    """Расширенное меню для админа."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="👤 Создать кандидата"),
                KeyboardButton(text="🔍 Проверить дубли"),
            ],
            [
                KeyboardButton(text="📋 Мои кандидаты"),
                KeyboardButton(text="⚙️ Настройки (/setup)"),
            ],
            [
                KeyboardButton(text="📊 Статистика (/usage)"),
                KeyboardButton(text="❓ Справка"),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие или напишите команду...",
    )


def get_reply_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Получить клавиатуру в зависимости от прав."""
    return _admin_reply_keyboard() if is_admin else _main_reply_keyboard()