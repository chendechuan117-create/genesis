#!/bin/bash
# NanoGenesis远程环境部署脚本
# 使用方法：./deploy_remote.sh user@remote_host

set -e

if [ $# -ne 1 ]; then
    echo "使用方法: $0 user@remote_host"
    exit 1
fi

REMOTE_HOST="$1"
LOCAL_DIR="."
REMOTE_DIR="~/nanogenesis-deploy"

echo "🚀 开始部署到远程主机: $REMOTE_HOST"

# 1. 检查远程Docker是否安装
echo "🔍 检查远程Docker安装..."
ssh "$REMOTE_HOST" "command -v docker >/dev/null 2>&1 || { echo 'Docker未安装，正在安装...'; curl -fsSL https://get.docker.com | sh; sudo usermod -aG docker \$USER; }"

# 2. 检查远程Docker Compose是否安装
echo "🔍 检查远程Docker Compose安装..."
ssh "$REMOTE_HOST" "command -v docker-compose >/dev/null 2>&1 || { echo 'Docker Compose未安装，正在安装...'; sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-\$(uname -s)-\$(uname -m)" -o /usr/local/bin/docker-compose; sudo chmod +x /usr/local/bin/docker-compose; }"

# 3. 创建远程目录
echo "📁 创建远程目录..."
ssh "$REMOTE_HOST" "mkdir -p $REMOTE_DIR"

# 4. 传输文件
echo "📤 传输文件到远程主机..."
rsync -avz --exclude='__pycache__' --exclude='.git' --exclude='venv' --exclude='*.pyc'     "$LOCAL_DIR/" "$REMOTE_HOST:$REMOTE_DIR/"

# 5. 在远程主机上构建和启动
echo "🔨 在远程主机上构建Docker镜像..."
ssh "$REMOTE_HOST" "cd $REMOTE_DIR && docker build -t nanogenesis:latest ."

echo "🚀 启动NanoGenesis容器..."
ssh "$REMOTE_HOST" "cd $REMOTE_DIR && docker-compose up -d"

echo "✅ 部署完成！"
echo "📊 检查容器状态："
ssh "$REMOTE_HOST" "docker ps | grep nanogenesis"
echo ""
echo "📝 查看日志："
echo "  ssh $REMOTE_HOST 'docker logs -f nanogenesis'"
echo ""
echo "🔧 停止容器："
echo "  ssh $REMOTE_HOST 'cd $REMOTE_DIR && docker-compose down'"
