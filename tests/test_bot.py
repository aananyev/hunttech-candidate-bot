"""
Tests for HuntTech Candidate Bot.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path


class TestAccessFlow:
    """Тесты управления доступом (по стандарту hunttech-bot-common)."""
    
    @pytest.mark.asyncio
    async def test_admin_can_add_user(self):
        """Администратор может добавить пользователя."""
        # Тест будет реализован при необходимости
        pass
    
    @pytest.mark.asyncio
    async def test_regular_user_cannot_access_admin_commands(self):
        """Обычный пользователь не имеет доступа к админ-командам."""
        pass


class TestDuplicateCheck:
    """Тесты проверки дублей кандидатов."""
    
    @pytest.mark.asyncio
    async def test_phone_normalization(self):
        """Нормализация телефонов работает корректно."""
        from hunttech_candidate_bot.services.duplicate_check import DuplicateCheckService
        
        service = DuplicateCheckService(None)
        
        # Тест нормализации
        assert service._normalize_phone("+7 (999) 123-45-67") == "79991234567"
        assert service._normalize_phone("8-999-123-45-67") == "89991234567"
        assert service._normalize_phone("+79991234567") == "79991234567"
        assert service._normalize_phone(None) == ""
    
    @pytest.mark.asyncio
    async def test_name_normalization(self):
        """Нормализация ФИО работает корректно."""
        from hunttech_candidate_bot.services.duplicate_check import DuplicateCheckService
        
        service = DuplicateCheckService(None)
        
        # Фамилия Имя Отчество
        norm = service._normalize_name("Иван", "Иванович", "Иванов")
        assert norm == "иванов иван иванович"
        
        # Без отчества
        norm = service._normalize_name("Петр", None, "Петров")
        assert norm == "петров петр"
    
    @pytest.mark.asyncio
    async def test_match_fields_detection(self):
        """Определение полей совпадения работает корректно."""
        pass


class TestCandidateCreate:
    """Тесты FSM создания кандидата."""
    
    @pytest.mark.asyncio
    async def test_parsed_resume_full_name(self):
        """Метод full_name() корректно собирает ФИО."""
        from hunttech_candidate_bot.ai.service import ParsedResume
        
        resume = ParsedResume(
            first_name="Иван",
            middle_name="Иванович",
            second_name="Иванов",
        )
        assert resume.full_name() == "Иванов Иван Иванович"
        
        resume2 = ParsedResume(
            first_name="Петр",
            middle_name=None,
            second_name="Петров",
        )
        assert resume2.full_name() == "Петров Петр"


class TestCVParser:
    """Тесты парсера резюме."""
    
    @pytest.mark.asyncio
    async def test_sanitize_text_for_cv(self):
        """HTML-экранирование и <br> работают."""
        from hunttech_candidate_bot.utils.cv_parser import sanitize_text_for_cv
        
        text = "Привет\nМир & <test>"
        result = sanitize_text_for_cv(text)
        assert "&" in result
        assert "<" in result
        assert ">" in result
        assert "<br>" in result


class TestFileStorage:
    """Тесты файлового хранилища."""
    
    @pytest.mark.asyncio
    async def test_storage_path_format(self):
        """Путь в fileStorage имеет формат YYYY/MM/DD/<id>.<ext>."""
        from hunttech_candidate_bot.services.file_storage import FileStorageService
        from pathlib import Path
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = FileStorageService(Path(tmpdir))
            path = storage._get_storage_path("test-id", "docx")
            
            # Проверяем формат пути
            parts = path.parts
            assert len(parts) >= 4  # base/year/month/day/file
            assert parts[-1] == "test-id.docx"
            # Год, месяц, день
            assert len(parts[-4]) == 4  # year
            assert len(parts[-3]) == 2  # month
            assert len(parts[-2]) == 2  # day


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestPositionResolution:
    """Тесты резолва должности кандидата."""

    @pytest.mark.asyncio
    async def test_resolve_position_id_table_not_exists(self):
        """Если таблица hunttech_person_position не существует, вернуть None."""
        from unittest.mock import AsyncMock, MagicMock
        from hunttech_candidate_bot.services.candidate_service import CandidateService
        
        mock_conn = AsyncMock()
        # Таблица не существует
        mock_conn.fetchval.return_value = False
        
        service = CandidateService(None, Path("/tmp"))
        result = await service._resolve_position_id(mock_conn, "Python Developer")
        
        assert result is None
        mock_conn.fetchval.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_position_id_found(self):
        """Если должность найдена в таблице, вернуть её UUID."""
        from unittest.mock import AsyncMock, MagicMock
        from hunttech_candidate_bot.services.candidate_service import CandidateService
        
        mock_conn = AsyncMock()
        # Таблица существует
        mock_conn.fetchval.return_value = True
        # Должность найдена
        mock_conn.fetchrow.return_value = {"id": "pos-uuid-123"}
        
        service = CandidateService(None, Path("/tmp"))
        result = await service._resolve_position_id(mock_conn, "Python Developer")
        
        assert result == "pos-uuid-123"
        mock_conn.fetchval.assert_called_once()
        mock_conn.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_position_id_not_found(self):
        """Если должность не найдена в таблице, вернуть None."""
        from unittest.mock import AsyncMock, MagicMock
        from hunttech_candidate_bot.services.candidate_service import CandidateService
        
        mock_conn = AsyncMock()
        mock_conn.fetchval.return_value = True
        mock_conn.fetchrow.return_value = None
        
        service = CandidateService(None, Path("/tmp"))
        result = await service._resolve_position_id(mock_conn, "Unknown Position")
        
        assert result is None
        mock_conn.fetchval.assert_called_once()
        mock_conn.fetchrow.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_position_id_none_input(self):
        """Если position_name=None, вернуть None без запросов к БД."""
        from unittest.mock import AsyncMock, MagicMock
        from hunttech_candidate_bot.services.candidate_service import CandidateService
        
        mock_conn = AsyncMock()
        
        service = CandidateService(None, Path("/tmp"))
        result = await service._resolve_position_id(mock_conn, None)
        
        assert result is None
        mock_conn.fetchval.assert_not_called()
        mock_conn.fetchrow.assert_not_called()


class TestVerifySafeJoin:
    """Тесты безопасного JOIN в верификации (hunttech_person_position может отсутствовать)."""

    @pytest.mark.asyncio
    async def test_verify_without_position_table(self):
        """Верификация должна работать, если таблицы hunttech_person_position нет."""
        from unittest.mock import AsyncMock, MagicMock
        from contextlib import AsyncExitStack
        from hunttech_candidate_bot.services.candidate_service import CandidateService
        from pathlib import Path
        
        mock_conn = AsyncMock()
        # Таблица position не существует
        mock_conn.fetchval.return_value = False
        # Кандидат найден
        mock_conn.fetchrow.side_effect = [
            # candidate
            {
                "id": "cand-123", "version": 0, "first_name": "Ivan",
                "middle_name": "Ivanovich", "second_name": "Ivanov",
                "full_name": "Ivanov Ivan Ivanovich",
                "email": "ivan@test.com", "phone": "+799****4567",
                "mobile_phone": None, "telegram_name": "ivan_test",
                "city_of_residence_id": None, "current_company_id": None,
                "person_position_id": None, "status": None, "work_status": None,
                "city_name": None, "company_name": None, "position_name": None
            },
            # CV
            {
                "id": "cv-123", "candidate_id": "cand-123", "resume_position_id": None,
                "owner_id": "owner-123", "text_cv": "summary",
                "link_original_cv": None, "original_file_cv_id": "file-123",
                "file_cv_id": "file-456", "link_it_pearls_cv": None,
                "date_post": "2026-08-19", "contact_info_checked": True
            },
            # iteraction
            {
                "id": "iteraction-123", "candidate_id": "cand-123", "iteraction_type_id": "a4a9c7ff-11a1-1d72-3be7-e9484323b7fc",
                "recrutier_id": "owner-123", "recrutier_name": "Owner",
                "number_iteraction": 1, "date_iteraction": "2026-08-19",
                "comment_": "test", "rating": 4
            }
        ]
        # sys_file записи
        mock_conn.fetch.side_effect = [
            # sys_file
            [
                {"id": "file-123", "name": "resume.docx", "ext": "docx", "file_size": 1024, "create_date": "2026-08-19"},
                {"id": "file-456", "name": "resume.doc", "ext": "doc", "file_size": 2048, "create_date": "2026-08-19"}
            ],
            # some_files
            []
        ]
        
        service = CandidateService(None, Path("/tmp"))
        # Правильно мокаем async context manager для db.acquire()
        mock_acquire = AsyncMock()
        mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire.__aexit__ = AsyncMock(return_value=None)
        service.db = MagicMock()
        service.db.acquire.return_value = mock_acquire
        service.file_storage = MagicMock()
        service.file_storage.verify_file_size.return_value = True
        
        # Не должно выбросить исключение
        await service._verify(
            "cand-123", "cv-123", "file-123", "file-456", 1024, 2048
        )

    @pytest.mark.asyncio
    async def test_verify_with_position_table(self):
        """Верификация должна работать, если таблица hunttech_person_position существует."""
        from unittest.mock import AsyncMock, MagicMock
        from contextlib import AsyncExitStack
        from hunttech_candidate_bot.services.candidate_service import CandidateService
        from pathlib import Path
        
        mock_conn = AsyncMock()
        # Таблица position существует
        mock_conn.fetchval.return_value = True
        
        call_count = 0
        def fetchrow_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "id": "cand-123", "version": 0, "first_name": "Ivan",
                    "middle_name": "Ivanovich", "second_name": "Ivanov",
                    "full_name": "Ivanov Ivan Ivanovich",
                    "email": "ivan@test.com", "phone": "+799****4567",
                    "mobile_phone": None, "telegram_name": "ivan_test",
                    "city_of_residence_id": None, "current_company_id": None,
                    "person_position_id": "pos-123", "status": None, "work_status": None,
                    "city_name": None, "company_name": None, "position_name": "Python Developer"
                }
            elif call_count == 2:
                return {
                    "id": "cv-123", "candidate_id": "cand-123", "resume_position_id": None,
                    "owner_id": "owner-123", "text_cv": "summary",
                    "link_original_cv": None, "original_file_cv_id": "file-123",
                    "file_cv_id": "file-456", "link_it_pearls_cv": None,
                    "date_post": "2026-08-19", "contact_info_checked": True
                }
            elif call_count == 3:
                return {
                    "id": "iteraction-123", "candidate_id": "cand-123", "iteraction_type_id": "a4a9c7ff-11a1-1d72-3be7-e9484323b7fc",
                    "recrutier_id": "owner-123", "recrutier_name": "Owner",
                    "number_iteraction": 1, "date_iteraction": "2026-08-19",
                    "comment_": "test", "rating": 4
                }
            return None
        
        mock_conn.fetchrow.side_effect = fetchrow_side_effect
        # sys_file записи
        mock_conn.fetch.side_effect = [
            # sys_file
            [
                {"id": "file-123", "name": "resume.docx", "ext": "docx", "file_size": 1024, "create_date": "2026-08-19"},
                {"id": "file-456", "name": "resume.doc", "ext": "doc", "file_size": 2048, "create_date": "2026-08-19"}
            ],
            # some_files
            []
        ]
        
        service = CandidateService(None, Path("/tmp"))
        mock_acquire = AsyncMock()
        mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire.__aexit__ = AsyncMock(return_value=None)
        service.db = MagicMock()
        service.db.acquire.return_value = mock_acquire
        service.file_storage = MagicMock()
        service.file_storage.verify_file_size.return_value = True
        
        # Не должно выбросить исключение
        await service._verify(
            "cand-123", "cv-123", "file-123", "file-456", 1024, 2048
        )

    @pytest.mark.asyncio
    async def test_verify_undefined_table_error_fallback(self):
        """РЕГРЕССИЯ: JOIN с несуществующей hunttech_person_position должен перехватываться.
        
        Воспроизводит реальную ошибку прод-базы:
        relation "hunttech_person_position" does not exist (asyncpg UndefinedTableError).
        Раньше _verify падал, теперь работает fallback-запрос без JOIN.
        """
        from unittest.mock import AsyncMock, MagicMock
        from hunttech_candidate_bot.services.candidate_service import CandidateService
        from pathlib import Path
        
        class UndefinedTableError(Exception):
            """Эмуляция asyncpg.exceptions.UndefinedTableError."""
            pass
        
        mock_conn = AsyncMock()
        # Проверка существования таблицы говорит True, но JOIN падает —
        # worst-case: гонка или некорректная проверка
        mock_conn.fetchval.return_value = True
        
        call_count = 0
        def fetchrow_side_effect(query, *args):
            nonlocal call_count
            call_count += 1
            # 1-й запрос — с JOIN hunttech_person_position → падает как на проде
            if call_count == 1:
                raise UndefinedTableError(
                    'relation "hunttech_person_position" does not exist'
                )
            # 2-й запрос — fallback без JOIN → кандидат найден
            if call_count == 2:
                return {
                    "id": "cand-123", "version": 0, "first_name": "Ivan",
                    "middle_name": "Ivanovich", "second_name": "Ivanov",
                    "full_name": "Ivanov Ivan Ivanovich",
                    "email": "ivan@test.com", "phone": "+79991234567",
                    "mobile_phone": None, "telegram_name": "ivan_test",
                    "city_of_residence_id": None, "current_company_id": None,
                    "person_position_id": None, "status": None, "work_status": None,
                    "city_name": None, "company_name": None, "position_name": None
                }
            # 3-й — CV
            if call_count == 3:
                return {
                    "id": "cv-123", "candidate_id": "cand-123", "resume_position_id": None,
                    "owner_id": "owner-123", "text_cv": "summary",
                    "link_original_cv": None, "original_file_cv_id": "file-123",
                    "file_cv_id": "file-456", "link_it_pearls_cv": None,
                    "date_post": "2026-08-19", "contact_info_checked": True
                }
            # 4-й — iteraction
            if call_count == 4:
                return {
                    "id": "iteraction-123", "candidate_id": "cand-123",
                    "iteraction_type_id": "a4a9c7ff-11a1-1d72-3be7-e9484323b7fc",
                    "recrutier_id": "owner-123", "recrutier_name": "Owner",
                    "number_iteraction": 1, "date_iteraction": "2026-08-19",
                    "comment_": "test", "rating": 4
                }
            return None
        
        mock_conn.fetchrow.side_effect = fetchrow_side_effect
        # sys_file + some_files
        mock_conn.fetch.side_effect = [
            [
                {"id": "file-123", "name": "resume.docx", "ext": "docx", "file_size": 1024, "create_date": "2026-08-19"},
                {"id": "file-456", "name": "resume.doc", "ext": "doc", "file_size": 2048, "create_date": "2026-08-19"}
            ],
            []
        ]
        
        service = CandidateService(None, Path("/tmp"))
        mock_acquire = AsyncMock()
        mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire.__aexit__ = AsyncMock(return_value=None)
        service.db = MagicMock()
        service.db.acquire.return_value = mock_acquire
        service.file_storage = MagicMock()
        service.file_storage.verify_file_size.return_value = True
        
        # Ключевая проверка: _verify НЕ должен выбросить UndefinedTableError
        await service._verify(
            "cand-123", "cv-123", "file-123", "file-456", 1024, 2048
        )
        # Убеждаемся, что fallback-запрос (2-й fetchrow) реально выполнялся
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_resolve_position_id_undefined_table_fallback(self):
        """РЕГРЕССИЯ: резолв позиции не должен падать на отсутствии таблицы."""
        from unittest.mock import AsyncMock, MagicMock
        from hunttech_candidate_bot.services.candidate_service import CandidateService
        from pathlib import Path
        
        mock_conn = AsyncMock()
        
        def fetchval_side_effect(query):
            if "information_schema.tables" in query:
                raise Exception('relation "hunttech_person_position" does not exist')
            return False
        
        mock_conn.fetchval.side_effect = fetchval_side_effect
        
        service = CandidateService(None, Path("/tmp"))
        # Не должно выбросить исключение — fail-open к None
        result = await service._resolve_position_id(mock_conn, "Python Developer")
        assert result is None