#!/bin/bash
# 在主节点运行，将代码和元信息同步到 Yoga (副本节点)
# 使用方式: ./sync_to_replica.sh <yoga_ip> <yoga_user>

TARGET_IP=$1
TARGET_USER=${2:-$USER}

if [ -z "$TARGET_IP" ]; then
    echo "用法: $0 <yoga_ip> [yoga_user]"
    echo "例如: $0 192.168.1.100 chendechusn"
    exit 1
fi

echo "🚀 开始同步 Genesis 到 Yoga 节点 ($TARGET_USER@$TARGET_IP)..."

# 1. 创建目标目录
ssh "$TARGET_USER@$TARGET_IP" "mkdir -p ~/Genesis ~/.genesis"

# 2. 同步代码仓库 (排除臃肿的 venv 和 git 历史)
echo "📦 同步代码库..."
rsync -avz --exclude 'venv/' --exclude '.git/' --exclude '__pycache__/' \
    /home/chendechusn/Genesis/Genesis/ "$TARGET_USER@$TARGET_IP:~/Genesis/"

# 3. 同步 NodeVault (SQLite DB) 和 Tracer
echo "🧠 同步 NodeVault (元信息系统)..."
rsync -avz /home/chendechusn/.genesis/workshop_v4.sqlite "$TARGET_USER@$TARGET_IP:~/.genesis/"

# 同步运行时的 trace DB (可选)
if [ -d "/home/chendechusn/Genesis/Genesis/runtime" ]; then
    rsync -avz /home/chendechusn/Genesis/Genesis/runtime/traces.db "$TARGET_USER@$TARGET_IP:~/Genesis/runtime/"
fi

echo "✅ 同步完成！请在 Yoga 上运行 ~/Genesis/scripts/replica_setup/bootstrap_yoga.sh"
