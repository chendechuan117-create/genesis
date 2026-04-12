#!/bin/bash
# 在 Yoga (副本节点) 上运行，用于初始化 Genesis 环境
# 请在 ~/Genesis 目录下运行此脚本

set -e

echo "🚀 开始初始化 Genesis 副本节点环境..."

# 1. 检查 Python 3.14
if ! command -v python3.14 &> /dev/null && ! python3 --version | grep -q "3.14"; then
    echo "⚠️ 警告: 未检测到 Python 3.14。Genesis V4 依赖 Python 3.14。"
    echo "如果是 Arch/EndeavourOS，请执行: yay -S python"
    echo "如果是 Ubuntu，请使用 deadsnakes PPA 或源码编译。"
    read -p "按 Enter 继续尝试，或 Ctrl+C 取消..."
fi

# 2. 创建 venv 并安装依赖
echo "📦 配置虚拟环境..."
cd ~/Genesis
python3 -m venv venv
source venv/bin/activate

echo "📦 安装 Python 依赖..."
pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "⚠️ 找不到 requirements.txt，跳过依赖安装。"
fi

# 3. 处理 .env (极其重要：剥离 Discord Token 防止两个 Bot 抢占)
echo "🔒 配置安全环境变量..."
if [ -f ".env" ]; then
    cp .env .env.bak
    # 删除 Discord Token，副本节点不应该启动 Discord Bot，只跑 Daemon/Verifier/Doctor
    sed -i '/DISCORD_BOT_TOKEN/d' .env
    echo "# 副本节点已禁用 DISCORD_BOT_TOKEN，防止冲突" >> .env
else
    echo "⚠️ 找不到 .env 文件，请从主节点手动复制并删除 DISCORD_BOT_TOKEN。"
fi

# 4. 初始化 Doctor 沙盒 (Docker)
if command -v docker &> /dev/null; then
    echo "🐳 检查 Docker 沙盒环境..."
    cd doctor && docker compose build || echo "Docker build 失败，请之后手动配置。"
    cd ..
else
    echo "⚠️ 未安装 Docker，genesis-doctor 沙盒将不可用。"
fi

echo "✅ 初始化完成！"
echo "你可以将此节点用作:"
echo "1. 知识验证器: python genesis/v4/verifier.py"
echo "2. 后台守护进程: ./scripts/autopilot.sh (后台清理/提纯)"
echo "3. API 服务器: ./start_api.sh"
