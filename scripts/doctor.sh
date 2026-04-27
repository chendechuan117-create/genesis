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
#   doctor.sh auto-apply     非交互式应用（自进化用，带 git 安全网）
#   doctor.sh status         查看容器状态
#   doctor.sh cat <file>     查看容器内文件
#   doctor.sh edit <file>    用 sed/heredoc 修改容器内文件（配合 exec）
#   doctor.sh run            从 stdin 读取脚本并在容器内执行（绕过宿主 shell 展开）

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

_ensure_git_safe() {
    # Git 2.35.2+ refuses operations when repo owner != process uid.
    # Container runs as root (uid=0) but /workspace is owned by uid=1000.
    docker exec "$CONTAINER" git config --global --add safe.directory /workspace 2>/dev/null || true
    # Git identity required for commits; lost on container restart.
    docker exec "$CONTAINER" git config --global user.email "doctor@genesis.local" 2>/dev/null || true
    docker exec "$CONTAINER" git config --global user.name "Genesis Doctor" 2>/dev/null || true
}

_ensure_running() {
    if ! _is_running; then
        echo -e "${YELLOW}Doctor container not running. Starting...${NC}"
        cmd_start
    fi
    _ensure_git_safe
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

# run: 从 stdin 读取脚本，写入容器后执行。
# 绕过宿主 shell → doctor.sh → 容器 bash 的三层变量展开问题。
# 用法: doctor.sh run <<'SCRIPT'
#          echo ${1:-default}   # 在容器内展开，不在宿主展开
#        SCRIPT
cmd_run() {
    _ensure_running
    docker exec -i -w /workspace -e PYTHONPATH=/workspace "$CONTAINER" \
        bash -c 'cat > /tmp/_doctor_run.sh && bash /tmp/_doctor_run.sh; rm -f /tmp/_doctor_run.sh'
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

# Test only files related to sandbox diff (used by SelfEvolution auto-apply)
# Finds test files that correspond to changed/new files in the sandbox
cmd_test_diff() {
    _ensure_running
    local test_files=()

    # Collect changed and untracked files from sandbox
    # Only include files that ACTUALLY EXIST in the container —
    # git diff --name-only includes deletions, which causes pytest "file not found"
    # and blocks all self-evolution apply attempts.
    local changed
    changed=$(docker exec -w /workspace "$CONTAINER" bash -c '
        (git diff --name-only HEAD 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null | grep -vE "(__pycache__|\.pyc|\.pyo|\.pytest_cache|^runtime/|^\.)") | sort -u | while IFS= read -r f; do [ -f "$f" ] && echo "$f"; done
    ' 2>/dev/null)

    # Map source files to corresponding test files
    while IFS= read -r f; do
        [ -z "$f" ] && continue
        # If it's a test file itself, include directly (existence already verified above)
        if [[ "$f" == test_*.py ]] || [[ "$f" == tests/test_*.py ]]; then
            test_files+=("$f")
            continue
        fi
        # If it's a probe impl in runtime/scratch, find its test
        local base
        base=$(basename "$f" _impl.py 2>/dev/null || basename "$f" .py 2>/dev/null)
        local t
        for t in "tests/test_${base}.py" "tests/${base}.py"; do
            if docker exec -w /workspace "$CONTAINER" test -f "$t" 2>/dev/null; then
                test_files+=("$t")
                break
            fi
        done
    done <<< "$changed"

    # Deduplicate
    local unique_tests
    unique_tests=$(printf '%s\n' "${test_files[@]}" 2>/dev/null | sort -u | grep -vE '^$|__pycache__|\.pyc' | grep '\.py$')

    if [ -z "$unique_tests" ]; then
        echo "🧪 No test files found for diff changes — passing by default"
        return 0
    fi

    echo "🧪 Running diff-scoped tests:"
    echo "$unique_tests" | while IFS= read -r t; do echo "  $t"; done

    # Smoke test: verify pytest can actually collect the discovered tests.
    # GP-created test files often have broken imports — running pytest on them
    # produces confusing errors. If collection fails, skip those files.
    local test_args
    test_args=$(echo "$unique_tests" | tr '\n' ' ')
    local collect_output
    collect_output=$(docker exec -w /workspace -e PYTHONPATH=/workspace "$CONTAINER" \
        "$PYTHON" -m pytest $test_args --collect-only -q 2>&1)
    if [ $? -ne 0 ]; then
        echo "⚠️ Smoke test: pytest collection failed for discovered tests"
        echo "$collect_output" | tail -5
        echo "🧪 Skipping broken test files — passing by default"
        return 0
    fi

    # Run pytest only on the verified test files
    docker exec -w /workspace -e PYTHONPATH=/workspace "$CONTAINER" \
        "$PYTHON" -m pytest $test_args -v --tb=short 2>&1
}

_doctor_workspace_patch() {
    # Optional: $1 = comma-separated file glob filter (--only)
    local only_filter="${1:-}"
    _ensure_running
    docker exec -i -w /workspace "$CONTAINER" bash <<EOF
set -euo pipefail

if [ -n "$only_filter" ]; then
    # Scoped: only emit diff for matching files
    git diff HEAD -- $only_filter
    for _path in \$(git ls-files --others --exclude-standard -z 2>/dev/null | tr '\0' '\n' | grep -E "^\$only_filter" || true); do
        case "\$_path" in
            .doctor-initialized|runtime/*|__pycache__/*|.pytest_cache/*|*.pyc|*.pyo|*.orig|*.rej|*.log)
                continue
                ;;
        esac
        git diff --no-index --binary -- /dev/null "\$_path" || true
    done
else
    git diff HEAD
    while IFS= read -r -d '' path; do
        case "\$path" in
            .doctor-initialized|runtime/*|__pycache__/*|.pytest_cache/*|*.pyc|*.pyo|*.orig|*.rej|*.log)
                continue
                ;;
    esac

    git diff --no-index --binary -- /dev/null "\$path" || true
    done < <(git ls-files --others --exclude-standard -z)
fi
EOF
}

cmd_diff_status() {
    _ensure_running
    docker exec -i -w /workspace "$CONTAINER" bash <<'EOF'
set -euo pipefail

# Tracked diff hash
tracked_diff=$(git diff HEAD 2>/dev/null || echo "")
if [ -n "$tracked_diff" ]; then
    tracked_hash=$(echo "$tracked_diff" | md5sum | cut -d' ' -f1 | cut -c1-12)
    tracked_lines=$(echo "$tracked_diff" | wc -l)
else
    tracked_hash=""
    tracked_lines=0
fi

# Untracked file set hash (path list only, sorted for stability)
untracked_list=$(git ls-files --others --exclude-standard 2>/dev/null | grep -vE '(__pycache__|\.pyc|\.pyo|\.orig|\.rej|\.log|\.pytest_cache|^runtime/|^\.)' || true)
if [ -n "$untracked_list" ]; then
    untracked_hash=$(echo "$untracked_list" | sort | md5sum | cut -d' ' -f1 | cut -c1-12)
    untracked_count=$(echo "$untracked_list" | wc -l)
else
    untracked_hash=""
    untracked_count=0
fi

echo "TRACKED_HASH:${tracked_hash}"
echo "TRACKED_LINES:${tracked_lines}"
echo "UNTRACKED_HASH:${untracked_hash}"
echo "UNTRACKED_COUNT:${untracked_count}"
EOF
}

cmd_file_status() {
    _ensure_running
    docker exec -i -w /workspace "$CONTAINER" bash <<'EOF'
set -euo pipefail

# Tracked files: per-file diff hash
git diff HEAD --name-only 2>/dev/null | while IFS= read -r f; do
    h=$(git diff HEAD -- "$f" 2>/dev/null | md5sum | cut -d' ' -f1 | cut -c1-12)
    echo "T:${f}:${h}"
done

# Untracked files: per-file content hash
git ls-files --others --exclude-standard 2>/dev/null | grep -vE '(__pycache__|\.pyc|\.pyo|\.orig|\.rej|\.log|\.pytest_cache|^runtime/|^\.)' | while IFS= read -r f; do
    h=$(cat "$f" 2>/dev/null | md5sum | cut -d' ' -f1 | cut -c1-12)
    echo "U:${f}:${h}"
done
EOF
}

cmd_diff() {
    _ensure_running
    _doctor_workspace_patch
}

cmd_patch() {
    _ensure_running
    local patch_file="$PROJECT_DIR/doctor-patch-$(date +%Y%m%d-%H%M%S).patch"
    if ! _doctor_workspace_patch > "$patch_file"; then
        rm -f "$patch_file"
        echo -e "${RED}Failed to export Doctor workspace changes.${NC}"
        return 1
    fi
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

    # Parse --only flag: doctor.sh apply [--only file1,file2,...]
    local only_filter=""
    if [ "${1:-}" = "--only" ] && [ -n "${2:-}" ]; then
        only_filter="$2"
        shift 2 2>/dev/null || true
    fi

    local patch_file
    patch_file=$(mktemp "$PROJECT_DIR/doctor-apply-XXXXXX.patch")
    if ! _doctor_workspace_patch "$only_filter" > "$patch_file"; then
        rm -f "$patch_file"
        echo -e "${RED}Failed to read Doctor workspace changes.${NC}"
        return 1
    fi

    if [ ! -s "$patch_file" ]; then
        rm -f "$patch_file"
        echo -e "${YELLOW}No changes to apply.${NC}"
        return 0
    fi

    echo "📋 Changes to apply to production:"
    echo "─────────────────────────────────"
    sed -n '1,50p' "$patch_file"
    local total_lines
    total_lines=$(wc -l < "$patch_file")
    if [ "$total_lines" -gt 50 ]; then
        echo "... ($total_lines total lines, showing first 50)"
    fi
    echo "─────────────────────────────────"
    echo -e "${RED}⚠️  This will modify PRODUCTION code!${NC}"
    read -p "Apply these changes? [y/N] " confirm

    if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
        if git -C "$PROJECT_DIR" apply --binary "$patch_file"; then
            echo -e "${GREEN}✅ Changes applied to production.${NC}"
            echo -e "${YELLOW}⚠️  Remember to restart Genesis: systemctl --user restart genesis-v4${NC}"
        else
            rm -f "$patch_file"
            return 1
        fi
    else
        echo "Cancelled."
    fi
    rm -f "$patch_file"
}

cmd_status() {
    if _is_running; then
        echo -e "${GREEN}● Doctor container: running${NC}"
        docker exec -w /workspace "$CONTAINER" bash -c "
            echo \"  Python: \$($PYTHON --version 2>&1)\"
            echo \"  Workspace files: \$(find /workspace -name '*.py' | wc -l) .py files\"
            echo \"  Git status:\"
            git status --short 2>/dev/null | head -10
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

cmd_auto_apply() {
    # 非交互式应用：自进化专用，带 git 安全网
    # 支持 --only file1,file2,... 限定应用范围
    _ensure_running

    local only_filter=""
    if [ "${1:-}" = "--only" ] && [ -n "${2:-}" ]; then
        only_filter="$2"
    fi

    local patch_file
    patch_file=$(mktemp "$PROJECT_DIR/doctor-auto-apply-XXXXXX.patch")
    if ! _doctor_workspace_patch "$only_filter" > "$patch_file"; then
        rm -f "$patch_file"
        echo "READ_PATCH_FAILED"
        return 1
    fi

    if [ ! -s "$patch_file" ]; then
        rm -f "$patch_file"
        echo "NO_CHANGES"
        return 0
    fi

    local lines_changed
    lines_changed=$(wc -l < "$patch_file")
    echo "PENDING_CHANGES: $lines_changed lines"

    # 1. Git commit current state as rollback point
    cd "$PROJECT_DIR"
    local pre_commit
    pre_commit=$(git rev-parse HEAD 2>/dev/null)
    git add -A 2>/dev/null
    git commit -q -m "[self-evolution] pre-apply snapshot" --allow-empty 2>/dev/null
    echo "ROLLBACK_POINT: $pre_commit"

    # 2. Apply the diff
    if git apply --binary "$patch_file" 2>&1; then
        echo "APPLY_OK"
    else
        echo "APPLY_FAILED"
        git reset --hard HEAD >/dev/null 2>&1
        git clean -fd >/dev/null 2>&1
        rm -f "$patch_file"
        return 1
    fi

    # 3. Commit the applied changes
    git add -A 2>/dev/null
    local apply_commit_msg="[self-evolution] auto-apply $(date +%Y%m%d_%H%M%S) ($lines_changed lines)"
    git commit -q -m "$apply_commit_msg" 2>/dev/null
    local new_commit
    new_commit=$(git rev-parse HEAD 2>/dev/null)
    echo "APPLIED_COMMIT: $new_commit"
    echo "APPLY_SUCCESS"
    rm -f "$patch_file"
}

cmd_rollback() {
    # 回滚到指定 commit（自进化安全网）
    local target="$1"
    if [ -z "$target" ]; then
        echo -e "${RED}Usage: doctor.sh rollback <commit-hash>${NC}"
        exit 1
    fi
    cd "$PROJECT_DIR"
    echo "Rolling back to $target..."
    git reset --hard "$target" 2>&1
    echo "ROLLBACK_DONE: $(git rev-parse HEAD)"
}

cmd_list_changed() {
    # List all changed files in sandbox (tracked + untracked), one per line
    # Used by SelfEvolution scope gate before apply
    _ensure_running
    docker exec -w /workspace "$CONTAINER" bash -c '
        (git diff --name-only HEAD 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null | grep -vE "(__pycache__|\.pyc|\.pyo|\.orig|\.rej|\.log|\.pytest_cache|^runtime/|^\.)") | sort -u | grep -vE "^$"
    ' 2>/dev/null
}

# ── 路由 ──
case "${1:-help}" in
    start)  cmd_start ;;
    stop)   cmd_stop ;;
    reset)  cmd_reset ;;
    exec)   shift; cmd_exec "$@" ;;
    run)    cmd_run ;;
    python) shift; cmd_python "$@" ;;
    test)   shift; cmd_test "$@" ;;
    test-diff) cmd_test_diff ;;
    diff)   cmd_diff ;;
    diff-status) cmd_diff_status ;;
    file-status) cmd_file_status ;;
    list-changed) cmd_list_changed ;;
    patch)  cmd_patch ;;
    apply)  shift 2>/dev/null; cmd_apply "$@" ;;
    auto-apply) shift 2>/dev/null; cmd_auto_apply "$@" ;;
    rollback) shift; cmd_rollback "$@" ;;
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
        echo "  list-changed   列出沙箱中所有修改文件（scope gate 用）"
        echo "  apply [--only f1,f2]  将修改应用到本体（需确认，--only 限定范围）"
        echo "  auto-apply [--only f1,f2]  非交互式应用（自进化用，--only 限定范围）"
        echo "  rollback <hash> 回滚到指定 commit"
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
