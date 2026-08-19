"""
Candidate service — бизнес-логика создания кандидата в HRM HuntTech.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from hunttech_candidate_bot.ai.service import ParsedResume
from hunttech_candidate_bot.services.duplicate_check import DuplicateCheckService
from hunttech_candidate_bot.services.file_storage import FileStorageService

logger = logging.getLogger(__name__)


@dataclass
class CreatedCandidate:
    """Результат создания кандидата."""
    candidate_id: str
    cv_id: str
    original_file_id: Optional[str]
    format_file_id: Optional[str]
    iteraction_id: str
    owner_id: str
    owner_name: str


# Константы из навыка hrm-candidate-creation
DEFAULT_VACANCY_ID = "4fc9fb45-5f78-2494-47aa-5a5fa2c97660"
NEW_CONTACT_TYPE_ID = "a4a9c7ff-11a1-1d72-3be7-e9484323b7fc"
RESUME_FILE_TYPE_ID = "fe77c780-a34d-c838-764d-7826eb0bed29"
OPERATOR_LOGIN = "hermes"


class CandidateService:
    """Сервис создания кандидата с жёстким порядком операций."""

    def __init__(self, db_pool, file_storage_base: Path):
        self.db = db_pool
        self.duplicate_check = DuplicateCheckService(db_pool)
        self.file_storage = FileStorageService(file_storage_base)

    async def check_duplicates(self, resume: ParsedResume):
        """Проверить дубли перед созданием."""
        return await self.duplicate_check.check_duplicates(resume)

    async def create_candidate(
        self,
        resume: ParsedResume,
        owner_id: str,
        owner_name: str,
        original_file_path: Optional[Path] = None,
        original_file_name: Optional[str] = None,
        format_file_path: Optional[Path] = None,
        format_file_name: Optional[str] = None,
    ) -> CreatedCandidate:
        """
        Создать кандидата в БД по жёсткому порядку:
        1. Репетиция (BEGIN ... ROLLBACK)
        2. Копия файлов в fileStorage
        3. Реальный COMMIT
        4. Read-back и верификация
        """
        if not self.db:
            raise RuntimeError("Database not connected")

        candidate_id = str(uuid.uuid4())
        cv_id = str(uuid.uuid4())
        original_file_id = str(uuid.uuid4()) if original_file_path else None
        format_file_id = str(uuid.uuid4()) if format_file_path else None
        now = datetime.now()
        date_str = now.strftime("%d.%m.%Y %H:%M")

        # === ШАГ 1: РЕПЕТИЦИЯ (BEGIN ... ROLLBACK) ===
        logger.info("Starting rehearsal transaction for candidate %s", candidate_id)
        try:
            await self._rehearsal(
                candidate_id, cv_id, original_file_id, format_file_id,
                resume, owner_id, owner_name, now, date_str,
                original_file_path, original_file_name,
                format_file_path, format_file_name,
            )
        except Exception as e:
            if "REHEARSAL_ROLLBACK" in str(e):
                logger.info("Rehearsal completed (rolled back as expected) for candidate %s", candidate_id)
            else:
                logger.error("Rehearsal failed for candidate %s: %s", candidate_id, e)
                raise

        # === ШАГ 2: КОПИЯ ФАЙЛОВ В FILESTORAGE ===
        logger.info("Copying files to fileStorage")
        original_file_size = None
        format_file_size = None

        if original_file_path and original_file_id:
            dest = self.file_storage.copy_file_to_storage(
                original_file_path, original_file_id,
                original_file_path.suffix.lstrip(".")
            )
            original_file_size = dest.stat().st_size
            logger.info("Original file copied: %s (%d bytes)", dest, original_file_size)

        if format_file_path and format_file_id:
            dest = self.file_storage.copy_file_to_storage(
                format_file_path, format_file_id,
                format_file_path.suffix.lstrip(".")
            )
            format_file_size = dest.stat().st_size
            logger.info("Format file copied: %s (%d bytes)", dest, format_file_size)

        # === ШАГ 3: РЕАЛЬНЫЙ COMMIT ===
        logger.info("Starting real transaction for candidate %s", candidate_id)
        try:
            await self._commit(
                candidate_id, cv_id, original_file_id, format_file_id,
                resume, owner_id, owner_name, now, date_str,
                original_file_name, original_file_size,
                format_file_name, format_file_size,
            )
        except Exception as e:
            # Если COMMIT упал — удалить физические файлы
            logger.error("Commit failed, cleaning up files: %s", e)
            if original_file_id:
                self.file_storage.remove_file_from_storage(
                    original_file_id, original_file_path.suffix.lstrip(".")
                )
            if format_file_id:
                self.file_storage.remove_file_from_storage(
                    format_file_id, format_file_path.suffix.lstrip(".")
                )
            raise

        # === ШАГ 4: READ-BACK И ВЕРИФИКАЦИЯ ===
        logger.info("Read-back and verification for candidate %s", candidate_id)
        await self._verify(candidate_id, cv_id, original_file_id, format_file_id,
                           original_file_size, format_file_size)

        # === АВТОВЗАИМОДЕЙСТВИЕ "Новый контакт" ===
        iteraction_id = await self._create_new_contact_iteraction(
            candidate_id, owner_id, owner_name, date_str
        )

        logger.info("Candidate created successfully: %s", candidate_id)
        return CreatedCandidate(
            candidate_id=candidate_id,
            cv_id=cv_id,
            original_file_id=original_file_id,
            format_file_id=format_file_id,
            iteraction_id=iteraction_id,
            owner_id=owner_id,
            owner_name=owner_name,
        )

    async def _rehearsal(
        self,
        candidate_id: str, cv_id: str, original_file_id: Optional[str], format_file_id: Optional[str],
        resume: ParsedResume, owner_id: str, owner_name: str, now: datetime, date_str: str,
        original_file_path: Optional[Path], original_file_name: Optional[str],
        format_file_path: Optional[Path], format_file_name: Optional[str],
    ):
        """Репетиция: выполнить все INSERT в транзакции и сделать ROLLBACK."""
        async with self.db.acquire() as conn:
            async with conn.transaction():
                # 1. sys_file (оригинал) — ДОЛЖЕН БЫТЬ ПЕРВЫМ, так как CV ссылается на него
                if original_file_id and original_file_path:
                    logger.info("REHEARSAL[%s] 1/7 INSERT sys_file (original)", candidate_id)
                    await self._insert_sys_file_rehearsal(conn, original_file_id, original_file_path, now)

                # 2. sys_file (формат Hunttech)
                if format_file_id and format_file_path:
                    logger.info("REHEARSAL[%s] 2/7 INSERT sys_file (format)", candidate_id)
                    await self._insert_sys_file_rehearsal(conn, format_file_id, format_file_path, now)

                # 3. hunttech_job_candidate
                logger.info("REHEARSAL[%s] 3/7 INSERT hunttech_job_candidate", candidate_id)
                await self._insert_candidate_rehearsal(conn, candidate_id, resume, owner_id, now)

                # 4. hunttech_candidate_cv (теперь sys_file уже есть)
                logger.info("REHEARSAL[%s] 4/7 INSERT hunttech_candidate_cv", candidate_id)
                await self._insert_cv_rehearsal(conn, cv_id, candidate_id, resume, owner_id, now,
                                                 original_file_id, format_file_id)

                # 5. hunttech_some_files (оригинал)
                if original_file_id:
                    logger.info("REHEARSAL[%s] 5/7 INSERT hunttech_some_files (original)", candidate_id)
                    await self._insert_some_files_rehearsal(conn, cv_id, original_file_id, owner_id,
                                                             "Оригинал резюме", now)

                # 6. hunttech_some_files (формат Hunttech)
                if format_file_id:
                    logger.info("REHEARSAL[%s] 6/7 INSERT hunttech_some_files (format)", candidate_id)
                    await self._insert_some_files_rehearsal(conn, cv_id, format_file_id, owner_id,
                                                             "Резюме по формату Hunttech", now)

                # 7. hunttech_iteraction_list (автовзаимодействие)
                logger.info("REHEARSAL[%s] 7/7 INSERT hunttech_iteraction_list", candidate_id)
                await self._insert_iteraction_rehearsal(conn, candidate_id, owner_id, owner_name, now, date_str)

                # SELECT-проверка
                await self._verify_rehearsal(conn, candidate_id, cv_id, original_file_id, format_file_id)

                # Явный ROLLBACK — asyncpg transaction() коммитит при нормальном выходе
                raise Exception("REHEARSAL_ROLLBACK")

    async def _commit(
        self,
        candidate_id: str, cv_id: str, original_file_id: Optional[str], format_file_id: Optional[str],
        resume: ParsedResume, owner_id: str, owner_name: str, now: datetime, date_str: str,
        original_file_name: Optional[str], original_file_size: Optional[int],
        format_file_name: Optional[str], format_file_size: Optional[int],
    ):
        """Реальная запись с COMMIT."""
        async with self.db.acquire() as conn:
            async with conn.transaction():
                # 1. sys_file (оригинал) — ДОЛЖЕН БЫТЬ ПЕРВЫМ, так как CV ссылается на него
                if original_file_id and original_file_name and original_file_size:
                    logger.info("COMMIT[%s] 1/7 INSERT sys_file (original)", candidate_id)
                    await self._insert_sys_file_real(conn, original_file_id, original_file_name,
                                                      original_file_size, now)

                # 2. sys_file (формат Hunttech)
                if format_file_id and format_file_name and format_file_size:
                    logger.info("COMMIT[%s] 2/7 INSERT sys_file (format)", candidate_id)
                    await self._insert_sys_file_real(conn, format_file_id, format_file_name,
                                                      format_file_size, now)

                # 3. hunttech_job_candidate
                logger.info("COMMIT[%s] 3/7 INSERT hunttech_job_candidate", candidate_id)
                await self._insert_candidate_real(conn, candidate_id, resume, owner_id, now)

                # 4. hunttech_candidate_cv (теперь sys_file уже есть)
                logger.info("COMMIT[%s] 4/7 INSERT hunttech_candidate_cv", candidate_id)
                await self._insert_cv_real(conn, cv_id, candidate_id, resume, owner_id, now,
                                            original_file_id, format_file_id)

                # 5. hunttech_some_files (оригинал)
                if original_file_id:
                    logger.info("COMMIT[%s] 5/7 INSERT hunttech_some_files (original)", candidate_id)
                    await self._insert_some_files_real(conn, cv_id, original_file_id, owner_id,
                                                        "Оригинал резюме", now)

                # 6. hunttech_some_files (формат Hunttech)
                if format_file_id:
                    logger.info("COMMIT[%s] 6/7 INSERT hunttech_some_files (format)", candidate_id)
                    await self._insert_some_files_real(conn, cv_id, format_file_id, owner_id,
                                                        "Резюме по формату Hunttech", now)

                # 7. hunttech_iteraction_list (автовзаимодействие)
                logger.info("COMMIT[%s] 7/7 INSERT hunttech_iteraction_list", candidate_id)
                await self._insert_iteraction_real(conn, candidate_id, owner_id, owner_name, now, date_str)

    async def _verify(
        self,
        candidate_id: str, cv_id: str, original_file_id: Optional[str], format_file_id: Optional[str],
        original_file_size: Optional[int], format_file_size: Optional[int],
    ):
        """Read-back и верификация созданных записей."""
        async with self.db.acquire() as conn:
            # Проверяем существование таблицы hunttech_person_position
            try:
                position_table_exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables 
                        WHERE table_schema = 'public' AND table_name = 'hunttech_person_position'
                    )
                """)
                logger.info("VERIFY[%s] hunttech_person_position table exists: %s",
                            candidate_id, position_table_exists)
            except Exception as e:
                # Не смогли даже проверить — считаем, что таблицы нет, и работаем без JOIN
                logger.warning("VERIFY[%s] failed to check hunttech_person_position existence (%s), "
                               "using fallback query without JOIN", candidate_id, e)
                position_table_exists = False
            
            # Карточка кандидата с JOIN справочников (опциональный JOIN для person_position)
            candidate = None
            if position_table_exists:
                try:
                    candidate = await conn.fetchrow("""
                        SELECT 
                            jc.id, jc.version, jc.first_name, jc.middle_name, jc.second_name, jc.full_name,
                            jc.email, jc.phone, jc.mobile_phone, jc.telegram_name,
                            jc.city_of_residence_id, jc.current_company_id, jc.person_position_id,
                            jc.status, jc.work_status,
                            c.name AS city_name,
                            comp.comany_name AS company_name,
                            pos.position_ru_name AS position_name
                        FROM hunttech_job_candidate jc
                        LEFT JOIN hunttech_city c ON jc.city_of_residence_id = c.id
                        LEFT JOIN hunttech_company comp ON jc.current_company_id = comp.id
                        LEFT JOIN hunttech_person_position pos ON jc.person_position_id = pos.id
                        WHERE jc.id = $1
                    """, candidate_id)
                except Exception as e:
                    # JOIN неожиданно упал (например, таблица удалена между проверкой и запросом)
                    logger.warning("VERIFY[%s] JOIN query with hunttech_person_position failed (%s), "
                                   "retrying without JOIN", candidate_id, e)
                    position_table_exists = False
            
            if not candidate:
                candidate = await conn.fetchrow("""
                    SELECT 
                        jc.id, jc.version, jc.first_name, jc.middle_name, jc.second_name, jc.full_name,
                        jc.email, jc.phone, jc.mobile_phone, jc.telegram_name,
                        jc.city_of_residence_id, jc.current_company_id, jc.person_position_id,
                        jc.status, jc.work_status,
                        c.name AS city_name,
                        comp.comany_name AS company_name,
                        NULL AS position_name
                    FROM hunttech_job_candidate jc
                    LEFT JOIN hunttech_city c ON jc.city_of_residence_id = c.id
                    LEFT JOIN hunttech_company comp ON jc.current_company_id = comp.id
                    WHERE jc.id = $1
                """, candidate_id)

            if not candidate:
                raise RuntimeError(f"Candidate {candidate_id} not found after commit")

            # CV запись
            cv = await conn.fetchrow("""
                SELECT id, candidate_id, resume_position_id, owner_id, text_cv,
                       link_original_cv, original_file_cv_id, file_cv_id,
                       link_it_pearls_cv, date_post, contact_info_checked
                FROM hunttech_candidate_cv
                WHERE candidate_id = $1
            """, candidate_id)

            # sys_file записи
            sys_files = await conn.fetch("""
                SELECT id, name, ext, file_size, create_date
                FROM sys_file
                WHERE id = ANY($1::uuid[])
            """, [fid for fid in [original_file_id, format_file_id] if fid])

            # some_files записи
            some_files = await conn.fetch("""
                SELECT id, candidate_cv_id, file_description, file_descriptor_id,
                       file_owner_id, file_type_id
                FROM hunttech_some_files
                WHERE candidate_cv_id = $1
            """, cv_id)

            # iteraction запись
            iteraction = await conn.fetchrow("""
                SELECT id, candidate_id, iteraction_type_id, recrutier_id, recrutier_name,
                       number_iteraction, date_iteraction, comment_, rating
                FROM hunttech_iteraction_list
                WHERE candidate_id = $1 AND iteraction_type_id = $2
            """, candidate_id, NEW_CONTACT_TYPE_ID)

            # Верификация размеров файлов
            if original_file_id and original_file_size:
                sf = next((f for f in sys_files if f["id"] == original_file_id), None)
                if not sf or sf["file_size"] != original_file_size:
                    raise RuntimeError(f"File size mismatch for original: expected {original_file_size}, got {sf['file_size'] if sf else 'not found'}")
                if not self.file_storage.verify_file_size(original_file_id, "docx"):
                    raise RuntimeError("Physical file size mismatch for original")

            if format_file_id and format_file_size:
                sf = next((f for f in sys_files if f["id"] == format_file_id), None)
                if not sf or sf["file_size"] != format_file_size:
                    raise RuntimeError(f"File size mismatch for format: expected {format_file_size}, got {sf['file_size'] if sf else 'not found'}")
                if not self.file_storage.verify_file_size(format_file_id, "doc"):
                    raise RuntimeError("Physical file size mismatch for format")

            logger.info("Verification passed for candidate %s", candidate_id)

    # === SQL INSERT METHODS ===

    async def _resolve_position_id(self, conn, position_name: Optional[str]) -> Optional[str]:
        """Резолвить person_position_id по названию должности.
        
        Таблица hunttech_person_position может отсутствовать в БД (на проде её нет).
        В этом случае возвращаем None и записываем NULL в person_position_id.
        """
        if not position_name:
            return None
        
        try:
            # Проверяем существование таблицы
            table_exists = await conn.fetchval("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_schema = 'public' AND table_name = 'hunttech_person_position'
                )
            """)
            
            if not table_exists:
                logger.warning("Table hunttech_person_position does not exist, skipping position resolution")
                return None
            
            # Ищем должность по названию (ILIKE для частичного совпадения)
            row = await conn.fetchrow("""
                SELECT id FROM hunttech_person_position 
                WHERE position_ru_name ILIKE $1 
                LIMIT 1
            """, f"%{position_name}%")
            
            if row:
                logger.info("Resolved position '%s' -> %s", position_name, row["id"])
                return row["id"]
            
            logger.warning("Position '%s' not found in hunttech_person_position", position_name)
            return None
        except Exception as e:
            # Любая ошибка резолва позиции не должна ронять создание кандидата
            logger.warning("Position resolution failed for '%s': %s. "
                           "Using NULL for person_position_id", position_name, e)
            return None

    async def _insert_candidate_rehearsal(self, conn, candidate_id, resume, owner_id, now):
        """INSERT hunttech_job_candidate (репетиция)."""
        # Резолвим city_id по названию города
        city_id = None
        if resume.city:
            city_row = await conn.fetchrow(
                "SELECT id FROM hunttech_city WHERE city_ru_name ILIKE $1 LIMIT 1", resume.city
            )
            if city_row:
                city_id = city_row["id"]
        
        # Резолвим person_position_id по названию должности
        position_id = await self._resolve_position_id(conn, resume.position)
        
        await conn.execute("""
            INSERT INTO hunttech_job_candidate (
                id, version, create_ts, created_by, update_ts, updated_by,
                first_name, middle_name, second_name, full_name,
                email, phone, mobile_phone, telegram_name,
                birdh_date, city_of_residence_id, current_company_id,
                person_position_id, status, work_status
            ) VALUES (
                $1, 0, $2, $3, $2, $3,
                $4, $5, $6, $7,
                $8, $9, $10, $11,
                NULL, $12, NULL,
                $13, NULL, NULL
            )
        """, candidate_id, now, OPERATOR_LOGIN,
           resume.first_name, resume.middle_name, resume.second_name, resume.full_name(),
           resume.email, resume.phone, resume.mobile_phone, resume.telegram_name,
           city_id, position_id)

    async def _insert_cv_rehearsal(self, conn, cv_id, candidate_id, resume, owner_id, now,
                                    original_file_id, format_file_id):
        """INSERT hunttech_candidate_cv (репетиция)."""
        text_cv = resume.summary or ""
        if text_cv:
            text_cv = text_cv.replace("&", "&").replace("<", "<").replace(">", ">")
            text_cv = text_cv.replace("\n", "<br>")

        await conn.execute("""
            INSERT INTO hunttech_candidate_cv (
                id, version, create_ts, created_by, update_ts, updated_by,
                candidate_id, resume_position_id, owner_id, text_cv,
                link_original_cv, original_file_cv_id, file_cv_id,
                link_it_pearls_cv, date_post, contact_info_checked
            ) VALUES (
                $1, 1, $2, $3, $2, $3,
                $4, NULL, $5, $6,
                NULL, $7, $8,
                NULL, CURRENT_DATE, true
            )
        """, cv_id, now, OPERATOR_LOGIN, candidate_id, owner_id, text_cv,
           original_file_id, format_file_id)

    async def _insert_sys_file_rehearsal(self, conn, file_id, file_path, now):
        """INSERT sys_file (репетиция)."""
        ext = file_path.suffix.lstrip(".")
        file_size = file_path.stat().st_size
        await conn.execute("""
            INSERT INTO sys_file (id, version, create_ts, created_by, name, ext, file_size)
            VALUES ($1, 1, $2, $3, $4, $5, $6)
        """, file_id, now, OPERATOR_LOGIN, file_path.name, ext, file_size)

    async def _insert_some_files_rehearsal(self, conn, cv_id, file_id, owner_id, description, now):
        """INSERT hunttech_some_files (репетиция)."""
        import uuid
        some_files_id = str(uuid.uuid4())
        await conn.execute("""
            INSERT INTO hunttech_some_files (
                id, version, create_ts, created_by,
                dtype, candidate_cv_id, file_description,
                file_descriptor_id, file_owner_id, file_type_id
            ) VALUES (
                $1, 1, $2, $3,
                'hunttech_SomeFilesCandidateCV', $4, $5,
                $6, $7, $8
            )
        """, some_files_id, now, OPERATOR_LOGIN, cv_id, description, file_id, owner_id, RESUME_FILE_TYPE_ID)

    async def _insert_iteraction_rehearsal(self, conn, candidate_id, owner_id, owner_name, now, date_str):
        """INSERT hunttech_iteraction_list (репетиция) — автовзаимодействие 'Новый контакт'."""
        import uuid
        iteraction_id = str(uuid.uuid4())
        # Получаем max number_iteraction
        max_num = await conn.fetchval("SELECT COALESCE(MAX(number_iteraction), 0) FROM hunttech_iteraction_list")
        next_num = max_num + 1

        await conn.execute("""
            INSERT INTO hunttech_iteraction_list (
                id, version, create_ts, created_by, update_ts, updated_by,
                candidate_id, vacancy_id, iteraction_type_id,
                recrutier_id, recrutier_name, rating, comment_,
                number_iteraction, date_iteraction,
                current_priority, current_open_close
            ) VALUES (
                $1, 1, $2, $3, $2, $3,
                $4, $5, $6,
                $7, $8, 4, $9,
                $10, $2,
                NULL, NULL
            )
        """, iteraction_id, now, OPERATOR_LOGIN, candidate_id, DEFAULT_VACANCY_ID, NEW_CONTACT_TYPE_ID,
           owner_id, owner_name, f"Взаимодействие создано автоматически ботом Hermes {date_str}",
           next_num)

    async def _verify_rehearsal(self, conn, candidate_id, cv_id, original_file_id, format_file_id):
        """SELECT-проверка после репетиции."""
        # Проверяем кандидата
        cand = await conn.fetchrow("SELECT id FROM hunttech_job_candidate WHERE id = $1", candidate_id)
        if not cand:
            raise RuntimeError("Rehearsal: candidate not inserted")

        # Проверяем CV
        cv = await conn.fetchrow("SELECT id FROM hunttech_candidate_cv WHERE id = $1", cv_id)
        if not cv:
            raise RuntimeError("Rehearsal: CV not inserted")

        # Проверяем sys_file
        for fid in [original_file_id, format_file_id]:
            if fid:
                sf = await conn.fetchrow("SELECT id FROM sys_file WHERE id = $1", fid)
                if not sf:
                    raise RuntimeError(f"Rehearsal: sys_file {fid} not inserted")

    async def _insert_candidate_real(self, conn, candidate_id, resume, owner_id, now):
        """INSERT hunttech_job_candidate (реальный)."""
        # Резолвим city_id по названию города
        city_id = None
        if resume.city:
            city_row = await conn.fetchrow(
                "SELECT id FROM hunttech_city WHERE city_ru_name ILIKE $1 LIMIT 1", resume.city
            )
            if city_row:
                city_id = city_row["id"]
        
        # Резолвим person_position_id по названию должности
        position_id = await self._resolve_position_id(conn, resume.position)
        
        await conn.execute("""
            INSERT INTO hunttech_job_candidate (
                id, version, create_ts, created_by, update_ts, updated_by,
                first_name, middle_name, second_name, full_name,
                email, phone, mobile_phone, telegram_name,
                birdh_date, city_of_residence_id, current_company_id,
                person_position_id, status, work_status
            ) VALUES (
                $1, 0, $2, $3, $2, $3,
                $4, $5, $6, $7,
                $8, $9, $10, $11,
                NULL, $12, NULL,
                $13, NULL, NULL
            )
        """, candidate_id, now, OPERATOR_LOGIN,
           resume.first_name, resume.middle_name, resume.second_name, resume.full_name(),
           resume.email, resume.phone, resume.mobile_phone, resume.telegram_name,
           city_id, position_id)

    async def _insert_cv_real(self, conn, cv_id, candidate_id, resume, owner_id, now,
                               original_file_id, format_file_id):
        """INSERT hunttech_candidate_cv (реальный)."""
        text_cv = resume.summary or ""
        if text_cv:
            text_cv = text_cv.replace("&", "&").replace("<", "<").replace(">", ">")
            text_cv = text_cv.replace("\n", "<br>")

        await conn.execute("""
            INSERT INTO hunttech_candidate_cv (
                id, version, create_ts, created_by, update_ts, updated_by,
                candidate_id, resume_position_id, owner_id, text_cv,
                link_original_cv, original_file_cv_id, file_cv_id,
                link_it_pearls_cv, date_post, contact_info_checked
            ) VALUES (
                $1, 1, $2, $3, $2, $3,
                $4, NULL, $5, $6,
                NULL, $7, $8,
                NULL, CURRENT_DATE, true
            )
        """, cv_id, now, OPERATOR_LOGIN, candidate_id, owner_id, text_cv,
           original_file_id, format_file_id)

    async def _insert_sys_file_real(self, conn, file_id, file_name, file_size, now):
        """INSERT sys_file (реальный)."""
        ext = Path(file_name).suffix.lstrip(".")
        await conn.execute("""
            INSERT INTO sys_file (id, version, create_ts, created_by, name, ext, file_size)
            VALUES ($1, 1, $2, $3, $4, $5, $6)
        """, file_id, now, OPERATOR_LOGIN, file_name, ext, file_size)

    async def _insert_some_files_real(self, conn, cv_id, file_id, owner_id, description, now):
        """INSERT hunttech_some_files (реальный)."""
        import uuid
        some_files_id = str(uuid.uuid4())
        await conn.execute("""
            INSERT INTO hunttech_some_files (
                id, version, create_ts, created_by,
                dtype, candidate_cv_id, file_description,
                file_descriptor_id, file_owner_id, file_type_id
            ) VALUES (
                $1, 1, $2, $3,
                'hunttech_SomeFilesCandidateCV', $4, $5,
                $6, $7, $8
            )
        """, some_files_id, now, OPERATOR_LOGIN, cv_id, description, file_id, owner_id, RESUME_FILE_TYPE_ID)

    async def _insert_iteraction_real(self, conn, candidate_id, owner_id, owner_name, now, date_str):
        """INSERT hunttech_iteraction_list (реальный) — автовзаимодействие."""
        import uuid
        iteraction_id = str(uuid.uuid4())
        max_num = await conn.fetchval("SELECT COALESCE(MAX(number_iteraction), 0) FROM hunttech_iteraction_list")
        next_num = max_num + 1

        await conn.execute("""
            INSERT INTO hunttech_iteraction_list (
                id, version, create_ts, created_by, update_ts, updated_by,
                candidate_id, vacancy_id, iteraction_type_id,
                recrutier_id, recrutier_name, rating, comment_,
                number_iteraction, date_iteraction,
                current_priority, current_open_close
            ) VALUES (
                $1, 1, $2, $3, $2, $3,
                $4, $5, $6,
                $7, $8, 4, $9,
                $10, $2,
                NULL, NULL
            )
        """, iteraction_id, now, OPERATOR_LOGIN, candidate_id, DEFAULT_VACANCY_ID, NEW_CONTACT_TYPE_ID,
           owner_id, owner_name, f"Взаимодействие создано автоматически ботом Hermes {date_str}",
           next_num)

        return await conn.fetchval("SELECT id FROM hunttech_iteraction_list WHERE candidate_id = $1 AND iteraction_type_id = $2 ORDER BY create_ts DESC LIMIT 1", candidate_id, NEW_CONTACT_TYPE_ID)

    async def _create_new_contact_iteraction(self, candidate_id, owner_id, owner_name, date_str):
        """Создать автовзаимодействие 'Новый контакт' (отдельно, после COMMIT кандидата)."""
        import uuid
        iteraction_id = str(uuid.uuid4())
        async with self.db.acquire() as conn:
            async with conn.transaction():
                max_num = await conn.fetchval("SELECT COALESCE(MAX(number_iteraction), 0) FROM hunttech_iteraction_list")
                next_num = max_num + 1
                now = datetime.now()

                await conn.execute("""
                    INSERT INTO hunttech_iteraction_list (
                        id, version, create_ts, created_by, update_ts, updated_by,
                        candidate_id, vacancy_id, iteraction_type_id,
                        recrutier_id, recrutier_name, rating, comment_,
                        number_iteraction, date_iteraction,
                        current_priority, current_open_close
                    ) VALUES (
                        $1, 1, $2, $3, $2, $3,
                        $4, $5, $6,
                        $7, $8, 4, $9,
                        $10, $2,
                        NULL, NULL
                    )
                """, iteraction_id, now, OPERATOR_LOGIN, candidate_id, DEFAULT_VACANCY_ID, NEW_CONTACT_TYPE_ID,
                   owner_id, owner_name, f"Взаимодействие создано автоматически ботом Hermes {date_str}",
                   next_num)

                return iteraction_id

                return str(iteraction_id)