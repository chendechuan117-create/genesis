#!/usr/bin/env bash
set -o pipefail

host="${YOGG_HOST:-yoga}"
seconds="${YOGG_TIMEOUT:-12}"
limit="${YOGG_MAX_LINES:-160}"

usage() {
    echo "Usage: $0 [--host HOST] [--timeout SECONDS] [--lines N] '<remote command>'" >&2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --host)
            host="${2:-}"
            shift 2
            ;;
        --timeout)
            seconds="${2:-}"
            shift 2
            ;;
        --lines)
            limit="${2:-}"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        --)
            shift
            break
            ;;
        *)
            break
            ;;
    esac
done

if [[ $# -eq 0 || -z "$host" || -z "$seconds" || -z "$limit" ]]; then
    usage
    exit 64
fi

remote_cmd="$*"
out_file="$(mktemp)"
trap 'rm -f "$out_file"' EXIT

timeout --foreground "${seconds}s" ssh -T \
    -o BatchMode=yes \
    -o ConnectTimeout=5 \
    -o ServerAliveInterval=5 \
    -o ServerAliveCountMax=1 \
    -o LogLevel=ERROR \
    "$host" "$remote_cmd" >"$out_file" 2>&1
status=$?

line_count="$(wc -l <"$out_file" | tr -d ' ')"
if [[ "$line_count" -gt "$limit" ]]; then
    tail -n "$limit" "$out_file"
    echo "[yogg_safe_ssh] output truncated: ${line_count} lines, showing last ${limit}" >&2
else
    cat "$out_file"
fi

if [[ "$status" -eq 124 ]]; then
    echo "[yogg_safe_ssh] timeout after ${seconds}s: ${host}: ${remote_cmd}" >&2
fi

exit "$status"
