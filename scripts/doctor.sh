#!/bin/bash
# Genesis Doctor - 安全沙箱 CLI
# Genesis 通过 shell 工具调用此脚本与 Doctor 容器交互
#
# 用法:
#   doctor.sh start          启动 Doctor 容器
#   doctor.sh stop           停止容器
#   doctor.sh reset          重置工作区（重新从本体复制源码）
#   doctor.sh exec <cmd>     在容器内执行命令
#   doctor.sh python <code>  在容器内执行 Python 代码
#   doctor.sh test [path]    运行测试
#   doctor.sh diff           查看相对于本体的所有修改
#   doctor.sh patch          导出修改为 patch 文件
#   doctor.sh apply          将 Doctor 的修改应用到本体（需人工确认）
#   doctor.sh status         查看容器状态
#   doctor.sh cat <file>     查看容器内文件
#   doctor.sh edit <file>    用 sed/heredoc 修改容器内文件（配合 exec）

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DOCTOR_DIR="$PROJECT_DIR/doctor"
CONTAINER="genesis-doctor"
PYTHON="/opt/venv/bin/python3"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

_is_running() {
    docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null | grep -q true
}

_ensure_running() {
    if ! _is_running; then
        echo -e "${YELLOW}Doctor container not running. Starting...${NC}"
        cmd_start
    fi
}

cmd_start() {
    if _is_running; then
        echo -e "${GREEN}Doctor container already running.${NC}"
        return 0
    fi
    
    echo "🔬 Starting Genesis Doctor container..."
    cd "$DOCTOR_DIR"
    docker compose up -d --remove-orphans 2>&1
    
    # 等待初始化完成
    for i in $(seq 1 30); do
        if docker exec "$CONTAINER" test -f /workspace/.doctor-initialized 2>/dev/null; then
            echo -e "${GREEN}✅ Doctor container ready.${NC}"
            return 0
        fi
        sleep 1
    done
    echo -e "${RED}⚠️ Container started but initialization may still be in progress.${NC}"
}

cmd_stop() {
    echo "Stopping Doctor container..."
    cd "$DOCTOR_DIR"
    docker compose down 2>&1
    echo -e "${GREEN}Doctor container stopped.${NC}"
}

cmd_reset() {
    echo "🔄 Resetting Doctor workspace..."
    if _is_running; then
        # ── 快照保护：reset 前自动保存当前改动 ──
        docker exec -w /workspace "$CONTAINER" bash -c '
            if [ -d .git ]; then
                git add -A 2>/dev/null
                CHANGES=$(git diff --cached --stat 2>/dev/null)
                if [ -n "$CHANGES" ]; then
                    TS=$(date +%Y%m%d_%H%M%S)
                    git commit -q -m "auto-snapshot before reset $TS"
                    git tag "snapshot/$TS"
                    echo "📸 Snapshot saved: snapshot/$TS"
                    echo "$CHANGES" | tail -1
                    # 保留最近 3 个快照，删除更早的
                    TAGS=$(git tag -l "snapshot/*" | sort -r)
                    COUNT=0
                    for TAG in $TAGS; do
                        COUNT=$((COUNT + 1))
                        if [ $COUNT -gt 3 ]; then
                            git tag -d "$TAG" >/dev/null 2>&1
                        fi
                    done
                    git gc --quiet 2>/dev/null
                else
                    echo "📸 No changes to snapshot"
                fi
            fi
        '
        docker exec "$CONTAINER" rm -f /workspace/.doctor-initialized
        docker restart "$CONTAINER" 2>&1
        sleep 3
        echo -e "${GREEN}Workspace reset complete (previous changes saved as snapshot).${NC}"
    else
        echo -e "${YELLOW}⚠️ Container not running — cannot snapshot. Starting fresh.${NC}"
        cd "$DOCTOR_DIR"
        docker compose down -v 2>&1
        cmd_start
    fi
}

cmd_exec() {
    _ensure_running
    docker exec -w /workspace "$CONTAINER" "$@"
}

cmd_python() {
    _ensure_running
    if [ $# -eq 0 ]; then
        docker exec -it -w /workspace "$CONTAINER" "$PYTHON"
    else
        docker exec -w /workspace "$CONTAINER" "$PYTHON" -c "$*"
    fi
}

cmd_test() {
    _ensure_running
    local target="${1:-tests/}"
    echo "🧪 Running tests: $target"
    docker exec -w /workspace -e PYTHONPATH=/workspace "$CONTAINER" \
        "$PYTHON" -m pytest "$target" -v --tb=short 2>&1
}

cmd_diff() {
    _ensure_running
    docker exec -w /workspace "$CONTAINER" git diff HEAD
}

cmd_patch() {
    _ensure_running
    local patch_file="$PROJECT_DIR/doctor-patch-$(date +%Y%m%d-%H%M%S).patch"
    docker exec -w /workspace "$CONTAINER" git diff HEAD > "$patch_file"
    if [ -s "$patch_file" ]; then
        echo -e "${GREEN}Patch exported to: $patch_file${NC}"
        echo "Lines changed: $(wc -l < "$patch_file")"
    else
        rm -f "$patch_file"
        echo -e "${YELLOW}No changes to export.${NC}"
    fi
}

cmd_apply() {
    _ensure_running
    
    # 先生成 diff
    local diff
    diff=$(docker exec -w /workspace "$CONTAINER" git diff HEAD)
    
    if [ -z "$diff" ]; then
        echo -e "${YELLOW}No changes to apply.${NC}"
        return 0
    fi
    
    echo "📋 Changes to apply to production:"
    echo "─────────────────────────────────"
    echo "$diff" | head -50
    local total_lines
    total_lines=$(echo "$diff" | wc -l)
    if [ "$total_lines" -gt 50 ]; then
        echo "... ($total_lines total lines, showing first 50)"
    fi
    echo "─────────────────────────────────"
    echo -e "${RED}⚠️  This will modify PRODUCTION code!${NC}"
    read -p "Apply these changes? [y/N] " confirm
    
    if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
        echo "$diff" | git -C "$PROJECT_DIR" apply -
        echo -e "${GREEN}✅ Changes applied to production.${NC}"
        echo -e "${YELLOW}⚠️  Remember to restart Genesis: systemctl --user restart genesis-v4${NC}"
    else
        echo "Cancelled."
    fi
}

cmd_status() {
    if _is_running; then
        echo -e "${GREEN}● Doctor container: running${NC}"
        docker exec -w /workspace "$CONTAINER" bash -c "
            echo \"  Python: \$($PYTHON --version 2>&1)\"
            echo \"  Workspace files: \$(find /workspace -name '*.py' | wc -l) .py files\"
            echo \"  Git status:\"
            git diff --stat HEAD 2>/dev/null | head -10
        "
    else
        echo -e "${RED}● Doctor container: stopped${NC}"
    fi
}

cmd_cat() {
    _ensure_running
    docker exec -w /workspace "$CONTAINER" cat "$@"
}

cmd_snapshots() {
    _ensure_running
    echo "📸 Doctor workspace snapshots:"
    docker exec -w /workspace "$CONTAINER" bash -c '
        TAGS=$(git tag -l "snapshot/*" 2>/dev/null | sort -r)
        if [ -z "$TAGS" ]; then
            echo "  (no snapshots)"
            exit 0
        fi
        for TAG in $TAGS; do
            COMMIT=$(git rev-list -1 "$TAG" 2>/dev/null)
            SHORT=$(echo "$COMMIT" | head -c 7)
            DATE=$(git log -1 --format="%ci" "$COMMIT" 2>/dev/null)
            STAT=$(git diff --stat "$COMMIT"^.."$COMMIT" 2>/dev/null | tail -1)
            echo "  $TAG  ($SHORT, $DATE)"
            echo "    $STAT"
        done
    '
}

cmd_restore() {
    _ensure_running
    local tag="$1"
    if [ -z "$tag" ]; then
        echo -e "${RED}Usage: doctor.sh restore <snapshot-tag>${NC}"
        echo "Run 'doctor.sh snapshots' to see available tags."
        exit 1
    fi
    echo "🔄 Restoring snapshot: $tag"
    docker exec -w /workspace "$CONTAINER" bash -c "
        if ! git rev-parse \"$tag\" >/dev/null 2>&1; then
            echo 'Error: tag $tag not found'
            exit 1
        fi
        git checkout \"$tag\" -- . 2>/dev/null
        echo '✅ Workspace restored to $tag'
        git diff --stat HEAD | tail -5
    "
}

# ── 路由 ──
case "${1:-help}" in
    start)  cmd_start ;;
    stop)   cmd_stop ;;
    reset)  cmd_reset ;;
    exec)   shift; cmd_exec "$@" ;;
    python) shift; cmd_python "$@" ;;
    test)   shift; cmd_test "$@" ;;
    diff)   cmd_diff ;;
    patch)  cmd_patch ;;
    apply)  cmd_apply ;;
    status) cmd_status ;;
    cat)    shift; cmd_cat "$@" ;;
    snapshots) cmd_snapshots ;;
    restore) shift; cmd_restore "$@" ;;
    help|--help|-h)
        echo "Genesis Doctor - 安全沙箱 CLI"
        echo ""
        echo "用法: doctor.sh <command> [args]"
        echo ""
        echo "命令:"
        echo "  start          启动 Doctor 容器"
        echo "  stop           停止容器"
        echo "  reset          重置工作区（自动快照当前改动，然后从本体复制）"
        echo "  exec <cmd>     在容器内执行命令"
        echo "  python [code]  执行 Python 代码（无参数进入 REPL）"
        echo "  test [path]    运行测试（默认 tests/）"
        echo "  diff           查看所有修改"
        echo "  patch          导出修改为 .patch 文件"
        echo "  apply          将修改应用到本体（需确认）"
        echo "  status         查看容器状态"
        echo "  cat <file>     查看容器内文件"
        echo "  snapshots      列出所有快照（保留最近 3 个）"
        echo "  restore <tag>  恢复指定快照（如 snapshot/20260412_180000）"
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        echo "Run 'doctor.sh help' for usage."
        exit 1
        ;;
esac
