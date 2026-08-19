"""
Stats service — статистика работы бота.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


def get_stats() -> dict:
    """Получить статистику работы бота (заглушка, расширяется при необходимости)."""
    return {
        "candidates_created": 0,
        "duplicates_checked": 0,
        "active_users": 0,
        "ai_requests_today": 0,
    }


def format_status_for_admin(stats: dict) -> str:
    """Форматировать статистику для админа."""
    lines = [
        "📊 *Статистика бота*\n",
        f"👤 Кандидатов создано: {stats.get('candidates_created', 0)}",
        f"🔍 Проверок дублей: {stats.get('duplicates_checked', 0)}",
        f"👥 Активных пользователей: {stats.get('active_users', 0)}",
        f"🤖 AI запросов сегодня: {stats.get('ai_requests_today', 0)}",
        "",
        f"🕐 Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
    ]
    return "\n".join(lines)