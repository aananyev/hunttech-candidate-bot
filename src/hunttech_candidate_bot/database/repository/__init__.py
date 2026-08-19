"""
Database repository — базовый репозиторий для работы с таблицами бота.
"""
from hunttech_bot_common.database import BaseRepository
from hunttech_bot_common.database.pool import DatabasePool


class CandidateBotRepository(BaseRepository):
    """Репозиторий для служебных таблиц бота кандидатов."""
    
    def __init__(self, pool: DatabasePool):
        super().__init__(pool, "hunttech_candidate_bot_stats")
    
    async def increment_metric(self, metric_name: str, value: int = 1):
        """Инкремент метрики."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO hunttech_candidate_bot_stats (metric_name, metric_value, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (metric_name) DO UPDATE SET
                    metric_value = hunttech_candidate_bot_stats.metric_value + EXCLUDED.metric_value,
                    updated_at = NOW()
            """, metric_name, value)
    
    async def get_metric(self, metric_name: str) -> int:
        """Получить значение метрики."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT metric_value FROM hunttech_candidate_bot_stats WHERE metric_name = $1",
                metric_name
            )
            return row["metric_value"] if row else 0
    
    async def get_all_metrics(self) -> dict:
        """Получить все метрики."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT metric_name, metric_value FROM hunttech_candidate_bot_stats")
            return {row["metric_name"]: row["metric_value"] for row in rows}


class BotStateRepository(BaseRepository):
    """Репозиторий для хранения состояния бота (key-value)."""
    
    def __init__(self, pool: DatabasePool):
        super().__init__(pool, "hunttech_candidate_bot_state")
    
    async def set_state(self, key: str, value: dict):
        """Сохранить состояние."""
        import json
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO hunttech_candidate_bot_state (key, value, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_at = NOW()
            """, key, json.dumps(value))
    
    async def get_state(self, key: str) -> dict | None:
        """Получить состояние."""
        import json
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value FROM hunttech_candidate_bot_state WHERE key = $1",
                key
            )
            return json.loads(row["value"]) if row else None