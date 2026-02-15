import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

from typing import Dict, Any
import json

class ProfitStrategyTest:
    """测试赚钱策略生成器"""
    
    name = "profit_strategy_test"
    description = "测试profit_strategy_generator工具"
    
    parameters = {
        "type": "object",
        "properties": {},
        "required": []
    }
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        """执行测试"""
        try:
            # 模拟用户输入
            test_data = {
                "user_skills": ["编程", "写作", "数据分析"],
                "available_resources": ["电脑", "网络", "时间"],
                "time_commitment": "flexible",
                "income_target": "extra_income",
                "risk_tolerance": "medium"
            }
            
            # 尝试导入并运行profit_strategy_generator
            import sys
            from pathlib import Path
            sys.path.insert(0, str(Path(__file__).parent.parent))
            
            try:
                from skills.profit_strategy_generator import ProfitStrategyGenerator
                generator = ProfitStrategyGenerator()
                result = generator.execute(**test_data)
                
                return {
                    "success": True,
                    "tool_loaded": True,
                    "test_result": result,
                    "message": "赚钱策略生成器测试成功"
                }
            except ImportError as e:
                return {
                    "success": False,
                    "tool_loaded": False,
                    "error": f"导入失败: {str(e)}",
                    "message": "请检查profit_strategy_generator.py文件"
                }
            except Exception as e:
                return {
                    "success": False,
                    "tool_loaded": True,
                    "error": f"执行失败: {str(e)}",
                    "message": "工具加载但执行出错"
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "测试过程出错"
            }