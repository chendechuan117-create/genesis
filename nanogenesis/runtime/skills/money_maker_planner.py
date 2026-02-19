import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

class MoneyMakerPlanner:
    """赚钱计划生成器 - 基于用户输入创建可执行的赚钱方案"""
    
    def __init__(self):
        self.name = "money_maker_planner"
        self.description = "根据用户技能生成赚钱计划"
        self.parameters = {
            "type": "object",
            "properties": {
                "user_skills": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "用户技能列表"
                },
                "available_hours": {
                    "type": "number",
                    "description": "每周可用小时数",
                    "default": 10
                }
            },
            "required": ["user_skills"]
        }
    
    def execute(self, params):
        skills = params.get("user_skills", [])
        hours = params.get("available_hours", 10)
        
        # 生成计划
        plan = self.generate_plan(skills, hours)
        
        return {
            "success": True,
            "plan": plan,
            "action_items": self.get_action_items(skills)
        }
    
    def generate_plan(self, skills, hours):
        """生成赚钱计划"""
        
        # 技能到机会的映射
        opportunities = {
            "编程": ["网站开发", "小程序", "自动化脚本", "数据爬虫"],
            "设计": ["Logo设计", "海报", "UI设计", "插画"],
            "写作": ["文案代写", "SEO文章", "技术文档"],
            "视频": ["短视频剪辑", "Vlog制作", "课程视频"],
            "翻译": ["文档翻译", "视频字幕"],
            "营销": ["社交媒体运营", "内容策划"]
        }
        
        # 找到匹配的机会
        matched = []
        for skill in skills:
            if skill in opportunities:
                matched.extend(opportunities[skill])
        
        if not matched:
            matched = ["自由职业", "知识付费", "数字产品"]
        
        # 估算收入
        skill_rates = {
            "编程": 100, "设计": 80, "写作": 60, "视频": 70,
            "翻译": 50, "营销": 90
        }
        
        avg_rate = 60
        for skill in skills:
            if skill in skill_rates:
                avg_rate = skill_rates[skill]
                break
        
        weekly_earnings = avg_rate * hours
        monthly_earnings = weekly_earnings * 4
        
        return {
            "matched_opportunities": list(set(matched))[:3],
            "estimated_earnings": {
                "hourly_rate": f"¥{avg_rate}",
                "weekly": f"¥{weekly_earnings}",
                "monthly": f"¥{monthly_earnings}"
            },
            "time_allocation": {
                "学习提升": f"{hours * 0.3}小时/周",
                "客户获取": f"{hours * 0.4}小时/周",
                "项目执行": f"{hours * 0.3}小时/周"
            }
        }
    
    def get_action_items(self, skills):
        """获取行动项"""
        return [
            "1. 选择1个主要技能方向",
            "2. 创建作品集（3个案例）",
            "3. 注册自由职业平台",
            "4. 设置合理的服务价格",
            "5. 开始接单并积累评价"
        ]

Tool = MoneyMakerPlanner