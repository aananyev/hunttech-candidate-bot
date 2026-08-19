# HuntTech Candidate Bot — Developer Documentation

## Overview
Telegram-бот для заведения кандидатов в HRM HuntTech из резюме с проверкой дублей в локальной базе PostgreSQL 11.

**Репозиторий:** `hunttech-candidate-bot`  
**Стек:** aiogram 3.x, asyncpg, hunttech-bot-common 0.6.2  
**Python:** 3.11+  

---

## Architecture

### Core Modules (hunttech-bot-common)
| Module | Purpose |
|--------|---------|
| `users` | AccessManager, PTBUserHandlers — управление доступом |
| `database` | DatabasePool, BaseRepository, UnitOfWork, migrations |
| `ai` | AIClient + UsageTracker — учёт токенов в общем реестре |
| `telegram` | CommandDef, render_help_text, escape_html, split_long_message |
| `media` | send_logo — логотип HuntTech |
| `services.startup` | send_startup_changelog — сводка изменений при перезапуске |
| `services.db_config_service` | FSM-мастер `/setup db` |

### Project Structure
```
hunttech-candidate-bot/
├── pyproject.toml              # версия 1.0.0, зависимости
├── .env.example                # шаблон конфигурации
├── .env                        # локальная конфигурация (не в git)
├── README.md                   # пользовательская документация
├── DEVELOPER_GUIDE.md          # этот файл
├── CANDIDATE_ALGORITHM.md      # алгоритм заведения кандидата (независимый)
├── data/
│   ├── access_hunttech_candidate.json   # AccessManager
│   ├── db_config.json                   # /setup db
│   ├── startup_state.json               # changelog marker
│   └── temp_cv/                         # временные файлы резюме
├── src/
│   └── hunttech_candidate_bot/
│       ├── __main__.py           # entry point для python -m
│       ├── main.py               # основной цикл запуска
│       ├── bootstrap.py          # загрузка настроек
│       ├── application.py        # DI-контейнер + миграции
│       ├── ai/
│       │   ├── service.py        # AIService (парсинг резюме)
│       │   └── prompts.py        # промпты
│       ├── database/
│       │   ├── migrations/       # миграции бота
│       │   └── repository/       # репозитории метрик/состояния
│       ├── services/
│       │   ├── candidate_service.py  # бизнес-логика создания
│       │   ├── duplicate_check.py    # проверка дублей
│       │   ├── file_storage.py       # fileStorage CUBA
│       │   ├── ai_config.py          # per-user AI config
│       │   └── stats.py              # статистика
│       ├── telegram/
│       │   ├── commands/registry.py  # CommandDef registry
│       │   ├── handlers/             # все хендлеры
│       │   ├── menu/reply.py         # ReplyKeyboardMarkup
│       │   └── menu/sync.py          # BotCommandScopeChat
│       └── utils/cv_parser.py        # извлечение текста docx/pdf
├── tests/
│   └── test_bot.py               # pytest тесты (8 шт.)
└── scripts/run_bot.sh            # запуск через Hermes venv
```

---

## Configuration

### Environment Variables (.env)
```env
# Telegram (обязательно)
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...

# AI (для парсинга резюме)
AI_ENDPOINT=https://api.deepseek.com/v1
AI_API_KEY=sk-...
AI_MODEL=deepseek-chat
AI_TIMEOUT=120

# Database (PG11, sslmode=disable обязательно)
DATABASE_URL=postgresql://cuba:cuba@127.0.0.1:5432/hunttech?sslmode=disable

# Admins
MASTER_ADMIN_ID=272980897
ADMIN_IDS=272980897

# Channel
CHANNEL_ID=@hunttech_candidates
```

### Priority Order
1. `/setup db` → `data/db_config.json`
2. `.env` → `DATABASE_URL`
3. Defaults → local PG11

---

## Commands Registry

### System (all users)
| Command | Handler | Description |
|---------|---------|-------------|
| `/start` | `start.cmd_start` | Приветствие + access gate + логотип |
| `/help [section]` | `help_handler.cmd_help` | Многоуровневая справка |
| `/cancel` | `cancel_handler.cmd_cancel` | Отмена FSM |

### Candidates (authorized users)
| Command | Handler | Description |
|---------|---------|-------------|
| `/candidate create` | `candidate_handler.cmd_candidate` | FSM мастер создания |
| `/candidate check` | `candidate_handler.cmd_candidate` | Проверка дублей |
| `/candidate list` | `candidate_handler.cmd_candidate` | Список последних |

### Admin Only (master_admin_id)
| Command | Handler | Description |
|---------|---------|-------------|
| `/setup ai` | `setup_handler.cmd_setup` | FSM: provider → api_key → model |
| `/setup ai test` | `setup_handler._test_ai_connection` | Тест подключения |
| `/setup ai show` | `setup_handler._show_ai_config` | Показать настройки AI |
| `/setup db` | `setup_handler.cmd_setup` | Мастер БД из библиотеки |
| `/setup db test` | `setup_handler._cmd_db_test` | Тест БД |
| `/setup db show` | `setup_handler._cmd_db_show` | Показать конфиг БД |
| `/setup user` | `setup_handler._cmd_setup_user` | Управление доступом |
| `/setup status` | `setup_handler._show_status` | Статистика бота |
| `/setup show` | `setup_handler._show_config` | Все настройки |
| `/user` | `user_handler.cmd_user` | Алиас `/setup user` |
| `/usage [period]` | `usage_handler.cmd_usage` | Расходы AI |

---

## FSM States

### CandidateCreateState
```python
class CandidateCreateState(StatesGroup):
    owner = State()              # 1. Выбор рекрутера из sec_user
    resume_file = State()        # 2. Загрузка .docx/.pdf
    resume_format_file = State() # 3. Опциональный .doc/.docx
    ai_parse = State()           # 4. AI парсинг (авто)
    confirm = State()            # 5. Подтверждение данных
    processing = State()         # 6. Запись в БД
```

### CandidateCheckState
```python
class CandidateCheckState(StatesGroup):
    resume_file = State()        # Загрузка файла для проверки
    ai_parse = State()           # Парсинг + проверка
```

### AiSetupState
```python
class AiSetupState(StatesGroup):
    provider = State()           # Выбор провайдера (callback)
    api_key = State()            # Ввод API ключа
    model = State()              # Ввод модели
```

---

## Database Schema (Bot Tables)

### hunttech_candidate_bot_stats
```sql
CREATE TABLE hunttech_candidate_bot_stats (
    id SERIAL PRIMARY KEY,
    metric_name VARCHAR(100) NOT NULL UNIQUE,
    metric_value BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
-- Seed: candidates_created, duplicates_checked, active_users, ai_requests_today
```

### hunttech_candidate_bot_state
```sql
CREATE TABLE hunttech_candidate_bot_state (
    key VARCHAR(100) PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Migration Tracking
```sql
CREATE TABLE hunttech_candidate_bot_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TIMESTAMPTZ DEFAULT NOW(),
    checksum TEXT DEFAULT '',
    duration_ms INTEGER DEFAULT 0
);
```

---

## Key Services

### CandidateService
**Метод:** `create_candidate(resume, owner_id, owner_name, original_file_path, original_file_name, format_file_path, format_file_name)`

**Жёсткий порядок операций:**
1. **Rehearsal** — BEGIN ... ROLLBACK (все INSERT + SELECT проверка)
2. **Copy Files** — fileStorage `YYYY/MM/DD/<id>.<ext>`
3. **Real Commit** — те же INSERT с COMMIT (при ошибке → удалить файлы)
4. **Read-back** — SELECT с JOIN справочников + верификация размеров
5. **Auto-Interaction** — «Новый контакт» 1.01 (rating=4)

### DuplicateCheckService
**Метод:** `check_duplicates(ParsedResume) → list[DuplicateCandidate]`

**Критерии поиска (OR):**
- ФИО: `LOWER(CONCAT(second_name, ' ', first_name, ' ', middle_name)) LIKE %normalized%`
- Email: `LOWER(email) = LOWER(input_email)`
- Телефон: `regexp_replace(phone||mobile_phone, '[^0-9]', '', 'g') = normalized_digits`
- Telegram: `LOWER(telegram_name) = LOWER(input_telegram)`

### AIService
**Метод:** `parse_resume(resume_text, user_id, username) → ParsedResume`

**Промпт:** Извлекает 13 полей в JSON (first_name, middle_name, second_name, email, phone, mobile_phone, telegram_name, city, current_company, position, salary_expectations, skills[], summary)

---

## Running

### Development
```bash
cd /Users/alekseyananyev/StudioProjects/hunttech-candidate-bot
cp .env.example .env
# Edit .env with real tokens
./scripts/run_bot.sh
```

### Direct
```bash
~/ .hermes/hermes-agent/venv/bin/python3 -m hunttech_candidate_bot
```

### Tests
```bash
~/ .hermes/hermes-agent/venv/bin/python3 -m pytest tests/ -v
```

---

## Adding New Commands

1. Add `CommandDef` to `telegram/commands/registry.py`
2. Create handler in `telegram/handlers/`
3. Register in `telegram/handlers/__init__.py`
4. Help auto-generates from registry

---

## Deployment Notes

- **PG11 requirement:** `sslmode=disable` (asyncpg не поддерживает SSL upgrade на PG11)
- **File storage:** `~/StudioProjects/hunttech_recruiting/fileStorage/YYYY/MM/DD/`
- **Access DB:** `~/.hermes/profiles/bot-dev/hunttech_bots/access_hunttech_candidate.json`
- **AI Usage Registry:** `~/.hermes/hunttech_bots/ai_usage.json` (shared)
- **Version:** из `pyproject.toml` → `bot_version()` → short SHA → "unknown"

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `sslmode=prefer` error | Force `sslmode=disable` in DATABASE_URL |
| `chat not found` warnings | Admin must `/start` bot first |
| AI parse fails | Check `AI_API_KEY`, `AI_ENDPOINT` in .env |
| Duplicate check slow | Add indexes on email, phone, telegram_name |
| FileStorage permission | Ensure write access to `fileStorage/` dir |