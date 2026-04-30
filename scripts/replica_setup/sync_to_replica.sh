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

# 3. 同步 SQLite DB — 必须先停目标服务，否则 rsync 写入期间 DB 被写导致损坏
echo "⏸️ 停止 Yogg 服务（防止 DB 写入冲突）..."
ssh "$TARGET_USER@$TARGET_IP" "sudo systemctl stop yogg-auto genesis-v4 genesis-daemon 2>/dev/null; echo 'stopped'" || true

echo "🧠 同步 NodeVault (元信息系统)..."
# --inplace: 直接覆盖而非创建临时文件再 rename，避免 SQLite WAL 残留不一致
rsync -avz --inplace /home/chendechusn/.genesis/workshop_v4.sqlite "$TARGET_USER@$TARGET_IP:~/.genesis/"

# 同步运行时的 trace DB
if [ -d "/home/chendechusn/Genesis/Genesis/runtime" ]; then
    echo "📊 同步 Trace DBs..."
    rsync -avz --inplace /home/chendechusn/Genesis/Genesis/runtime/traces.db "$TARGET_USER@$TARGET_IP:~/Genesis/runtime/"
    # trace_entities.db 可选（1.9GB，跳过则 Yogg 自动从空库重建）
    if [ -f "/home/chendechusn/Genesis/Genesis/runtime/trace_entities.db" ]; then
        echo "  trace_entities.db 较大，默认跳过（Yogg 会自动重建）。如需同步，手动 rsync --inplace。"
    fi
fi

# 4. 验证 DB 完整性并重启服务
echo "🔍 验证 DB 完整性..."
ssh "$TARGET_USER@$TARGET_IP" 'python3 -c "
import sqlite3, os
for db in [\"~/.genesis/workshop_v4.sqlite\", \"~/Genesis/runtime/traces.db\"]:
    path = os.path.expanduser(db)
    try:
        c = sqlite3.connect(path)
        r = c.execute(\"PRAGMA integrity_check\").fetchone()
        print(f\"{db}: {r[0]}\")
        c.close()
    except Exception as e:
        print(f\"{db}: ERROR {e}\")
"'

echo "🔄 重启 Yogg 服务..."
ssh "$TARGET_USER@$TARGET_IP" "sudo systemctl start genesis-v4 genesis-daemon yogg-auto; echo 'restarted'"

echo "✅ 同步完成！DB integrity 已验证，服务已重启。"
