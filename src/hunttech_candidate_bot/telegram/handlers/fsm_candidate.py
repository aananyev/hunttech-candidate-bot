"""
FSM состояния для создания кандидата.
"""
from aiogram.fsm.state import State, StatesGroup


class CandidateCreateState(StatesGroup):
    """Состояния FSM для создания кандидата."""
    owner = State()              # 1. Выбор владельца-рекрутера
    resume_file = State()        # 2. Загрузка файла резюме (docx/pdf)
    resume_format_file = State() # 3. Загрузка файла в формате Hunttech (опционально)
    ai_parse = State()           # 4. Парсинг резюме через AI (автоматически)
    confirm = State()            # 5. Подтверждение данных перед записью
    processing = State()         # 6. Запись в БД


class CandidateCheckState(StatesGroup):
    """Состояния FSM для проверки дублей."""
    resume_file = State()        # Загрузка файла для проверки
    ai_parse = State()           # Парсинг и проверка