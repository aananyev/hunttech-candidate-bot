"""
Duplicate check service — проверка дублей кандидатов в БД.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from hunttech_candidate_bot.ai.service import ParsedResume

logger = logging.getLogger(__name__)


@dataclass
class DuplicateCandidate:
    """Найденный дубль кандидата."""
    id: str
    first_name: str
    middle_name: Optional[str]
    second_name: str
    email: Optional[str]
    phone: Optional[str]
    mobile_phone: Optional[str]
    telegram_name: Optional[str]
    full_name: str
    match_fields: list[str]  # по каким полям совпал


class DuplicateCheckService:
    """Сервис проверки дублей перед созданием кандидата."""

    # Ключевые UUID из навыка hrm-candidate-creation
    DEFAULT_VACANCY_ID = "4fc9fb45-5f78-2494-47aa-5a5fa2c97660"
    NEW_CONTACT_TYPE_ID = "a4a9c7ff-11a1-1d72-3be7-e9484323b7fc"
    RESUME_FILE_TYPE_ID = "fe77c780-a34d-c838-764d-7826eb0bed29"

    def __init__(self, db_pool):
        self.db = db_pool

    def _normalize_phone(self, phone: Optional[str]) -> str:
        """Нормализация телефона: только цифры."""
        if not phone:
            return ""
        import re
        return re.sub(r"[^0-9]", "", phone)

    def _normalize_name(self, first: str, middle: Optional[str], second: str) -> str:
        """Нормализация ФИО для сравнения."""
        parts = [second.strip().lower(), first.strip().lower()]
        if middle:
            parts.append(middle.strip().lower())
        return " ".join(parts)

    async def check_duplicates(self, resume: ParsedResume) -> list[DuplicateCandidate]:
        """
        Проверить дубли по ФИО, email, телефону, telegram.
        Возвращает список найденных дублей с указанием полей совпадения.
        """
        if not self.db:
            logger.warning("Database not connected, skipping duplicate check")
            return []

        # Нормализуем входные данные
        norm_name = self._normalize_name(
            resume.first_name or "", resume.middle_name, resume.second_name or ""
        )
        norm_email = (resume.email or "").lower().strip()
        norm_phone = self._normalize_phone(resume.phone) + self._normalize_phone(resume.mobile_phone)
        norm_telegram = (resume.telegram_name or "").lower().strip().lstrip("@")

        # SQL запрос для поиска дублей
        query = """
        SELECT 
            id, first_name, middle_name, second_name, 
            email, phone, mobile_phone, telegram_name
        FROM hunttech_job_candidate
        WHERE delete_ts IS NULL
        AND (
            -- По ФИО (ILIKE + нормализованное полное совпадение)
            LOWER(CONCAT(second_name, ' ', first_name, ' ', COALESCE(middle_name, ''))) 
                LIKE $1
            -- По email (точное совпадение lower)
            OR LOWER(email) = $2
            -- По телефону (нормализованные цифры)
            OR regexp_replace(COALESCE(phone,'') || COALESCE(mobile_phone,''), '[^0-9]', '', 'g') = $3
            -- По telegram_name (без @)
            OR LOWER(telegram_name) = $4
        )
        LIMIT 20
        """

        name_pattern = f"%{norm_name}%"

        try:
            async with self.db.acquire() as conn:
                rows = await conn.fetch(
                    query, name_pattern, norm_email, norm_phone, norm_telegram
                )

            duplicates = []
            for row in rows:
                match_fields = []
                row_name = self._normalize_name(
                    row["first_name"] or "", row["middle_name"], row["second_name"] or ""
                )
                row_email = (row["email"] or "").lower().strip()
                row_phone = self._normalize_phone(row["phone"]) + self._normalize_phone(row["mobile_phone"])
                row_telegram = (row["telegram_name"] or "").lower().strip().lstrip("@")

                if norm_name and row_name == norm_name:
                    match_fields.append("ФИО (точное совпадение)")
                elif norm_name and norm_name in row_name:
                    match_fields.append("ФИО (частичное совпадение)")

                if norm_email and row_email == norm_email:
                    match_fields.append("Email")

                if norm_phone and row_phone == norm_phone:
                    match_fields.append("Телефон")

                if norm_telegram and row_telegram == norm_telegram:
                    match_fields.append("Telegram")

                full_name = f"{row['second_name']} {row['first_name']} {row['middle_name'] or ''}".strip()

                duplicates.append(DuplicateCandidate(
                    id=str(row["id"]),
                    first_name=row["first_name"] or "",
                    middle_name=row["middle_name"],
                    second_name=row["second_name"] or "",
                    email=row["email"],
                    phone=row["phone"],
                    mobile_phone=row["mobile_phone"],
                    telegram_name=row["telegram_name"],
                    full_name=full_name,
                    match_fields=match_fields,
                ))

            return duplicates

        except Exception as e:
            logger.error("Duplicate check failed: %s", e)
            # Не падаем — лучше пропустить проверку чем ломать создание
            return []

    def format_duplicates_report(self, duplicates: list[DuplicateCandidate]) -> str:
        """Форматировать отчёт о дублях для пользователя."""
        if not duplicates:
            return "✅ Дублей не найдено."

        lines = ["⚠️ *Найдены возможные дубли:*\n"]
        for i, dup in enumerate(duplicates, 1):
            lines.append(f"{i}. *{dup.full_name}* (ID: `{dup.id}`)")
            if dup.email:
                lines.append(f"   📧 Email: {dup.email}")
            if dup.phone:
                lines.append(f"   📞 Телефон: {dup.phone}")
            if dup.mobile_phone:
                lines.append(f"   📱 Моб.: {dup.mobile_phone}")
            if dup.telegram_name:
                lines.append(f"   💬 Telegram: @{dup.telegram_name}")
            lines.append(f"   🔍 Совпадение по: {', '.join(dup.match_fields)}")
            lines.append("")

        lines.append("❓ *Это тот же человек или новый кандидат?*")
        return "\n".join(lines)