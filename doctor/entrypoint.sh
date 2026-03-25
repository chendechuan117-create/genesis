#!/bin/bash
# Genesis Doctor Container - Entrypoint
# 初始化容器环境

echo "=== Genesis Doctor 容器启动 ==="
echo "时间: $(date)"
echo "容器: $HOSTNAME"
echo "Python版本: $(python3 --version 2>/dev/null || echo "未安装")"

# 检查工作空间
if [ -d "/workspace" ]; then
    echo "工作空间: /workspace"
else
    echo "工作空间: 未找到"
fi

# 启动约束感知的价值创造系统（后台模式）
echo "=== 启动约束感知的价值创造系统 ==="
if [ -d "/value_creation_system" ]; then
    cd /value_creation_system
    nohup python3 simple_value_engine.py --continuous --interval 300 > /tmp/value_creation.log 2>&1 &
    echo "价值创造系统已启动，日志：/tmp/value_creation.log"
    echo "后台进程PID: $!"
else
    echo "警告：价值创造系统目录未找到"
fi

# 保持容器运行
echo "=== 容器进入待命状态 ==="
echo "价值创造系统在后台持续运行..."
echo "容器主进程：sleep infinity"
sleep infinity