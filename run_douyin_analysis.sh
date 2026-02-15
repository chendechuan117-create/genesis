#!/bin/bash
# 抖音数据分析系统启动脚本

echo "🎯 启动抖音变现潜力分析系统"
echo "========================================"

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到Python3，请先安装Python3"
    exit 1
fi

# 检查依赖
echo "📦 检查Python依赖..."
REQUIRED_PACKAGES=("aiohttp" "pyyaml")

for pkg in "${REQUIRED_PACKAGES[@]}"; do
    if ! python3 -c "import $pkg" 2>/dev/null; then
        echo "  安装 $pkg..."
        pip3 install $pkg
    else
        echo "  ✓ $pkg 已安装"
    fi
done

# 创建输出目录
mkdir -p analysis_reports

# 运行分析系统
echo ""
echo "🚀 开始分析抖音账号变现潜力..."
echo ""

# 运行主程序
python3 douyin_analyzer.py

# 检查结果
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 分析完成！"
    echo ""
    
    # 查找最新报告
    LATEST_REPORT=$(ls -t analysis_reports/douyin_analysis_*.json 2>/dev/null | head -1)
    if [ -n "$LATEST_REPORT" ]; then
        echo "📄 最新报告: $LATEST_REPORT"
        echo ""
        echo "📊 报告摘要:"
        python3 -c "
import json
try:
    with open('$LATEST_REPORT', 'r', encoding='utf-8') as f:
        data = json.load(f)
    summary = data['action_plan']['account_summary']
    print(f'   粉丝数: {summary[\"followers\"]:,}')
    print(f'   互动率: {summary[\"engagement_rate\"]}%')
    print(f'   内容类型: {summary[\"content_type\"]}')
    
    total_potential = data['action_plan']['total_potential_revenue']
    print(f'   总变现潜力: ¥{total_potential:,.2f}')
    
    best_op = data['action_plan']['recommended_opportunities'][0]
    print(f'   最佳机会: {best_op[\"type\"]}')
    print(f'   预计收入: ¥{best_op[\"estimated_revenue\"]:,.2f}')
    
except Exception as e:
    print(f'   读取报告时出错: {e}')
"
    fi
    
    echo ""
    echo "💡 下一步行动建议:"
    echo "   1. 查看完整报告了解详细行动计划"
    echo "   2. 选择1-2个变现方向开始执行"
    echo "   3. 每周复盘调整策略"
    echo "   4. 考虑批量分析多个账号"
    
    echo ""
    echo "💰 商业化机会:"
    echo "   • 单个账号分析服务: ¥99-¥299"
    echo "   • 批量分析套餐: ¥888/10个账号"
    echo "   • 月度监控服务: ¥399/月"
    echo "   • 定制化方案: ¥1,500起"
    
else
    echo "❌ 分析过程中出现错误"
    exit 1
fi

echo ""
echo "========================================"
echo "🎯 系统准备就绪，可以开始赚钱了！"
echo ""