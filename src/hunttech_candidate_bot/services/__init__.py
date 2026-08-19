"""
Services package — экспорт сервисов.
"""
from hunttech_candidate_bot.services.candidate_service import CandidateService, CreatedCandidate
from hunttech_candidate_bot.services.duplicate_check import DuplicateCheckService, DuplicateCandidate
from hunttech_candidate_bot.services.file_storage import FileStorageService
from hunttech_candidate_bot.services.ai_config import AIConfigService, get_ai_providers, get_provider_keyboard
from hunttech_candidate_bot.services.stats import get_stats, format_status_for_admin

__all__ = [
    "CandidateService",
    "CreatedCandidate",
    "DuplicateCheckService",
    "DuplicateCandidate",
    "FileStorageService",
    "AIConfigService",
    "get_ai_providers",
    "get_provider_keyboard",
    "get_stats",
    "format_status_for_admin",
]