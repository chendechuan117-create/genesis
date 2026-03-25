#!/bin/bash
# Genesis V4 启动脚本
cd "$(dirname "$0")"

pkill -f "Genesis/discord_bot.py" 2>/dev/null
sleep 1

VENV="$(pwd)/venv"
if [ -d "$VENV" ]; then
    source "$VENV/bin/activate"
else
    echo "⚠️ venv not found at $VENV"
    exit 1
fi

echo "🔮 Genesis V4 启动中..."
python -u discord_bot.py
