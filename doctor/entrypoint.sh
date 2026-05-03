#!/bin/bash
# Genesis Doctor Container - Entrypoint
# 初始化容器环境：复制源码 → git init → 标记完成 → 待命

echo "=== Genesis Doctor 容器启动 ==="
echo "时间: $(date)"
echo "容器: $HOSTNAME"
echo "Python: $(/opt/venv/bin/python3 --version 2>/dev/null || echo '未安装')"

INIT_MARKER="/workspace/.doctor-initialized"

# 仅在首次（或 reset 后）执行初始化
if [ ! -f "$INIT_MARKER" ]; then
    echo "=== 初始化工作区 ==="

    # 从只读挂载复制源码到可写工作区（排除 venv/8GB、.git、runtime、cache）
    if [ -d "/src/genesis" ]; then
        echo "复制源码 /src/genesis → /workspace ..."
        tar -C /src/genesis \
            --exclude='.git' \
            --exclude='venv' \
            --exclude='runtime' \
            --exclude='__pycache__' \
            --exclude='*.pyc' \
            --exclude='archive' \
            -cf - . | tar -C /workspace -xf -
        echo "源码复制完成: $(find /workspace -name '*.py' | wc -l) 个 .py 文件"
    else
        echo "⚠️ /src/genesis 不存在，跳过源码复制"
    fi

    # 快照数据库（独立副本，不影响本体）
    # DB 通过 docker-compose 挂载到 /src/db/workshop_v4.sqlite (只读)
    DB_SRC="/src/db/workshop_v4.sqlite"
    DB_DST="/workspace/runtime/workshop_v4_snapshot.sqlite"
    mkdir -p /workspace/runtime
    if [ -f "$DB_SRC" ]; then
        cp "$DB_SRC" "$DB_DST"
        echo "DB 快照: $DB_DST"

        # NodeVault.DB_PATH = Path.home()/.genesis/workshop_v4.sqlite
        # 容器内 Path.home() = /，指向 /.genesis/workshop_v4.sqlite
        # 创建符号链接让 NodeVault 找到快照数据库（search_knowledge_nodes 依赖）
        mkdir -p /.genesis
        ln -sf "$DB_DST" /.genesis/workshop_v4.sqlite
        echo "DB 路径修复: /.genesis/workshop_v4.sqlite -> $DB_DST"
    else
        echo "⚠️ DB 未挂载，跳过快照"
    fi

    # Git：保留历史，新基线叠加在旧快照之上
    cd /workspace
    git config --global --add safe.directory /workspace
    git config --global user.email "doctor@genesis.local"
    git config --global user.name "Genesis Doctor"
    if [ ! -d .git ]; then
        git init -q
        echo "Git: 首次初始化"
    else
        echo "Git: 保留历史 ($(git log --oneline snapshot/ 2>/dev/null | head -1 || echo 'no snapshots'))"
    fi
    git add -A
    git commit -q -m "Doctor: baseline from production $(date +%Y%m%d_%H%M%S)" --allow-empty
    echo "Git 基线提交 ($(git rev-parse --short HEAD 2>/dev/null || echo 'no commit'))"

    touch "$INIT_MARKER"
    echo "=== 初始化完成 ==="
else
    echo "工作区已初始化，跳过"
fi

# 保持容器运行
echo "=== 容器进入待命状态 ==="
sleep infinity
