#!/bin/bash
# Genesis Autopilot — 自动驾驶控制面板
# 用法:
#   autopilot.sh start [--interval 30] [--category explore]  # 启动
#   autopilot.sh stop                                         # 停止
#   autopilot.sh status                                       # 状态
#   autopilot.sh log [N]                                      # 查看日志（最后 N 行）
#   autopilot.sh results                                      # 查看任务结果
#   autopilot.sh list                                         # 列出所有任务

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PIDFILE="$PROJECT_DIR/runtime/autopilot.pid"
LOGFILE="$PROJECT_DIR/runtime/autopilot.log"
RESULTS="$PROJECT_DIR/runtime/autopilot_results.json"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

_is_running() {
    if [ -f "$PIDFILE" ]; then
        local pid=$(cat "$PIDFILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
            return 0
        fi
        rm -f "$PIDFILE"
    fi
    return 1
}

case "${1:-help}" in

start)
    if pid=$(_is_running); then
        echo -e "${YELLOW}⚠️  Autopilot 已在运行 (PID $pid)${NC}"
        exit 1
    fi
    shift
    echo -e "${GREEN}🚀 启动 Autopilot...${NC}"
    cd "$PROJECT_DIR"
    # 激活虚拟环境（如果存在）
    if [ -f "$PROJECT_DIR/venv/bin/activate" ]; then
        source "$PROJECT_DIR/venv/bin/activate"
    fi
    nohup python3 scripts/autopilot.py "$@" >> "$LOGFILE" 2>&1 &
    local_pid=$!
    echo "$local_pid" > "$PIDFILE"
    sleep 2
    if kill -0 "$local_pid" 2>/dev/null; then
        echo -e "${GREEN}✅ Autopilot 已启动 (PID $local_pid)${NC}"
        echo -e "   日志: ${CYAN}tail -f $LOGFILE${NC}"
        echo -e "   停止: ${CYAN}$0 stop${NC}"
    else
        echo -e "${RED}❌ 启动失败，查看日志:${NC}"
        tail -20 "$LOGFILE"
        rm -f "$PIDFILE"
        exit 1
    fi
    ;;

stop)
    if pid=$(_is_running); then
        echo -e "${YELLOW}🛑 停止 Autopilot (PID $pid)...${NC}"
        kill "$pid"
        # 等待优雅退出（最多 30 秒）
        for i in $(seq 1 30); do
            if ! kill -0 "$pid" 2>/dev/null; then
                echo -e "${GREEN}✅ Autopilot 已停止${NC}"
                rm -f "$PIDFILE"
                exit 0
            fi
            sleep 1
        done
        echo -e "${RED}⚠️  强制终止...${NC}"
        kill -9 "$pid" 2>/dev/null || true
        rm -f "$PIDFILE"
        echo -e "${GREEN}✅ 已强制终止${NC}"
    else
        echo -e "${YELLOW}ℹ️  Autopilot 未在运行${NC}"
    fi
    ;;

status)
    if pid=$(_is_running); then
        echo -e "${GREEN}● Autopilot: running (PID $pid)${NC}"
        # 显示运行时间
        if [ -f "/proc/$pid/stat" ]; then
            start_time=$(stat -c %Y "/proc/$pid")
            now=$(date +%s)
            elapsed=$(( (now - start_time) / 60 ))
            echo -e "  运行时间: ${elapsed} 分钟"
        fi
        # 显示最后一条任务日志
        if [ -f "$LOGFILE" ]; then
            echo -e "  最近任务:"
            grep -E '(✅|❌|⏰|📊)' "$LOGFILE" | tail -3 | sed 's/^/    /'
        fi
        # 显示结果摘要
        if [ -f "$RESULTS" ]; then
            echo -e "  结果摘要:"
            python3 -c "
import json
d = json.load(open('$RESULTS'))
print(f\"    {d.get('summary', 'N/A')}\")
tasks = d.get('tasks', [])
if tasks:
    ok = sum(1 for t in tasks if t['success'])
    fail = len(tasks) - ok
    print(f'    最近任务: {tasks[-1][\"label\"]} ({\"✅\" if tasks[-1][\"success\"] else \"❌\"})')
" 2>/dev/null || true
        fi
    else
        echo -e "${RED}● Autopilot: stopped${NC}"
        if [ -f "$RESULTS" ]; then
            echo -e "  上次结果:"
            python3 -c "
import json
d = json.load(open('$RESULTS'))
print(f\"    {d.get('summary', 'N/A')}\")
" 2>/dev/null || true
        fi
    fi
    ;;

log)
    lines=${2:-50}
    if [ -f "$LOGFILE" ]; then
        tail -n "$lines" "$LOGFILE"
    else
        echo "日志文件不存在"
    fi
    ;;

follow|tail)
    if [ -f "$LOGFILE" ]; then
        tail -f "$LOGFILE"
    else
        echo "日志文件不存在"
    fi
    ;;

results)
    if [ -f "$RESULTS" ]; then
        python3 -c "
import json
d = json.load(open('$RESULTS'))
print(d.get('summary', ''))
print()
for t in d.get('tasks', []):
    emoji = '✅' if t['success'] else '❌'
    print(f\"{emoji} {t['label']:30s} {t['duration_secs']:6.1f}s  {t['iterations']:3d} iters  {t['response_preview'][:60]}\")
" 2>/dev/null
    else
        echo "还没有结果（Autopilot 未运行过）"
    fi
    ;;

list)
    cd "$PROJECT_DIR"
    python3 scripts/autopilot.py --list
    ;;

help|*)
    echo "Genesis Autopilot 控制面板"
    echo ""
    echo "用法:"
    echo -e "  ${CYAN}$0 start${NC} [--interval 30] [--category NAME] [--max-tasks N]"
    echo -e "  ${CYAN}$0 stop${NC}"
    echo -e "  ${CYAN}$0 status${NC}"
    echo -e "  ${CYAN}$0 log${NC} [行数]"
    echo -e "  ${CYAN}$0 follow${NC}              # tail -f 日志"
    echo -e "  ${CYAN}$0 results${NC}             # 任务结果"
    echo -e "  ${CYAN}$0 list${NC}                # 列出所有任务"
    echo ""
    echo "任务类别: explore, doctor, maintain, challenge, deep, quick"
    echo ""
    echo "示例:"
    echo "  $0 start                          # 全类别，30s 间隔"
    echo "  $0 start --interval 10            # 10s 间隔（高压模式）"
    echo "  $0 start --category deep          # 只跑深度思考"
    echo "  $0 start --max-tasks 20           # 跑 20 个就停"
    ;;

esac
