#!/bin/bash
# Genesis V4 独立启动脚本
cd "$(dirname "$0")"

pkill -f "Genesis/discord_bot.py" 2>/dev/null
sleep 1

# 使用 nanogenesis 的 venv（共享依赖）
VENV="/home/chendechusn/Genesis/nanogenesis/venv"
if [ -d "$VENV" ]; then
    source "$VENV/bin/activate"
else
    echo "⚠️ venv not found at $VENV"
    exit 1
fi

echo "🔮 Genesis V4.2 (Glassbox) 启动中..."
python -u discord_bot.py
