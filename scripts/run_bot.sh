#!/usr/bin/env bash
# HuntTech Candidate Bot — запуск бота
# Использование: ./scripts/run_bot.sh

set -euo pipefail

# Корень проекта
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Виртуальное окружение Hermes
VENV_PYTHON="$HOME/.hermes/hermes-agent/venv/bin/python3"

if [[ ! -f "$VENV_PYTHON" ]]; then
    echo "❌ Python не найден: $VENV_PYTHON"
    echo "Убедитесь, что Hermes Agent установлен и venv создан."
    exit 1
fi

# Проверка .env
if [[ ! -f .env ]]; then
    echo "⚠️  Файл .env не найден. Копирую из .env.example..."
    cp .env.example .env
    echo "✏️  Отредактируйте .env и задайте TELEGRAM_BOT_TOKEN, AI_API_KEY и др."
    exit 1
fi

# Проверка токена
if ! grep -q "^TELEGRAM_BOT_TOKEN=" .env || grep -q "^TELEGRAM_BOT_TOKEN=$" .env; then
    echo "❌ TELEGRAM_BOT_TOKEN не задан в .env"
    exit 1
fi

echo "🚀 Запуск HuntTech Candidate Bot..."
echo "📁 Проект: $PROJECT_ROOT"
echo "🐍 Python: $VENV_PYTHON"

# Запуск
exec "$VENV_PYTHON" -m hunttech_candidate_bot