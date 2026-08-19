# Алгоритм заведения кандидата в HRM HuntTech

> **Независимый от бота алгоритм** для ручного заведения кандидата через HRM HuntTech UI или прямых SQL-операций в БД.  
> Версия: 1.0 (август 2026)  
> Основан на навыке `hrm-candidate-creation` и проверен на тестовой/прод БД.

---

## ⚠️ Ключевые принципы

1. **Порядок операций жёсткий:** Репетиция → Файлы → COMMIT → Read-back
2. **Два файла CV обязательны:** Оригинал + Формат Hunttech
3. **Автовзаимодействие:** Всегда создавать «Новый контакт» 1.01 (rating=4)
4. **Проверка дублей:** Обязательна перед созданием (read-only)
5. **UUID генерирует клиент** (не `gen_random_uuid()`)
6. **Владелец кандидата** — обязательный входной параметр

---

## 📥 Входные данные

### Кандидат (из резюме)
| Поле | Описание | Обязательно |
|------|----------|-------------|
| `first_name` | Имя | Да |
| `middle_name` | Отчество | Нет |
| `second_name` | Фамилия | Да |
| `email` | Email | Нет |
| `phone` | Основной телефон | Нет |
| `mobile_phone` | Мобильный телефон | Нет |
| `telegram_name` | Telegram без @ | Нет |
| `city_of_residence_id` | UUID города (справочник `hunttech_city`) | Нет |
| `current_company_id` | UUID компании (справочник `hunttech_company`) | Нет |
| `person_position_id` | UUID должности (справочник `hunttech_person_position`) | Нет |

### Файлы резюме
| Файл | Назначение | Поле в БД |
|------|------------|-----------|
| **Оригинал** | Файл как прислал кандидат (.docx/.pdf) | `original_file_cv_id` → `sys_file` |
| **Формат Hunttech** | Резюме в стандарте hh/HuntTech (.doc/.docx) | `file_cv_id` → `sys_file` |

### Метаданные
| Параметр | Значение |
|----------|----------|
| `owner_id` | UUID рекрутера-владельца (`sec_user.id`) |
| `owner_name` | Имя рекрутера (`sec_user.user_name`) |
| `operator_login` | Логин оператора (`hermes` или `yakov`) |
| `vacancy_id` | Default: `4fc9fb45-5f78-2494-47aa-5a5fa2c97660` |

---

## 🔍 Шаг 0: Проверка дублей (Read-Only)

Выполнить **перед** любыми записями. Если найдены совпадения — **остановиться и уточнить у пользователя**.

```sql
-- Нормализация входных данных
SET @norm_name = LOWER(CONCAT(TRIM(@second_name), ' ', TRIM(@first_name), ' ', COALESCE(TRIM(@middle_name), '')));
SET @norm_email = LOWER(TRIM(@email));
SET @norm_phone = REGEXP_REPLACE(COALESCE(@phone,'') || COALESCE(@mobile_phone,''), '[^0-9]', '', 'g');
SET @norm_telegram = LOWER(TRIM(LEADING '@' FROM @telegram_name));

-- Поиск дублей
SELECT 
    id, first_name, middle_name, second_name,
    email, phone, mobile_phone, telegram_name,
    -- Поля совпадения для отчёта
    CASE WHEN LOWER(CONCAT(second_name, ' ', first_name, ' ', COALESCE(middle_name, ''))) LIKE CONCAT('%', @norm_name, '%') THEN 1 ELSE 0 END AS match_name,
    CASE WHEN LOWER(email) = @norm_email AND @norm_email != '' THEN 1 ELSE 0 END AS match_email,
    CASE WHEN REGEXP_REPLACE(COALESCE(phone,'') || COALESCE(mobile_phone,''), '[^0-9]', '', 'g') = @norm_phone AND @norm_phone != '' THEN 1 ELSE 0 END AS match_phone,
    CASE WHEN LOWER(telegram_name) = @norm_telegram AND @norm_telegram != '' THEN 1 ELSE 0 END AS match_telegram
FROM hunttech_job_candidate
WHERE delete_ts IS NULL
  AND (
    LOWER(CONCAT(second_name, ' ', first_name, ' ', COALESCE(middle_name, ''))) LIKE CONCAT('%', @norm_name, '%')
    OR LOWER(email) = @norm_email
    OR REGEXP_REPLACE(COALESCE(phone,'') || COALESCE(mobile_phone,''), '[^0-9]', '', 'g') = @norm_phone
    OR LOWER(telegram_name) = @norm_telegram
  )
LIMIT 20;
```

**Действие при нахождении:**
- Показать пользователю: ID, ФИО, контакты, по каким полям совпало
- Спросить: «Это дубль? Создать всё равно?»
- Только после подтверждения → продолжать

---

## 🗄️ Шаг 1: Репетиция (BEGIN ... ROLLBACK)

Все INSERT выполняются в одной транзакции с последующим ROLLBACK для проверки корректности.

### 1.1 Генерация UUID
```python
# Клиентская генерация (Python)
import uuid
candidate_id = str(uuid.uuid4())
cv_id = str(uuid.uuid4())
original_file_id = str(uuid.uuid4()) if original_file else None
format_file_id = str(uuid.uuid4()) if format_file else None
iteraction_id = str(uuid.uuid4())
```

### 1.2 Константы справочников (стабильны тест/прод)
```sql
-- Взаимодействие "Новый контакт" 1.01
NEW_CONTACT_TYPE_ID = 'a4a9c7ff-11a1-1d72-3be7-e9484323b7fc';
-- Default-вакансия
DEFAULT_VACANCY_ID = '4fc9fb45-5f78-2494-47aa-5a5fa2c97660';
-- Тип файла "Резюме"
RESUME_FILE_TYPE_ID = 'fe77c780-a34d-c838-764d-7826eb0bed29';
```

### 1.3 INSERT в транзакции (порядок важен)

```sql
BEGIN;

-- 1. hunttech_job_candidate (version=0 для нового)
INSERT INTO hunttech_job_candidate (
    id, version, create_ts, created_by, update_ts, updated_by,
    first_name, middle_name, second_name, full_name,
    email, phone, mobile_phone, telegram_name,
    birdh_date, city_of_residence_id, current_company_id,
    person_position_id, status, work_status
) VALUES (
    :candidate_id, 0, NOW(), :operator, NOW(), :operator,
    :first_name, :middle_name, :second_name, :full_name,
    :email, :phone, :mobile_phone, :telegram_name,
    NULL, :city_id, :company_id,
    :position_id, NULL, NULL
);

-- 2. hunttech_candidate_cv (version=1)
-- text_cv: HTML-экранированный summary с <br> вместо \n
INSERT INTO hunttech_candidate_cv (
    id, version, create_ts, created_by, update_ts, updated_by,
    candidate_id, resume_position_id, owner_id, text_cv,
    link_original_cv, original_file_cv_id, file_cv_id,
    link_it_pearls_cv, date_post, contact_info_checked
) VALUES (
    :cv_id, 1, NOW(), :operator, NOW(), :operator,
    :candidate_id, NULL, :owner_id, :text_cv,
    NULL, :original_file_id, :format_file_id,
    NULL, CURRENT_DATE, TRUE
);

-- 3. sys_file (оригинал резюме)
INSERT INTO sys_file (id, version, create_ts, created_by, name, ext, file_size)
VALUES (:original_file_id, 1, NOW(), :operator, :orig_name, :orig_ext, :orig_size);

-- 4. sys_file (формат Hunttech)
INSERT INTO sys_file (id, version, create_ts, created_by, name, ext, file_size)
VALUES (:format_file_id, 1, NOW(), :operator, :fmt_name, :fmt_ext, :fmt_size);

-- 5. hunttech_some_files (оригинал)
INSERT INTO hunttech_some_files (
    id, version, create_ts, created_by,
    dtype, candidate_cv_id, file_description,
    file_descriptor_id, file_owner_id, file_type_id
) VALUES (
    gen_random_uuid(), 1, NOW(), :operator,
    'hunttech_SomeFilesCandidateCV', :cv_id, 'Оригинал резюме',
    :original_file_id, :owner_id, :RESUME_FILE_TYPE_ID
);

-- 6. hunttech_some_files (формат Hunttech)
INSERT INTO hunttech_some_files (
    id, version, create_ts, created_by,
    dtype, candidate_cv_id, file_description,
    file_descriptor_id, file_owner_id, file_type_id
) VALUES (
    gen_random_uuid(), 1, NOW(), :operator,
    'hunttech_SomeFilesCandidateCV', :cv_id, 'Резюме по формату Hunttech',
    :format_file_id, :owner_id, :RESUME_FILE_TYPE_ID
);

-- 7. hunttech_iteraction_list (автовзаимодействие "Новый контакт")
-- number_iteraction = MAX(number_iteraction) + 1
INSERT INTO hunttech_iteraction_list (
    id, version, create_ts, created_by, update_ts, updated_by,
    candidate_id, vacancy_id, iteraction_type_id,
    recrutier_id, recrutier_name, rating, comment_,
    number_iteraction, date_iteraction,
    current_priority, current_open_close
) VALUES (
    :iteraction_id, 1, NOW(), :operator, NOW(), :operator,
    :candidate_id, :DEFAULT_VACANCY_ID, :NEW_CONTACT_TYPE_ID,
    :owner_id, :owner_name, 4, 
    CONCAT('Взаимодействие создано автоматически ', TO_CHAR(NOW(), 'DD.MM.YYYY HH24:MI')),
    (SELECT COALESCE(MAX(number_iteraction), 0) + 1 FROM hunttech_iteraction_list),
    NOW(),
    NULL, NULL
);

-- SELECT-проверка всех записей
SELECT 'candidate' AS t, COUNT(*) FROM hunttech_job_candidate WHERE id = :candidate_id
UNION ALL SELECT 'cv', COUNT(*) FROM hunttech_candidate_cv WHERE id = :cv_id
UNION ALL SELECT 'sys_file_orig', COUNT(*) FROM sys_file WHERE id = :original_file_id
UNION ALL SELECT 'sys_file_fmt', COUNT(*) FROM sys_file WHERE id = :format_file_id
UNION ALL SELECT 'some_files', COUNT(*) FROM hunttech_some_files WHERE candidate_cv_id = :cv_id
UNION ALL SELECT 'iteraction', COUNT(*) FROM hunttech_iteraction_list WHERE id = :iteraction_id;

-- ОБЯЗАТЕЛЬНЫЙ ROLLBACK
ROLLBACK;
```

---

## 📁 Шаг 2: Копия файлов в fileStorage

Путь: `YYYY/MM/DD/<sys_file_id>.<ext>`  
Локально: `~/StudioProjects/hunttech_recruiting/fileStorage/`  
Прод: `/opt/app_home/fileStorage/`

```bash
# Для каждого файла (оригинал + формат)
YEAR=$(date +%Y)
MONTH=$(date +%m)
DAY=$(date +%d)

mkdir -p /path/to/fileStorage/$YEAR/$MONTH/$DAY

cp /path/to/source/file.docx /path/to/fileStorage/$YEAR/$MONTH/$DAY/$original_file_id.docx
cp /path/to/source/file.doc /path/to/fileStorage/$YEAR/$MONTH/$DAY/$format_file_id.doc

# Верификация размеров
stat -c%s /path/to/fileStorage/$YEAR/$MONTH/$DAY/$original_file_id.docx  # == :orig_size
stat -c%s /path/to/fileStorage/$YEAR/$MONTH/$DAY/$format_file_id.doc      # == :fmt_size
```

---

## ✅ Шаг 3: Реальный COMMIT

Те же INSERT, что и в репетиции, но с **COMMIT**.

```sql
BEGIN;

-- 1-7. Те же INSERT (см. Шаг 1.3)
-- ...

COMMIT;
```

**При ошибке COMMIT:**
```bash
# Удалить физические файлы
rm -f /path/to/fileStorage/$YEAR/$MONTH/$DAY/$original_file_id.docx
rm -f /path/to/fileStorage/$YEAR/$MONTH/$DAY/$format_file_id.doc
```

---

## 🔎 Шаг 4: Read-back и верификация

```sql
-- 1. Карточка кандидата с JOIN справочников
SELECT 
    jc.id, jc.version, jc.first_name, jc.middle_name, jc.second_name, jc.full_name,
    jc.email, jc.phone, jc.mobile_phone, jc.telegram_name,
    jc.city_of_residence_id, jc.current_company_id, jc.person_position_id,
    jc.status, jc.work_status,
    c.name AS city_name,
    comp.comany_name AS company_name,  -- опечатка в схеме!
    pos.position_ru_name AS position_name
FROM hunttech_job_candidate jc
LEFT JOIN hunttech_city c ON jc.city_of_residence_id = c.id
LEFT JOIN hunttech_company comp ON jc.current_company_id = comp.id
LEFT JOIN hunttech_person_position pos ON jc.person_position_id = pos.id
WHERE jc.id = :candidate_id;

-- 2. CV запись
SELECT * FROM hunttech_candidate_cv WHERE candidate_id = :candidate_id;

-- 3. sys_file записи
SELECT id, name, ext, file_size, create_date
FROM sys_file
WHERE id IN (:original_file_id, :format_file_id);

-- 4. some_files записи
SELECT * FROM hunttech_some_files WHERE candidate_cv_id = :cv_id;

-- 5. iteraction запись
SELECT * FROM hunttech_iteraction_list 
WHERE candidate_id = :candidate_id AND iteraction_type_id = :NEW_CONTACT_TYPE_ID;
```

**Верификация размеров:**
```sql
-- В sys_file file_size должен совпадать с физическим файлом
SELECT sf.id, sf.file_size, 
       (stat файл в fileStorage) AS physical_size
FROM sys_file sf
WHERE sf.id IN (:original_file_id, :format_file_id);
```

---

## 📋 Итоговый чек-лист (Definition of Done)

| Проверка | Критерий |
|----------|----------|
| ✅ Кандидат | Полные ФИО, контакты, city/company/position IDs, version=0 |
| ✅ CV | `original_file_cv_id` → sys_file (оригинал) И `file_cv_id` → sys_file (формат Hunttech) |
| ✅ Файлы | `file_size` в БД == `stat` физического файла для обоих |
| ✅ some_files | 2 записи: `dtype='hunttech_SomeFilesCandidateCV'`, `file_type_id=RESUME_FILE_TYPE_ID` |
| ✅ Взаимодействие | `iteraction_type_id=NEW_CONTACT_TYPE_ID`, `rating=4`, comment с датой, `vacancy_id=DEFAULT` |
| ✅ Контакты | `contact_info_checked=TRUE` в CV после сверки |

---

## 🗝️ Ключевые UUID (тест = прод)

| Сущность | UUID |
|----------|------|
| Взаимодействие «Новый контакт» 1.01 | `a4a9c7ff-11a1-1d72-3be7-e9484323b7fc` |
| Default-вакансия | `4fc9fb45-5f78-2494-47aa-5a5fa2c97660` |
| Тип файла «Резюме» | `fe77c780-a34d-c838-764d-7826eb0bed29` |
| Город Москва | `276b3aae-627e-9bd0-4695-12326b6ee946` |
| Компания MAYKOR | `d17365b8-b6b2-416d-8704-86acf461fb7d` |
| Оператор yakov | `80920aa2-bbfa-244e-8da4-331e2b0979ee` |
| Оператор hermes (бот) | логин `hermes` |

---

## ⚠️ Опечатки в схеме БД (учитывать в SQL)

| Таблица/Колонка | Правильное написание |
|-----------------|---------------------|
| `birdh_date` | не `birth_date` |
| `comany_name` | не `company_name` (в `hunttech_company`) |
| `decription_file_type` | не `description` (в `hunttech_file_type`) |
| `Iteraction` | сущность, не `Interaction` |
| `number_` | колонка с подчёркиванием (в `hunttech_iteraction`) |

---

## 📝 Пример выполнения (псевдокод)

```python
def create_candidate_hrm(resume_data, owner_id, owner_name, 
                         original_file_path, original_file_name,
                         format_file_path=None, format_file_name=None,
                         operator='hermes'):
    """
    Полный цикл заведения кандидата в HRM HuntTech.
    Возвращает (candidate_id, cv_id, iteraction_id) или вызывает исключение.
    """
    # 0. Проверка дублей
    duplicates = check_duplicates(resume_data)
    if duplicates and not confirm_duplicates(duplicates):
        raise DuplicateAborted("Пользователь отменил создание")
    
    # 1. Репетиция
    ids = generate_uuids()
    rehearsal_transaction(ids, resume_data, owner_id, owner_name, operator)
    
    # 2. Копия файлов
    copy_files_to_storage(ids, original_file_path, format_file_path)
    
    # 3. Реальный COMMIT
    try:
        commit_transaction(ids, resume_data, owner_id, owner_name, operator)
    except Exception:
        cleanup_files(ids)
        raise
    
    # 4. Read-back
    verify_records(ids)
    
    return ids.candidate_id, ids.cv_id, ids.iteraction_id
```

---

## 🔗 Связанные документы

- `DEVELOPER_GUIDE.md` — документация разработчика бота
- `README.md` — пользовательская документация бота
- Навык `hrm-candidate-creation` — источник правил
- Навык `hunttech-bot-common` — библиотека ботов