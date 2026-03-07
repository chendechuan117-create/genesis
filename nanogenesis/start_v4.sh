#!/bin/bash
# Genesis V4 启动脚本
cd /home/chendechusn/Genesis/nanogenesis

# 杀掉旧进程
pkill -f "discord_bot.py" 2>/dev/null
sleep 1

# 激活虚拟环境并启动
source venv/bin/activate
echo "🔮 Genesis V4.2 (Glassbox) 正在启动..."
python -u discord_bot.py
