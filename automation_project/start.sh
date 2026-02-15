#!/bin/bash

# 自动化赚钱系统启动脚本

echo "🚀 启动自动化赚钱系统..."
echo "================================"

# 检查Python环境
if [ ! -d "automation_env" ]; then
    echo "❌ 虚拟环境不存在，正在创建..."
    python -m venv automation_env
    source automation_env/bin/activate
    pip install playwright beautifulsoup4 requests schedule
    echo "✅ 虚拟环境创建完成"
else
    echo "✅ 虚拟环境已存在"
fi

# 激活虚拟环境
source automation_env/bin/activate

# 检查Playwright浏览器
if [ ! -f "automation_env/bin/playwright" ]; then
    echo "📦 安装Playwright浏览器..."
    python -m playwright install chromium
    echo "✅ 浏览器安装完成"
else
    echo "✅ Playwright已安装"
fi

# 创建必要的目录
echo "📁 创建目录结构..."
mkdir -p data/{results,materials,backups}
mkdir -p logs
mkdir -p config

echo "📊 系统信息:"
echo "  Python版本: $(python --version)"
echo "  工作目录: $(pwd)"
echo "  虚拟环境: automation_env"

# 启动调度器
echo "🤖 启动任务调度器..."
echo "================================"
echo "按 Ctrl+C 停止系统"
echo "================================"

cd src && python scheduler.py