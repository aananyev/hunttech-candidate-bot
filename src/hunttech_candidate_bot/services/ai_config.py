"""
Per-user AI configuration service.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class AIConfigService:
    """Управление per-user настройками AI."""

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _config_path(self, user_id: int) -> Path:
        return self.data_dir / f"ai_config_{user_id}.json"

    def get_config(self, user_id: int) -> Optional[dict]:
        """Получить конфиг пользователя."""
        path = self._config_path(user_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load AI config for user %s: %s", user_id, e)
            return None

    def save_config(self, user_id: int, config: dict):
        """Сохранить конфиг пользователя."""
        path = self._config_path(user_id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            logger.info("AI config saved for user %s", user_id)
        except Exception as e:
            logger.error("Failed to save AI config for user %s: %s", user_id, e)
            raise

    def clear_config(self, user_id: int):
        """Удалить конфиг пользователя."""
        path = self._config_path(user_id)
        if path.exists():
            path.unlink()
            logger.info("AI config cleared for user %s", user_id)

    def format_config(self, config: Optional[dict]) -> str:
        """Форматировать конфиг для вывода."""
        if not config:
            return "❌ Не настроен"
        key_status = "✅ задан" if config.get("api_key") else "❌ не задан"
        return (
            f"📌 Провайдер: {config.get('provider', 'custom')}\n"
            f"   • Endpoint: `{config.get('endpoint', '')}`\n"
            f"   • API-ключ: {key_status}\n"
            f"   • Модель: `{config.get('model', '')}`"
        )


# Провайдеры для клавиатуры
_AI_PROVIDERS = {
    "deepseek": {
        "label": "DeepSeek",
        "endpoint": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner", "deepseek-v3"],
    },
    "openai": {
        "label": "OpenAI",
        "endpoint": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
    },
    "openrouter": {
        "label": "OpenRouter",
        "endpoint": "https://openrouter.ai/api/v1",
        "models": ["anthropic/claude-sonnet-4", "google/gemini-2.0-flash-001"],
    },
    "gemini": {
        "label": "Google Gemini",
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "models": ["gemini-2.0-flash-001", "gemini-2.0-pro", "gemini-1.5-pro"],
    },
    "qwen": {
        "label": "Qwen (Alibaba)",
        "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-max", "qwen-plus", "qwen2.5-72b-instruct"],
    },
    "custom": {
        "label": "Другое (Custom)",
        "endpoint": "",
        "models": [],
    },
}


# Singleton для сервиса конфига
_ai_config_service: AIConfigService | None = None


def _get_ai_config_service() -> AIConfigService:
    """Получить singleton AIConfigService."""
    global _ai_config_service
    if _ai_config_service is None:
        from pathlib import Path
        data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        _ai_config_service = AIConfigService(data_dir)
    return _ai_config_service


def get_ai_providers() -> dict:
    return _AI_PROVIDERS


def get_provider_keyboard():
    """Inline клавиатура выбора провайдера."""
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    for key, info in _AI_PROVIDERS.items():
        buttons.append([InlineKeyboardButton(text=info["label"], callback_data=f"ai_provider:{key}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_user_ai_config(user_id: int) -> dict | None:
    """Получить конфиг пользователя."""
    return _get_ai_config_service().get_config(user_id)


def save_user_ai_config(user_id: int, config: dict):
    """Сохранить конфиг пользователя."""
    _get_ai_config_service().save_config(user_id, config)


def clear_user_ai_config(user_id: int):
    """Удалить конфиг пользователя."""
    _get_ai_config_service().clear_config(user_id)


def format_user_ai_config(config: dict | None) -> str:
    """Форматировать конфиг для вывода."""
    return _get_ai_config_service().format_config(config)