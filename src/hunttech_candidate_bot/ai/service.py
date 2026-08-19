"""
AI Service — парсинг резюме через LLM.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

from hunttech_bot_common.ai import AIClient, AIResponse

logger = logging.getLogger(__name__)


def thinking_disabled_extra(client: AIClient) -> dict:
    """Disable thinking for DeepSeek models."""
    if "deepseek" in client.model.lower():
        return {"chat_template_kwargs": {"enable_thinking": False}}
    return {}


@dataclass
class ParsedResume:
    """Структурированные данные из резюме."""
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    second_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile_phone: Optional[str] = None
    telegram_name: Optional[str] = None
    city: Optional[str] = None
    current_company: Optional[str] = None
    position: Optional[str] = None
    salary_expectations: Optional[str] = None
    skills: list[str] = None
    summary: Optional[str] = None

    def __post_init__(self):
        if self.skills is None:
            self.skills = []

    def full_name(self) -> str:
        parts = [self.second_name, self.first_name, self.middle_name]
        return " ".join(p for p in parts if p)

    def to_dict(self) -> dict:
        return {
            "first_name": self.first_name,
            "middle_name": self.middle_name,
            "second_name": self.second_name,
            "email": self.email,
            "phone": self.phone,
            "mobile_phone": self.mobile_phone,
            "telegram_name": self.telegram_name,
            "city": self.city,
            "current_company": self.current_company,
            "position": self.position,
            "salary_expectations": self.salary_expectations,
            "skills": self.skills,
            "summary": self.summary,
        }


RESUME_PARSE_PROMPT = """
Ты — HR-система HuntTech. Извлеки из текста резюме структурированные данные.
Верни ТОЛЬКО валидный JSON без markdown-блоков, без лишнего текста.

Поля (все строки, если нет — null; skills — массив строк):
- first_name (имя)
- middle_name (отчество, может быть пустым)
- second_name (фамилия)
- email
- phone (основной телефон)
- mobile_phone (мобильный телефон)
- telegram_name (без @)
- city (город проживания)
- current_company (текущая компания)
- position (желаемая/текущая должность)
- salary_expectations (вилка или сумма, текст, напр. "200000-250000" или "200 000 руб.")
- skills (массив технологий/навыков: ["Python", "PostgreSQL", "Docker"])
- summary (краткое описание опыта, 2-3 предложения)

Правила:
- Телефоны нормализуй к формату +7XXXXXXXXXX (только цифры после +7)
- telegram_name без @
- Если поля нет в резюме — верни null
- skills — только технические навыки, инструменты, языки программирования
- summary — кратко, по сути, без "воды"

Текст резюме:
{resume_text}
"""


class AIService:
    """Сервис AI для парсинга резюме и других задач."""

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        model: str,
        timeout: int = 120,
        usage_tracker=None,
    ):
        self.client = AIClient(
            endpoint=endpoint,
            api_key=api_key,
            model=model,
            provider="deepseek",
            default_timeout=timeout,
            usage_tracker=usage_tracker,
            bot_name="HuntTech Candidate Bot",
            ai_source="admin (.env)",
        )
        self.model = model

    async def parse_resume(self, resume_text: str, user_id: int, username: str = "") -> ParsedResume:
        """Распарсить текст резюме через AI."""
        # Обновляем клиент с user_id для учёта токенов
        self.client.user_id = user_id
        self.client.username = username
        self.client.ai_source = "user" if username else "admin (.env)"

        prompt = RESUME_PARSE_PROMPT.format(resume_text=resume_text[:8000])  # обрезаем если длинное

        try:
            response: AIResponse = await self.client.complete(
                system_prompt="Ты — HR-система HuntTech. Извлекаешь структурированные данные из резюме. Отвечаешь ТОЛЬКО валидным JSON.",
                user_prompt=prompt,
                temperature=0.1,
                max_tokens=2000,
                task="parse_resume",
            )

            # Парсим JSON ответ
            content = response.content.strip()
            # Убираем возможные markdown-блоки
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            data = json.loads(content)
            return ParsedResume(**data)

        except json.JSONDecodeError as e:
            logger.error("Failed to parse AI response as JSON: %s, content: %s", e, response.content)
            raise ValueError(f"AI вернул невалидный JSON: {e}")
        except Exception as e:
            logger.error("AI parse_resume failed: %s", e)
            raise

    async def test_connection(self) -> tuple[bool, str]:
        """Проверить подключение к AI."""
        try:
            response = await self.client.complete(
                system_prompt="Ответь одним словом.",
                user_prompt="Скажи 'OK'",
                temperature=0.1,
                max_tokens=10,
                task="test_connection",
            )
            return True, response.content.strip()
        except Exception as e:
            return False, str(e)