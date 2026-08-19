"""
File storage service — работа с fileStorage CUBA.
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class FileStorageService:
    """Сервис для работы с файловым хранилищем CUBA (fileStorage)."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_storage_path(self, file_id: str, ext: str) -> Path:
        """Получить путь в fileStorage: YYYY/MM/DD/<id>.<ext>"""
        now = datetime.now()
        year = now.strftime("%Y")
        month = now.strftime("%m")
        day = now.strftime("%d")
        dir_path = self.base_path / year / month / day
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path / f"{file_id}.{ext}"

    def copy_file_to_storage(self, source_path: Path, file_id: str, ext: str) -> Path:
        """Копировать файл в fileStorage и вернуть целевой путь."""
        dest_path = self._get_storage_path(file_id, ext)
        shutil.copy2(source_path, dest_path)
        logger.info("File copied to storage: %s", dest_path)
        return dest_path

    def remove_file_from_storage(self, file_id: str, ext: str) -> bool:
        """Удалить файл из fileStorage (если COMMIT упал)."""
        dest_path = self._get_storage_path(file_id, ext)
        if dest_path.exists():
            dest_path.unlink()
            logger.info("File removed from storage: %s", dest_path)
            return True
        return False

    def get_file_size(self, file_id: str, ext: str) -> Optional[int]:
        """Получить размер файла в storage (для верификации)."""
        dest_path = self._get_storage_path(file_id, ext)
        if dest_path.exists():
            return dest_path.stat().st_size
        return None

    def verify_file_size(self, file_id: str, ext: str, expected_size: int) -> bool:
        """Верификация размера файла."""
        actual = self.get_file_size(file_id, ext)
        if actual is None:
            return False
        return actual == expected_size