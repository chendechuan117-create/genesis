#!/bin/bash
# 增强版entrypoint补丁 - 添加表达多样性功能

# 在原有entrypoint的基础上添加以下内容：

# 在显示理解状态后，添加多样性表达
echo "=== 容器初始化完成，理解状态 ==="
python3 /doctor/understanding_display.py

# 新增：展示表达多样性
echo ""
echo "=== 表达多样性演示 ==="
if [ -f "/doctor/expression_diversity_demo.py" ]; then
    echo "🎭 容器具备多种表达风格："
    python3 /doctor/expression_diversity_demo.py --quick
else
    echo "📝 基础表达模式已启用"
fi

# 新增：设置表达模式环境变量
export CONTAINER_EXPRESSION_MODE="enhanced"
export CONTAINER_PERSONALITY="adaptive"

# 新增：创建表达控制接口
cat > /tmp/expression_control.sh << 'EOF'
#!/bin/bash
# 容器表达控制接口

case "$1" in
    "technical")
        python3 /doctor/expression_diversity_demo.py --style technical
        ;;
    "casual")
        python3 /doctor/expression_diversity_demo.py --style casual
        ;;
    "poetic")
        python3 /doctor/expression_diversity_demo.py --style poetic
        ;;
    "status")
        python3 /doctor/understanding_display.py
        ;;
    "demo")
        python3 /doctor/expression_diversity_demo.py
        ;;
    *)
        echo "可用命令:"
        echo "  technical - 技术报告风格"
        echo "  casual    - 休闲对话风格"
        echo "  poetic    - 诗意表达风格"
        echo "  status    - 基础状态报告"
        echo "  demo      - 完整多样性演示"
        ;;
esac
EOF

chmod +x /tmp/expression_control.sh
echo "💬 表达控制接口已创建: /tmp/expression_control.sh"
echo "   使用: docker exec genesis-doctor /tmp/expression_control.sh <mode>"

# 保持容器运行
exec sleep infinity
