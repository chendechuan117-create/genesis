#!/usr/bin/env python3
"""测试赚钱策略生成器"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent / "nanogenesis"
sys.path.insert(0, str(project_root))

try:
    # 尝试导入工具
    from skills.profit_strategy_generator import ProfitStrategyGenerator
    
    print("✅ 成功导入 ProfitStrategyGenerator")
    
    # 创建实例
    generator = ProfitStrategyGenerator()
    print("✅ 成功创建工具实例")
    
    # 测试数据
    test_data = {
        "user_skills": ["编程", "写作", "数据分析"],
        "available_resources": ["电脑", "网络", "时间"],
        "time_commitment": "flexible",
        "income_target": "extra_income",
        "risk_tolerance": "medium"
    }
    
    print("\n📊 测试数据:")
    print(f"技能: {test_data['user_skills']}")
    print(f"资源: {test_data['available_resources']}")
    print(f"时间投入: {test_data['time_commitment']}")
    print(f"收入目标: {test_data['income_target']}")
    print(f"风险承受: {test_data['risk_tolerance']}")
    
    # 执行测试
    print("\n🚀 执行策略生成...")
    result = generator.execute(**test_data)
    
    print("\n📈 生成结果:")
    print(f"成功: {result.get('success', False)}")
    print(f"消息: {result.get('message', '无消息')}")
    
    if result.get('success'):
        strategies = result.get('result', {}).get('matched_strategies', [])
        print(f"\n🎯 找到 {len(strategies)} 个匹配策略:")
        
        for i, strategy in enumerate(strategies[:3], 1):
            print(f"\n{i}. {strategy.get('name', '未命名')}")
            print(f"   描述: {strategy.get('description', '无描述')}")
            print(f"   收入潜力: {strategy.get('income_potential', '未知')}")
            print(f"   时间: {strategy.get('time_to_income', '未知')}")
            print(f"   风险: {strategy.get('risk_level', '未知')}")
            print(f"   匹配技能: {strategy.get('matched_skill', '未知')}")
            
            # 显示前2个行动步骤
            steps = strategy.get('action_steps', [])
            if steps:
                print(f"   行动步骤:")
                for step in steps[:2]:
                    print(f"     - {step}")
    
    else:
        print(f"❌ 错误: {result.get('error', '未知错误')}")
        
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    print("\n🔍 检查文件结构...")
    
    # 检查文件是否存在
    tool_file = project_root / "skills" / "profit_strategy_generator.py"
    if tool_file.exists():
        print(f"✅ 工具文件存在: {tool_file}")
        # 显示文件内容前几行
        with open(tool_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()[:10]
            print("\n📄 文件前10行:")
            for i, line in enumerate(lines, 1):
                print(f"{i:2}: {line.rstrip()}")
    else:
        print(f"❌ 工具文件不存在: {tool_file}")
        
except Exception as e:
    print(f"❌ 测试过程中出错: {e}")
    import traceback
    traceback.print_exc()