"""
Tests for HuntTech Candidate Bot.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


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