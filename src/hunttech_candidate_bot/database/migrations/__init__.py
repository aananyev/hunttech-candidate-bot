"""
Database migrations for HuntTech Candidate Bot.
Миграции для создания служебных таблиц бота (статистика, состояние и т.д.)
"""
from hunttech_bot_common.database.migrations import DatabaseMigrator
from hunttech_bot_common.database.pool import DatabasePool


MIGRATIONS = [
    {
        "version": 1,
        "name": "001_create_bot_stats_table.sql",
        "content": """
        CREATE TABLE IF NOT EXISTS hunttech_candidate_bot_stats (
            id SERIAL PRIMARY KEY,
            metric_name VARCHAR(100) NOT NULL UNIQUE,
            metric_value BIGINT NOT NULL DEFAULT 0,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        
        -- Начальные метрики
        INSERT INTO hunttech_candidate_bot_stats (metric_name, metric_value)
        VALUES 
            ('candidates_created', 0),
            ('duplicates_checked', 0),
            ('active_users', 0),
            ('ai_requests_today', 0)
        ON CONFLICT (metric_name) DO NOTHING;
        """,
    },
    {
        "version": 2,
        "name": "002_create_bot_state_table.sql",
        "content": """
        CREATE TABLE IF NOT EXISTS hunttech_candidate_bot_state (
            key VARCHAR(100) PRIMARY KEY,
            value JSONB NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """,
    },
]


async def run_candidate_bot_migrations(db_pool: DatabasePool):
    """Запуск миграций бота кандидатов."""
    # Создаём временную директорию для миграций
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        migrations_dir = os.path.join(tmpdir, "migrations")
        os.makedirs(migrations_dir, exist_ok=True)
        
        # Записываем файлы миграций
        for migration in MIGRATIONS:
            filepath = os.path.join(migrations_dir, migration["name"])
            with open(filepath, "w") as f:
                f.write(migration["content"])
        
        # Запускаем мигратор
        migrator = DatabaseMigrator(db_pool, migrations_dir=migrations_dir, table_name="hunttech_candidate_bot_migrations")
        await migrator.run()