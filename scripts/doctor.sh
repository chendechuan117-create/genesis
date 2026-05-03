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

DEFAULT_WORKSPACE='/workspace'
FALLBACK_WORKSPACE='/src/genesis'

_doctor_workspace_dir() {
    local preferred="${DOCTOR_WORKSPACE_DIR:-$DEFAULT_WORKSPACE}"
    local fallback="${DOCTOR_FALLBACK_WORKSPACE_DIR:-$FALLBACK_WORKSPACE}"
    local chosen=""

    for candidate in "$preferred" "$fallback"; do
        if [ -n "$candidate" ] && docker exec "$CONTAINER" test -d "$candidate" >/dev/null 2>&1; then
            chosen="$candidate"
            break
        fi
    done

    if [ -z "$chosen" ]; then
        chosen="$fallback"
        echo "Warning: no usable Doctor workspace directory found. Falling back to raw path: $chosen (checked: $preferred $fallback)" >&2
    fi

    printf '%s\n' "$chosen"
}

_doctor_exec() {
    docker exec -w "$(_doctor_workspace_dir)" "$CONTAINER" "$@"
}

_doctor_exec_i() {
    docker exec -i -w "$(_doctor_workspace_dir)" "$CONTAINER" "$@"
}

_doctor_exec_it() {
    docker exec -it -w "$(_doctor_workspace_dir)" "$CONTAINER" "$@"
}

_doctor_pythonpath() {
    _doctor_workspace_dir
}

_ensure_git_safe() {
    local workspace
    workspace="$(_doctor_workspace_dir)" || return 1
    # Git 2.35.2+ refuses operations when repo owner != process uid.
    docker exec "$CONTAINER" git config --global --add safe.directory "$workspace" 2>/dev/null || true
    # Git identity required for commits; lost on container restart.
    docker exec "$CONTAINER" git config --global user.email "doctor@genesis.local" 2>/dev/null || true
    docker exec "$CONTAINER" git config --global user.name "Genesis Doctor" 2>/dev/null || true
}

_inside_doctor_container() {
    [ -f /.dockerenv ] && [ -d /workspace ] && [ -x "$PYTHON" ]
}

_ensure_running() {
    if _inside_doctor_container; then
        _ensure_git_safe || return 1
        return 0
    fi
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
        docker exec -w "$(_doctor_workspace_dir)" "$CONTAINER" bash -c '
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
    _doctor_exec "$@"
}

# run: 从 stdin 读取脚本，写入容器后执行。
# 绕过宿主 shell → doctor.sh → 容器 bash 的三层变量展开问题。
# 用法: doctor.sh run <<'SCRIPT'
#          echo ${1:-default}   # 在容器内展开，不在宿主展开
#        SCRIPT
cmd_run() {
    _ensure_running
    local timeout_secs="${DOCTOR_RUN_TIMEOUT_SECS:-600}"
    local kill_after_secs="${DOCTOR_RUN_KILL_AFTER_SECS:-10}"
    local job_id="doctor_run_$(date +%Y%m%d_%H%M%S)_$$"
    docker exec -i -w "$(_doctor_workspace_dir)" -e PYTHONPATH="$(_doctor_pythonpath)" \
        -e DOCTOR_RUN_TIMEOUT_SECS="$timeout_secs" \
        -e DOCTOR_RUN_KILL_AFTER_SECS="$kill_after_secs" \
        -e DOCTOR_RUN_JOB_ID="$job_id" \
        "$CONTAINER" bash -c '
set -u
job_id="${DOCTOR_RUN_JOB_ID:-doctor_run_unknown}"
timeout_secs="${DOCTOR_RUN_TIMEOUT_SECS:-600}"
kill_after_secs="${DOCTOR_RUN_KILL_AFTER_SECS:-10}"
case "$timeout_secs" in ""|*[!0-9]*) timeout_secs=600 ;; esac
case "$kill_after_secs" in ""|*[!0-9]*) kill_after_secs=10 ;; esac
[ "$timeout_secs" -gt 0 ] || timeout_secs=600
[ "$kill_after_secs" -gt 0 ] || kill_after_secs=10
script_path="/tmp/${job_id}.sh"
child=""
cat > "$script_path"
chmod +x "$script_path"
terminate_group() {
    if [ -n "${child:-}" ]; then
        kill -TERM -- "-$child" 2>/dev/null || kill -TERM "$child" 2>/dev/null || true
        sleep "$kill_after_secs"
        kill -KILL -- "-$child" 2>/dev/null || kill -KILL "$child" 2>/dev/null || true
    fi
}
cleanup() {
    rm -f "$script_path"
}
trap "terminate_group; cleanup; exit 143" INT TERM HUP
trap "cleanup" EXIT
setsid bash "$script_path" &
child=$!
deadline=$((SECONDS + timeout_secs))
while kill -0 "$child" 2>/dev/null; do
    if [ "$SECONDS" -ge "$deadline" ]; then
        echo "[doctor-run] timeout after ${timeout_secs}s; terminating job ${job_id}" >&2
        terminate_group
        wait "$child" 2>/dev/null || true
        exit 124
    fi
    sleep 1
done
wait "$child"
code=$?
if kill -TERM -- "-$child" 2>/dev/null; then
    sleep "$kill_after_secs"
    kill -KILL -- "-$child" 2>/dev/null || true
fi
exit "$code"
'
}

cmd_python() {
    _ensure_running
    if [ $# -eq 0 ]; then
        _doctor_exec_it "$PYTHON"
    else
        _doctor_exec "$PYTHON" -c "$*"
    fi
}

cmd_test() {
    _ensure_running
    local target="${1:-tests/}"
    echo "🧪 Running tests: $target"
    docker exec -w "$(_doctor_workspace_dir)" -e PYTHONPATH="$(_doctor_pythonpath)" "$CONTAINER" \
        "$PYTHON" -m pytest "$target" -v --tb=short 2>&1
}

# Test only files related to sandbox diff (used by SelfEvolution auto-apply)
# Finds test files that correspond to changed/new files in the sandbox
cmd_test_diff() {
    _ensure_running
    local test_files=()

    # Preflight: surface likely .gitignore gate early instead of silently passing.
    # Check both tracked test files already shadowed by ignore rules and untracked
    # test-like paths that ignore rules would hide from git ls-files --others.
    local preflight_output
    preflight_output=$(bash <<'EOF'
set -e
pattern='(^|/)test_.*\.py$|(^|/).*_test.*\.py$'
tracked_tests=$(git ls-files 'tests/*.py' 2>/dev/null | grep -E "$pattern" || true)
ignored_tracked_tests=$(printf '%s\n' "$tracked_tests" | while IFS= read -r f; do
    [ -n "$f" ] || continue
    git check-ignore -v "$f" 2>/dev/null | sed "s#^#tracked:$f :: #"
done)

untracked_shadowed_tests=$(find . -path './.git' -prune -o -path './archive' -prune -o -path './runtime' -prune -o -path './.tmp_probe' -prune -o -type f \( -name 'test_*.py' -o -name '*_test*.py' \) -print 2>/dev/null | sed 's#^./##' | while IFS= read -r f; do
    git ls-files --error-unmatch "$f" >/dev/null 2>&1 && continue
    git check-ignore -v "$f" 2>/dev/null | sed "s#^#untracked:$f :: #"
done)

if [ -n "$ignored_tracked_tests$untracked_shadowed_tests" ]; then
    echo 'DOCTOR_TEST_DIFF_PREFLIGHT:.gitignore gate detected'
    echo 'Test-like files are hidden or shadowed by ignore rules, so baseline/add and diff discovery can drift:'
    [ -n "$ignored_tracked_tests" ] && echo "$ignored_tracked_tests"
    [ -n "$untracked_shadowed_tests" ] && echo "$untracked_shadowed_tests"
fi
EOF
)
    if [ -n "$preflight_output" ]; then
        echo "$preflight_output"
    fi

    # Only consider git-tracked files for test discovery.
    # Untracked files (Yogg's self-created probes/tests in sandbox root)
    # are practice artifacts — they must NOT gate the apply decision.
    local tracked_changed
    tracked_changed=$(git diff --name-only HEAD 2>/dev/null | grep -vE '^(archive/|blog/|docs/|\.tmp_probe/|n8n-workflows/|scripts/replica_setup/)')
    local untracked_changed
    untracked_changed=$(git ls-files --others --exclude-standard 2>/dev/null | grep -vE "(__pycache__|\.pyc|\.pyo|\.pytest_cache|^runtime/|^\.)" | while IFS= read -r f; do [ -f "$f" ] && echo "$f"; done)

    # Test discovery: only from tracked changes (production source files)
    while IFS= read -r f; do
        [ -z "$f" ] && continue
        # Only discover tests under tests/ directory — skip root-level test_*.py (sandbox artifacts)
        if [[ "$f" == tests/test_*.py ]]; then
            test_files+=("$f")
            continue
        fi
        local base
        base=$(basename "$f" _impl.py 2>/dev/null || basename "$f" .py 2>/dev/null)
        local t
        for t in "tests/test_${base}.py" "tests/${base}.py"; do
            if [ -f "$t" ]; then
                test_files+=("$t")
                break
            fi
        done
    done <<< "$tracked_changed"

    local unique_tests
    unique_tests=$(printf '%s\n' "${test_files[@]}" 2>/dev/null | sort -u | grep -vE '^$|__pycache__|\.pyc' | grep '\.py$')

    if [ -z "$unique_tests" ]; then
        if [ -n "$preflight_output" ]; then
            echo "❌ test-diff preflight blocked: likely .gitignore-constrained tests are invisible to diff discovery"
            return 2
        fi
        echo "NO_TESTS_FOUND: no test files found for diff changes"
        echo "⚠️  No evidence ≠ positive evidence — SelfEvolution should treat this as unverified, not as passing"
        return 3
    fi

    echo "🧪 Running diff-scoped tests:"
    echo "$unique_tests" | while IFS= read -r t; do echo "  $t"; done

    local test_args
    test_args=$(echo "$unique_tests" | tr '\n' ' ')
    local collect_output
    local collect_rc
    collect_output=$("$PYTHON" -m pytest $test_args --collect-only -q 2>&1)
    collect_rc=$?
    if [ $collect_rc -ne 0 ]; then
        echo "COLLECTION_FAILED: pytest collection failed for discovered tests"
        echo "$collect_output" | tail -5
        return 4
    fi

    "$PYTHON" -m pytest $test_args -v --tb=short 2>&1
}
_doctor_workspace_patch() {
    # Optional: $1 = comma-separated file glob filter (--only)
    local only_filter="${1:-}"
    _ensure_running
    docker exec -i -w "$(_doctor_workspace_dir)" "$CONTAINER" bash <<EOF
set -euo pipefail

if [ -n "$only_filter" ]; then
    # Scoped: only emit diff for matching files
    # --only uses comma-separated paths; git diff needs space-separated args
    _only_args=\$(echo "$only_filter" | tr ',' ' ')
    git diff HEAD -- \$_only_args
    # Build grep pattern from individual paths: ^path1$|^path2$|^path3$
    _only_pattern=\$(echo "$only_filter" | sed 's/,/\$|^/g' | sed 's/^/^/' | sed 's/$/\$/')
    for _path in \$(git ls-files --others --exclude-standard -z 2>/dev/null | tr '\0' '\n' | grep -E "\$_only_pattern" || true); do
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
    docker exec -i -w "$(_doctor_workspace_dir)" "$CONTAINER" bash <<'EOF'
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
    docker exec -i -w "$(_doctor_workspace_dir)" "$CONTAINER" bash <<'EOF'
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

cmd_sync_state_preflight() {
    _ensure_running

    local head_commit
    head_commit=$(docker exec -w /workspace "$CONTAINER" git rev-parse HEAD 2>/dev/null || true)
    local head_snapshot_tag
    head_snapshot_tag=$(docker exec -w /workspace "$CONTAINER" bash -lc 'git tag --points-at HEAD 2>/dev/null | grep "^snapshot/" | head -n 1 || true' 2>/dev/null || true)
    local tracked_diff
    tracked_diff=$(docker exec -w /workspace "$CONTAINER" git diff HEAD 2>/dev/null || true)

    local tracked_hash=""
    local tracked_lines=0
    if [ -n "$tracked_diff" ]; then
        tracked_hash=$(printf "%s" "$tracked_diff" | md5sum | cut -d" " -f1 | cut -c1-12)
        tracked_lines=$(printf "%s" "$tracked_diff" | wc -l | tr -d " ")
    fi

    local untracked_list
    untracked_list=$(docker exec -w /workspace "$CONTAINER" bash -lc "git ls-files --others --exclude-standard 2>/dev/null | grep -vE '(__pycache__|\.pyc|\.pyo|\.orig|\.rej|\.log|\.pytest_cache|^runtime/|^\.)' || true" 2>/dev/null || true)
    local untracked_hash=""
    local untracked_count=0
    if [ -n "$untracked_list" ]; then
        untracked_hash=$(printf "%s
" "$untracked_list" | sort | md5sum | cut -d" " -f1 | cut -c1-12)
        untracked_count=$(printf "%s
" "$untracked_list" | wc -l | tr -d " ")
    fi

    local snapshot_count
    snapshot_count=$(docker exec -w /workspace "$CONTAINER" bash -lc 'git tag -l "snapshot/*" 2>/dev/null | wc -l | tr -d " "' 2>/dev/null || true)
    local initialized=0
    if docker exec "$CONTAINER" test -f /workspace/.doctor-initialized 2>/dev/null; then
        initialized=1
    fi

    local host_head
    host_head=$(cat "$PROJECT_DIR/.doctor/.host_head" 2>/dev/null || true)
    local host_sync_required=0
    local host_sync_reason=""
    if [ -n "$host_head" ] && [ -n "$head_commit" ] && [ "$host_head" != "$head_commit" ]; then
        host_sync_required=1
        host_sync_reason="host_head_mismatch"
    fi

    printf "HEAD_COMMIT:%s
" "$head_commit"
    printf "HEAD_SNAPSHOT_TAG:%s
" "$head_snapshot_tag"
    printf "SNAPSHOT_COUNT:%s
" "$snapshot_count"
    printf "INITIALIZED:%s
" "$initialized"
    printf "HOST_HEAD:%s
" "$host_head"
    printf "HOST_SYNC_REQUIRED:%s
" "$host_sync_required"
    printf "HOST_SYNC_REASON:%s
" "$host_sync_reason"
    printf "TRACKED_HASH:%s
" "$tracked_hash"
    printf "TRACKED_LINES:%s
" "$tracked_lines"
    printf "UNTRACKED_HASH:%s
" "$untracked_hash"
    printf "UNTRACKED_COUNT:%s
" "$untracked_count"
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
        docker exec -w "$(_doctor_workspace_dir)" "$CONTAINER" bash -c "
            echo \"  Python: \$($PYTHON --version 2>&1)\"
            echo \"  Workspace files: \$(find $(_doctor_workspace_dir) -name '*.py' | wc -l) .py files\"
            echo \"  Git status:\"
            git status --short 2>/dev/null | head -10
        "
    else
        echo -e "${RED}● Doctor container: stopped${NC}"
    fi
}

cmd_cat() {
    _ensure_running
    _doctor_exec cat "$@"
}

cmd_snapshots() {
    _ensure_running
    echo "📸 Doctor workspace snapshots:"
    docker exec -w "$(_doctor_workspace_dir)" "$CONTAINER" bash -c '
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

    # 1. Git commit current state as rollback point + named tag
    cd "$PROJECT_DIR"
    local pre_commit
    pre_commit=$(git rev-parse HEAD 2>/dev/null)
    git add -A 2>/dev/null
    git commit -q -m "[self-evolution] pre-apply snapshot" --allow-empty 2>/dev/null
    local rollback_tag="rollback/$(date +%Y%m%d_%H%M%S)"
    git tag "$rollback_tag" HEAD 2>/dev/null
    echo "ROLLBACK_POINT: $pre_commit"
    echo "ROLLBACK_TAG: $rollback_tag"

    # 2. Dry-run check: verify patch applies cleanly before modifying working tree
    if ! git apply --check --binary "$patch_file" 2>&1; then
        echo "APPLY_CHECK_FAILED: patch would not apply cleanly (dry-run)"
        rm -f "$patch_file"
        return 1
    fi

    # 3. Apply the diff (guaranteed clean after --check)
    if git apply --binary "$patch_file" 2>&1; then
        echo "APPLY_OK"
    else
        echo "APPLY_FAILED: unexpected failure after successful --check (should not happen)"
        git reset --hard "$rollback_tag" >/dev/null 2>&1
        git clean -fd >/dev/null 2>&1
        rm -f "$patch_file"
        return 1
    fi

    # 4. Smoke test canary: verify core modules still import after apply
    #     This catches syntax errors and broken imports BEFORE restart.
    #     If this fails, rollback to the tag — the running process is still safe.
    local smoke_output
    smoke_output=$("$PYTHON" -c "
from genesis.auto_mode import SelfEvolution
from genesis.v4.loop import V4Loop
from genesis.v4.manager import NodeVault
from genesis.tools.node_tools import RecordPointTool, RecordLineTool
from genesis.tools.search_tool import SearchKnowledgeNodesTool
print('SMOKE_OK')
" 2>&1)
    if echo "$smoke_output" | grep -q "SMOKE_OK"; then
        echo "SMOKE_TEST: PASS"
    else
        echo "SMOKE_TEST: FAIL"
        echo "$smoke_output" | tail -10
        echo "SMOKE_FAILED: core import broken after apply, rolling back"
        git reset --hard "$rollback_tag" >/dev/null 2>&1
        git clean -fd >/dev/null 2>&1
        rm -f "$patch_file"
        return 5
    fi

    # 5. Commit the applied changes
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
    docker exec -w "$(_doctor_workspace_dir)" "$CONTAINER" bash -c '
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
    sync-state-preflight) cmd_sync_state_preflight ;;
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
        echo "  sync-state-preflight  显式校验首次快照/后续增量同步状态"
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
