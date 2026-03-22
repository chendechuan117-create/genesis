#!/bin/bash

# Genesis博客自动化发布脚本
# 用于触发n8n工作流发布博客文章

set -e

# 配置参数
N8N_URL="http://localhost:5679"
WEBHOOK_PATH="blog-publish"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查参数
if [ $# -lt 1 ]; then
    echo "用法: $0 <博客文件路径>"
    echo "示例: $0 /home/chendechusn/Genesis/Genesis/blog/my-post.md"
    exit 1
fi

BLOG_FILE="$1"

# 检查文件是否存在
if [ ! -f "$BLOG_FILE" ]; then
    log_error "博客文件不存在: $BLOG_FILE"
    exit 1
fi

# 检查文件是否为Markdown文件
if [[ "$BLOG_FILE" != *.md ]] && [[ "$BLOG_FILE" != *.markdown ]]; then
    log_warn "文件扩展名不是.md或.markdown，继续处理..."
fi

# 检查n8n服务是否运行
log_info "检查n8n服务状态..."
if ! curl -s "$N8N_URL/rest/health" > /dev/null 2>&1; then
    log_error "n8n服务未运行，请确保n8n容器正在运行"
    log_info "尝试启动n8n容器..."
    if docker start n8n-chinese > /dev/null 2>&1; then
        log_info "等待n8n服务启动..."
        sleep 5
    else
        log_error "无法启动n8n容器"
        exit 1
    fi
fi

log_info "n8n服务正常运行"

# 读取文件内容
log_info "读取博客文件: $BLOG_FILE"
FILE_CONTENT=$(cat "$BLOG_FILE" | jq -R -s .)
if [ $? -ne 0 ]; then
    log_error "读取文件失败或jq命令未安装"
    log_info "尝试使用简单方式读取..."
    FILE_CONTENT=$(cat "$BLOG_FILE")
    # 转义JSON特殊字符
    FILE_CONTENT=$(echo "$FILE_CONTENT" | sed 's/\\/\\\\/g' | sed 's/"/\\"/g' | sed ':a;N;$!ba;s/\\n/\\\\n/g')
    FILE_CONTENT="\"$FILE_CONTENT\""
fi

# 准备请求数据
REQUEST_DATA=$(cat <<EOF
{
    "filePath": "$BLOG_FILE",
    "fileContent": $FILE_CONTENT
}
EOF
)

log_info "触发n8n工作流..."
RESPONSE=$(curl -s -X POST \
    "$N8N_URL/webhook/$WEBHOOK_PATH" \
    -H "Content-Type: application/json" \
    -d "$REQUEST_DATA")

# 检查响应
if [ $? -eq 0 ]; then
    log_info "工作流触发成功"
    echo "响应: $RESPONSE"
    
    # 尝试解析JSON响应
    if command -v jq > /dev/null 2>&1; then
        echo "格式化响应:"
        echo "$RESPONSE" | jq .
    fi
    
    # 记录发布日志
    LOG_FILE="$PROJECT_ROOT/logs/blog-publish-$(date +%Y%m%d-%H%M%S).log"
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "=== 博客发布日志 ===" > "$LOG_FILE"
    echo "时间: $(date)" >> "$LOG_FILE"
    echo "文件: $BLOG_FILE" >> "$LOG_FILE"
    echo "响应: $RESPONSE" >> "$LOG_FILE"
    echo "请求数据: $REQUEST_DATA" >> "$LOG_FILE"
    
    log_info "发布日志已保存到: $LOG_FILE"
else
    log_error "工作流触发失败"
    exit 1
fi

log_info "博客发布流程完成"
echo ""
echo "下一步："
echo "1. 检查n8n工作流执行状态"
echo "2. 查看各平台发布结果"
echo "3. 如有问题，查看日志文件: $LOG_FILE"