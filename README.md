# HuntTech Candidate Bot

Telegram-бот для заведения кандидатов в HRM HuntTech из резюме с проверкой дублей в локальной базе данных (PostgreSQL 11).

## Возможности

- 🎯 **Создание кандидатов** — мастер `/candidate create` из резюме (docx/pdf) с парсингом через AI
- 🔍 **Проверка дублей** — `/candidate check` по ФИО, email, телефону, Telegram перед созданием
- 📋 **Список кандидатов** — `/candidate list` недавно созданных
- 🧠 **Настройка AI** — `/setup ai` (FSM-мастер: провайдер → API-ключ → модель) + тест подключения
- 🗄️ **Настройка БД** — `/setup db` (мастер из hunttech-bot-common)
- 👥 **Управление доступом** — `/setup user` / `/user` (выдача/отзыв доступа рекрутерам)
- 💰 **Статистика AI** — `/usage` расходы на нейросеть (today/week/month/all/N дней)
- 🛡️ **Безопасность** — доступ только по одобрению админа, суперпользователь = владелец бота

## Архитектура

Использует библиотеку **hunttech-bot-common** для всех общих функций:
- `users` — управление доступом (AccessManager, PTBUserHandlers)
- `database` — PostgreSQL пул, репозиторий, миграции
- `ai` — AI-клиент с учётом токенов (UsageTracker)
- `telegram` — CommandDef, render_help_text, escape_html
- `media` — логотип HuntTech (send_logo)
- `services.startup` — changelog при перезапуске
- `services.db_config_service` — мастер `/setup db`

## Установка и запуск

### 1. Зависимости

```bash
cd /Users/alekseyananyev/StudioProjects/hunttech-candidate-bot
pip install -e ../hunttech-bot-common
pip install -r requirements.txt  # или pip install -e ".[dev]"
```

### 2. Конфигурация

```bash
cp .env.example .env
# Отредактируйте .env:
# - TELEGRAM_BOT_TOKEN (от @BotFather)
# - AI_API_KEY (DeepSeek / OpenAI / др.)
# - DATABASE_URL (если не используете /setup db)
# - MASTER_ADMIN_ID (ваш Telegram ID)
```

### 3. Запуск

```bash
# Через скрипт (рекомендуется)
./scripts/run_bot.sh

# Или напрямую
~/ .hermes/hermes-agent/venv/bin/python3 -m hunttech_candidate_bot
```

## Команды бота

### Пользовательские (после выдачи доступа)

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие + access gate (логотип → меню) |
| `/help [раздел]` | Многоуровневая справка (system, candidate, setup) |
| `/candidate create` | Мастер создания кандидата из резюме |
| `/candidate check` | Проверить дубли по ФИО/контактам |
| `/candidate list` | Список недавно созданных кандидатов |
| `/cancel` | Отменить текущую операцию |

### Административные (только master_admin_id)

| Команда | Описание |
|---------|----------|
| `/setup ai` | FSM-мастер настройки AI-провайдера |
| `/setup ai test` | Проверить подключение к AI |
| `/setup ai show` | Показать настройки AI |
| `/setup db` | FSM-мастер настройки PostgreSQL |
| `/setup db test` | Проверить подключение к БД |
| `/setup db show` | Показать конфигурацию БД |
| `/setup user` | Управление доступом рекрутеров (алиас `/user`) |
| `/setup status` | Статистика работы бота |
| `/usage [period]` | Расходы на AI (today/week/month/all/N) |

## FSM создания кандидата (`/candidate create`)

1. **Владелец** — выбор рекрутера из `sec_user` (inline keyboard)
2. **Резюме** — загрузка .docx/.pdf (до 10 МБ)
3. **Формат Hunttech** — опциональный файл .doc/.docx для поля fileCV
4. **AI парсинг** — автоматическое извлечение структуры из резюме
5. **Подтверждение** — проверка данных + кнопка «Создать»
6. **Запись в БД** — жёсткий порядок: rehearsal → файлы → COMMIT → read-back

### Порядок записи в БД (по навыку hrm-candidate-creation)

1. **Репетиция** (BEGIN ... ROLLBACK) — все INSERT в транзакции с проверкой SELECT
2. **Копия файлов** в fileStorage: `YYYY/MM/DD/<sys_file_id>.<ext>`
3. **Реальный COMMIT** — те же INSERT, если упало — удаление физических файлов
4. **Read-back** — SELECT с JOIN справочников, верификация размеров файлов
5. **Автовзаимодействие** — «Новый контакт» 1.01 (rating=4, comment с датой)

Два файла CV: оригинал + формат Hunttech (оба в `hunttech_some_files` с `dtype='hunttech_SomeFilesCandidateCV'`).

## База данных

### Локальная тестовая БД (PG11)
```
Host: 127.0.0.1:5432
Database: hunttech
User: cuba
Password: cuba
sslmode=disable (ОБЯЗАТЕЛЬНО!)
```

### Настройка через `/setup db`
- Использует `DbConfigService` из библиотеки (FSM-мастер)
- Сохраняет в `data/db_config.json`
- Приоритет: `/setup db` → `.env` (DATABASE_URL)

## Структура проекта

```
hunttech-candidate-bot/
├── pyproject.toml           # версия 1.0.0
├── .env.example             # шаблон конфигурации
├── README.md                # этот файл
├── ALGORITHM.md             # детальный алгоритм
├── data/
│   ├── access_hunttech_candidate.json   # AccessManager
│   ├── db_config.json                   # /setup db
│   ├── startup_state.json               # changelog marker
│   └── temp_cv/                         # временные файлы резюме
├── src/
│   └── hunttech_candidate_bot/
│       ├── main.py                      # точка входа
│       ├── bootstrap.py                 # загрузка настроек
│       ├── application.py               # DI-контейнер
│       ├── config/settings.py           # настройки
│       ├── ai/service.py                # AIService (парсинг резюме)
│       ├── database/
│       │   ├── migrations/              # миграции бота
│       │   └── repository/              # репозитории
│       ├── services/
│       │   ├── candidate_service.py     # бизнес-логика создания
│       │   ├── duplicate_check.py       # проверка дублей
│       │   ├── file_storage.py          # fileStorage CUBA
│       │   ├── ai_config.py             # per-user AI config
│       │   └── stats.py                 # статистика
│       ├── telegram/
│       │   ├── commands/registry.py     # CommandDef registry
│       │   ├── handlers/                # все хендлеры
│       │   ├── menu/reply.py            # ReplyKeyboardMarkup
│       │   └── menu/sync.py             # BotCommandScopeChat
│       └── utils/cv_parser.py           # извлечение текста
├── tests/
│   └── test_bot.py                      # pytest тесты
└── scripts/run_bot.sh                   # запуск
```

## Стандарты HuntTech (08.2026)

### Приветствие (/start)
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
[👤 Создать кандидата] [🔍 Проверить дубли]
[📋 Мои кандидаты]     [❓ Справка]
```
Админ получает расширенное меню с кнопками Настроек и Статистики.

### Боковое меню (BotCommandScopeChat)
- Рекрутер: start, help, candidate, cancel
- Админ: + setup, usage, user

## Тестирование

```bash
# Запуск тестов
~/ .hermes/hermes-agent/venv/bin/python3 -m pytest tests/ -v

# Конкретный тест
~/ .hermes/hermes-agent/venv/bin/python3 -m pytest tests/test_bot.py::TestDuplicateCheck -v
```

## Ключевые UUID (тестовая БД = прод)

| Сущность | UUID |
|----------|------|
| Взаимодействие «Новый контакт» 1.01 | a4a9c7ff-11a1-1d72-3be7-e9484323b7fc |
| Default-вакансия | 4fc9fb45-5f78-2494-47aa-5a5fa2c97660 |
| Тип файла «Резюме» | fe77c780-a34d-c838-764d-7826eb0bed29 |
| Город Москва | 276b3aae-627e-9bd0-4695-12326b6ee946 |
| Оператор hermes | hermes (login) |

## Опечатки в схеме БД (учитываются в SQL)
- `birdh_date` (не birth_date)
- `comany_name` (не company_name)
- `decription_file_type` (не description)
- `Iteraction` (сущность, не Interaction)
- `number_` (колонка с подчёркиванием)

## Проверка дублей (обязательно перед созданием)

Выполняется read-only сверка по:
- ФИО (ILIKE + нормализованное полное совпадение)
- email (lower, точное)
- телефон (нормализованные цифры: `regexp_replace(phone||mobile_phone, '[^0-9]', '', 'g')`)
- telegram_name (без @)

Если найдены совпадения — бот показывает список с ID и полями совпадения, спрашивает подтверждение.

## Учёт AI токенов

Использует общий реестр `~/.hermes/hunttech_bots/ai_usage.json` через `UsageTracker` из библиотеки.
Команда `/usage` показывает отчёт за период с разбивкой по задачам.

## Разработка

### Добавление новой команды
1. Добавьте `CommandDef` в `telegram/commands/registry.py`
2. Создайте хендлер в `telegram/handlers/`
3. Зарегистрируйте в `telegram/handlers/__init__.py`
4. Добавьте в справку (автоматически через registry)

### Миграции БД
Миграции бота находятся в `database/migrations/__init__.py`.
Запускаются автоматически при подключении к БД.

## Лицензия

MIT — HuntTech / Hermes Agent