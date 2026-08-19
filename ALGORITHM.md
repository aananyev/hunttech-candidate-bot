# HuntTech Candidate Bot — Детальный алгоритм и спецификация

## Обзор
Бот для заведения кандидатов в HRM HuntTech из резюме с проверкой дублей, работой с локальной БД (PG11) и поддержкой стандартного стека HuntTech-ботов.

---

## Архитектура (по стандарту hunttech-bot-common)

### Используемые модули библиотеки:
| Модуль | Назначение |
|--------|------------|
| `hunttech_bot_common.users` | Управление доступом (AccessManager, PTBUserHandlers) |
| `hunttech_bot_common.database` | PostgreSQL пул, репозиторий, миграции |
| `hunttech_bot_common.ai` | AI-клиент для парсинга резюме |
| `hunttech_bot_common.telegram` | CommandDef, render_help_text, escape_html |
| `hunttech_bot_common.security` | sanitize_text_input, validate_url |
| `hunttech_bot_common.media` | send_logo (логотип HuntTech) |
| `hunttech_bot_common.services.startup` | send_startup_changelog |
| `hunttech_bot_common.services.db_config_service` | /setup db мастер |
| `hunttech_bot_common.config` | AppSettings, BotSettings |

---

## Команды бота

### Пользовательские (доступны после /start и выдачи доступа):
| Команда | Описание |
|---------|----------|
| `/start` | Приветствие + access gate (логотип → приветствие → меню) |
| `/help [раздел]` | Многоуровневая справка (system, candidate, setup) |
| `/candidate create` | Создать кандидата из резюме (FSM-мастер) |
| `/candidate check` | Проверить дубли по ФИО/email/телефону/telegram |
| `/candidate list` | Список недавно созданных кандидатов |
| `/cancel` | Отменить текущую операцию |

### Административные (только master_admin_id):
| Команда | Описание |
|---------|----------|
| `/setup ai` | FSM-мастер настройки AI-провайдера |
| `/setup ai test` | Проверить подключение к AI |
| `/setup ai show` | Показать настройки AI |
| `/setup db` | FSM-мастер настройки PostgreSQL (из библиотеки) |
| `/setup db test` | Проверить подключение к БД |
| `/setup db show` | Показать конфигурацию БД |
| `/setup user` | Управление доступом рекрутеров (алиас /user) |
| `/setup status` | Статистика работы бота |
| `/usage [period]` | Расходы на AI (today/week/month/all/N) |

---

## FSM-мастер создания кандидата (`/candidate create`)

### Этапы (StatesGroup):
```python
class CandidateCreateState(StatesGroup):
    owner = State()           # 1. Выбор владельца-рекрутера (inline keyboard)
    resume_file = State()     # 2. Загрузка файла резюме (docx/pdf)
    resume_format_file = State()  # 3. Загрузка файла в формате Hunttech (опционально)
    ai_parse = State()        # 4. Парсинг резюме через AI (автоматически)
    confirm = State()         # 5. Подтверждение данных перед записью
    processing = State()      # 6. Запись в БД (rehearsal → COMMIT → read-back)
```

### Детальный флоу:

#### 1. Выбор владельца (owner)
- Показываем inline-клавиатуру с рекрутерами из `sec_user` (ExtUser)
- Данные берутся из БД: `SELECT id, login, name FROM sec_user WHERE delete_ts IS NULL AND active = true`
- Кнопка "Другой..." — ручной ввод ID/username
- Обязательный шаг — без владельца не идём дальше (по требованию навыка)

#### 2. Загрузка резюме (resume_file)
- Принимаем document (docx, pdf)
- Валидация: расширение, размер (max 10MB через `validate_file_size`)
- Сохраняем во временную директорию `data/temp_cv/`
- Переход к этапу 3

#### 3. Файл в формате Hunttech (resume_format_file) — опционально
- "Есть файл в формате Hunttech?" — inline кнопки: "Загрузить" / "Пропустить"
- Если загружают — валидация и сохранение
- Переход к этапу 4

#### 4. Парсинг через AI (ai_parse) — автоматический
- Извлечение текста:
  - docx: `textutil -convert txt -stdout file.docx` (macOS) или python-docx
  - pdf: pdfplumber
- HTML-экранирование (`& < >`) + `\n` → `<br>` (по стандарту CandidateCVEdit)
- AI-промпт для структурированного извлечения:
  ```json
  {
    "first_name": "Имя",
    "middle_name": "Отчество", 
    "second_name": "Фамилия",
    "email": "email@domain.ru",
    "phone": "+79991234567",
    "mobile_phone": "+79991234567",
    "telegram_name": "username",
    "city": "Москва",
    "current_company": "Компания",
    "position": "Должность",
    "salary_expectations": "200000-250000",
    "skills": ["Python", "PostgreSQL", "Docker"],
    "summary": "Краткое описание..."
  }
  ```
- Результат сохраняется в state

#### 5. Подтверждение (confirm)
- Показываем извлечённые данные в читаемом виде
- Inline кнопки: "✅ Создать", "✏️ Исправить поле", "❌ Отмена"
- При "Исправить" — переход к вводу конкретного поля

#### 6. Запись в БД (processing) — ЖЁСТКИЙ ПОРЯДОК (по навыку hrm-candidate-creation)

**Шаг 0: Проверка дублей (read-only)**
```sql
-- По ФИО (ILIKE + нормализованное полное совпадение)
SELECT id, first_name, middle_name, second_name, email, phone, mobile_phone, telegram_name
FROM hunttech_job_candidate
WHERE LOWER(CONCAT(second_name, ' ', first_name, ' ', COALESCE(middle_name, ''))) 
      LIKE LOWER(CONCAT(%(second_name)s, ' ', %(first_name)s, ' ', COALESCE(%(middle_name)s, '')))
   OR LOWER(email) = LOWER(%(email)s)
   OR regexp_replace(COALESCE(phone,'')||COALESCE(mobile_phone,''), '[^0-9]', '', 'g') 
      = regexp_replace(COALESCE(%(phone)s,'')||COALESCE(%(mobile_phone)s,''), '[^0-9]', '', 'g')
   OR LOWER(telegram_name) = LOWER(%(telegram_name)s)
```

- Если найдены совпадения — показать пользователю список с ID и полями совпадения
- Спросить: "Это дубль? Создать всё равно?" — только после подтверждения идём дальше

**Шаг 1: Репетиция (BEGIN ... ROLLBACK)**
- Генерация UUID клиентом: `python3 -c "import uuid; print(uuid.uuid4())"`
- INSERT в `hunttech_job_candidate` (version=0, created_by='hermes')
- INSERT в `hunttech_candidate_cv` (version=1, owner_id=владелец)
- INSERT в `sys_file` (оригинал + формат Hunttech) — version=1
- INSERT в `hunttech_some_files` (dtype='hunttech_SomeFilesCandidateCV', file_type_id='Резюме'=fe77c780)
- INSERT в `hunttech_iteraction_list` (автовзаимодействие "Новый контакт" 1.01):
  - iteraction_type_id = a4a9c7ff-11a1-1d72-3be7-e9484323b7fc
  - recrutier_id/recrutier_name = владелец
  - rating = 4
  - comment_ = "Взаимодействие создано автоматически ботом Hermes dd.MM.yyyy HH:mm"
  - vacancy_id = 4fc9fb45-5f78-2494-47aa-5a5fa2c97660 (Default)
  - number_iteraction = (SELECT COALESCE(MAX(number_iteraction),0)+1 FROM hunttech_iteraction_list)
  - date_iteraction = NOW()
- SELECT-проверка всех записей
- ROLLBACK

**Шаг 2: Копия файлов в fileStorage**
- Путь: `~/StudioProjects/hunttech_recruiting/fileStorage/YYYY/MM/DD/<sys_file_id>.<ext>`
- `mkdir -p` + копирование файлов

**Шаг 3: Реальный COMMIT**
- Те же INSERT'ы, но с COMMIT
- Если COMMIT падает — удалить физические файлы из fileStorage

**Шаг 4: Read-back и верификация**
- SELECT карточки с JOIN справочников (город, компания, должность)
- SELECT CV, sys_file, some_files
- `stat` физических файлов — размеры должны совпадать с file_size в БД
- Отчёт пользователю: "✅ Кандидат создан! ID: ..., Владелец: ..., CV: 2 файла, Взаимодействие: Новый контакт"

---

## Безопасность и доступ (по стандарту)

### AccessManager (per-bot база)
- Файл: `data/access_hunttech_candidate.json` (или shared через `get_shared_access_path()`)
- master_admin_id = 272980897 (Алексей Ананьев)
- Команды: `/user add|delete|list`, `/request_access`
- Middleware блокирует неавторизованных на всех командах кроме `/start`, `/request_access`, `/cancel`

### Приветствие (стандарт HuntTech 08.2026)
```
👋 Добро пожаловать!
✅ Бот готов!
📋 Назначение: заведение кандидатов в HRM HuntTech из резюме с проверкой дублей.

1️⃣ /candidate create — создать кандидата из резюме
2️⃣ /candidate check — проверить дубли
3️⃣ /help — все команды

━━━━━━━━━━━━━━━━━━━━━━
🔎 HuntTech
```
- Plain text, parse_mode=None
- Логотип отправляется ПЕРВЫМ сообщением (send_logo)

### Нижнее меню (ReplyKeyboardMarkup)
```
[📝 Создать кандидата] [🔍 Проверить дубли]
[📋 Мои кандидаты]     [❓ Справка]
```

### Боковое меню (BotCommandScopeChat)
- Для админа: все команды включая /setup, /usage
- Для рекрутера: только пользовательские

---

## Подключение к БД

### Локальная тестовая БД (PG11)
- Host: 127.0.0.1:5432
- Database: hunttech
- User: cuba
- Password: cuba
- JNDI в context.xml
- sslmode=disable (ОБЯЗАТЕЛЬНО — prefer падает в asyncpg)

### Настройка через /setup db
- Используем `DbConfigService` из библиотеки (FSM-мастер)
- Сохраняет в `data/db_config.json`
- Приоритет: /setup db → .env (DATABASE_URL)

---

## AI-парсинг резюме

### Промпт для извлечения структуры
```
Ты — HR-система HuntTech. Извлеки из текста резюме структурированные данные.
Верни ТОЛЬКО валидный JSON без markdown-блоков.

Поля:
- first_name (имя)
- middle_name (отчество, может быть пустым)
- second_name (фамилия)
- email
- phone (основной телефон)
- mobile_phone (мобильный)
- telegram_name (без @)
- city (город проживания)
- current_company (текущая компания)
- position (желаемая/текущая должность)
- salary_expectations (вилка или сумма, текст)
- skills (массив технологий/навыков)
- summary (краткое описание опыта, 2-3 предложения)

Если поля нет в резюме — верни null.
Телефоны нормализуй к формату +7XXXXXXXXXX.
```

### Использование AI
- Через `AIService` (обёртка над `AIClient` из библиотеки)
- Per-user настройки через `/setup ai` (сохраняются в `data/ai_config_{user_id}.json`)
- Глобальные из .env (AI_ENDPOINT, AI_API_KEY, AI_MODEL)
- Учёт токенов через `UsageTracker` (общий реестр `~/.hermes/hunttech_bots/ai_usage.json`)

---

## Статистика (/usage)

### Периоды:
- `/usage` — сегодня
- `/usage week` — 7 дней
- `/usage month` — 30 дней
- `/usage all` — всё время
- `/usage N` — N дней

### Вывод (формат отчёта):
```
💰 Расходы на нейросеть за сегодня:
• Всего запросов: 15
• Токенов: 45,230 (prompt: 32,100 / completion: 13,130)
• Стоимость: $0.0234
• По задачам:
  - parse_resume: 10 запросов, $0.0156
  - other: 5 запросов, $0.0078
```

---

## Структура проекта

```
hunttech-candidate-bot/
├── pyproject.toml
├── .env.example
├── README.md
├── data/
│   ├── access_hunttech_candidate.json   # AccessManager (per-bot)
│   ├── db_config.json                   # /setup db
│   ├── startup_state.json               # changelog marker
│   └── temp_cv/                         # временные файлы резюме
├── src/
│   └── hunttech_candidate_bot/
│       ├── __init__.py
│       ├── main.py                      # entry point
│       ├── bootstrap.py                 # загрузка настроек
│       ├── application.py               # DI-контейнер
│       ├── config/
│       │   └── settings.py
│       ├── ai/
│       │   ├── service.py               # AIService (парсинг резюме)
│       │   └── prompts.py               # промпты
│       ├── database/
│       │   ├── repository.py            # репозитории для候选人
│       │   └── migrations/              # миграции схемы бота
│       ├── services/
│       │   ├── candidate_service.py     # бизнес-логика создания
│       │   ├── duplicate_check.py       # проверка дублей
│       │   ├── file_storage.py          # работа с fileStorage
│       │   └── ai_config.py             # per-user AI config
│       ├── telegram/
│       │   ├── commands/
│       │   │   └── registry.py          # CommandDef registry
│       │   ├── handlers/
│       │   │   ├── __init__.py
│       │   │   ├── start.py             # /start + access gate
│       │   │   ├── help_handler.py      # /help
│       │   │   ├── cancel_handler.py    # /cancel
│       │   │   ├── user_handler.py      # /user
│       │   │   ├── setup_handler.py     # /setup (ai, db, user, status)
│       │   │   ├── usage_handler.py     # /usage
│       │   │   ├── candidate_handler.py # /candidate create/check/list
│       │   │   └── fsm_candidate.py     # FSM состояния создания
│       │   ├── menu/
│       │   │   ├── reply.py             # ReplyKeyboardMarkup
│       │   │   └── sync.py              # BotCommandScopeChat
│       │   ├── media.py                 # send_logo
│       │   └── permissions.py           # admin checks
│       └── utils/
│           └── cv_parser.py             # извлечение текста из docx/pdf
├── tests/
│   ├── test_access.py
│   ├── test_candidate_create.py
│   └── test_duplicate_check.py
└── scripts/
    └── run_bot.sh
```

---

## Справочные данные (из навыка hrm-candidate-creation)

### Ключевые UUID (тестовая БД = прод):
| Сущность | UUID |
|----------|------|
| Взаимодействие "Новый контакт" 1.01 | a4a9c7ff-11a1-1d72-3be7-e9484323b7fc |
| Default-вакансия | 4fc9fb45-5f78-2494-47aa-5a5fa2c97660 |
| Тип файла "Резюме" | fe77c780-a34d-c838-764d-7826eb0bed29 |
| Город Москва | 276b3aae-627e-9bd0-4695-12326b6ee946 |
| Компания MAYKOR | d17365b8-b6b2-416d-8704-86acf461fb7d |
| Оператор yakov | 80920aa2-bbfa-244e-8da4-331e2b0979ee |

### Опечатки в схеме БД (учитывать в SQL):
- `birdh_date` (не birth_date)
- `comany_name` (не company_name)
- `decription_file_type` (не description)
- `Iteraction` (сущность, не Interaction)
- `number_` (колонка с подчёркиванием)

---

## Чек-лист готовности (Definition of Done)

- [ ] Проект создан, pyproject.toml с версией 1.0.0
- [ ] Библиотека hunttech-bot-common установлена (pip install -e ../hunttech-bot-common)
- [ ] /start: логотип → приветствие → access gate → меню
- [ ] /help: разделы system, candidate, setup с фильтрацией по админке
- [ ] /candidate create: полный FSM (owner → файл → AI → подтверждение → БД)
- [ ] Проверка дублей перед созданием (read-only, сообщение пользователю)
- [ ] Жёсткий порядок записи: rehearsal → файлы → COMMIT → read-back
- [ ] Автовзаимодействие "Новый контакт" (rating=4, comment с датой)
- [ ] Два файла CV: оригинал + формат Hunttech (some_files обе)
- [ ] /setup ai: FSM-мастер (provider → api_key → model) + test
- [ ] /setup db: мастер из библиотеки
- [ ] /setup user: управление доступом (алиас /user)
- [ ] /usage: статистика токенов/стоимости по периодам
- [ ] startup_changelog: приветствие админу + изменения с прошлого запуска
- [ ] Нижнее меню (ReplyKeyboard) + боковое меню (BotCommand)
- [ ] Тесты: access, duplicate_check, candidate_create (минимум)
- [ ] Ручной прогон: создание кандидата из тестового резюме в локальной БД