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
        docker exec "$CONTAINER" rm -f /workspace/.doctor-initialized
        docker restart "$CONTAINER" 2>&1
        sleep 3
        echo -e "${GREEN}Workspace reset complete.${NC}"
    else
        # 删除 volume 并重新启动
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
    help|--help|-h)
        echo "Genesis Doctor - 安全沙箱 CLI"
        echo ""
        echo "用法: doctor.sh <command> [args]"
        echo ""
        echo "命令:"
        echo "  start          启动 Doctor 容器"
        echo "  stop           停止容器"
        echo "  reset          重置工作区（重新从本体复制源码）"
        echo "  exec <cmd>     在容器内执行命令"
        echo "  python [code]  执行 Python 代码（无参数进入 REPL）"
        echo "  test [path]    运行测试（默认 tests/）"
        echo "  diff           查看所有修改"
        echo "  patch          导出修改为 .patch 文件"
        echo "  apply          将修改应用到本体（需确认）"
        echo "  status         查看容器状态"
        echo "  cat <file>     查看容器内文件"
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        echo "Run 'doctor.sh help' for usage."
        exit 1
        ;;
esac
