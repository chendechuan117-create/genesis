import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

from typing import Dict, Any, List
import json
from datetime import datetime

class MicroBusinessGenerator:
    """生成微型商业计划书 - 基于用户技能和资源的赚钱方案"""
    
    def __init__(self):
        self.name = "micro_business_generator"
        self.description = "根据用户技能、资金、时间生成可执行的赚钱方案"
        self.parameters = {
            "type": "object",
            "properties": {
                "skills": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "用户技能列表（如：编程、写作、设计、视频剪辑等）"
                },
                "initial_capital": {
                    "type": "number",
                    "description": "初始资金（人民币）",
                    "default": 0
                },
                "weekly_hours": {
                    "type": "number",
                    "description": "每周可用小时数",
                    "default": 10
                },
                "preferred_platforms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "偏好平台（如：淘宝、抖音、小红书、Upwork等）",
                    "default": []
                }
            },
            "required": ["skills"]
        }
    
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        skills = params.get("skills", [])
        capital = params.get("initial_capital", 0)
        hours = params.get("weekly_hours", 10)
        platforms = params.get("preferred_platforms", [])
        
        # 生成方案
        plan = self._generate_plan(skills, capital, hours, platforms)
        
        return {
            "success": True,
            "plan": plan,
            "next_steps": self._get_next_steps(plan),
            "estimated_earnings": self._estimate_earnings(skills, hours)
        }
    
    def _generate_plan(self, skills: List[str], capital: float, hours: float, platforms: List[str]) -> Dict[str, Any]:
        """生成具体的商业计划"""
        
        # 技能映射到赚钱机会
        skill_opportunities = {
            "编程": ["网站开发", "小程序制作", "自动化脚本", "数据爬虫"],
            "写作": ["文案代写", "SEO文章", "技术文档", "小说创作"],
            "设计": ["Logo设计", "海报制作", "UI/UX设计", "插画"],
            "视频剪辑": ["短视频制作", "Vlog剪辑", "课程视频", "广告片"],
            "翻译": ["文档翻译", "视频字幕", "网站本地化"],
            "营销": ["社交媒体运营", "内容策划", "广告投放"],
            "数据分析": ["Excel处理", "数据可视化", "报告生成"]
        }
        
        # 找到匹配的机会
        opportunities = []
        for skill in skills:
            if skill in skill_opportunities:
                opportunities.extend(skill_opportunities[skill])
        
        if not opportunities:
            opportunities = ["自由职业接单", "知识付费", "数字产品销售"]
        
        # 根据资金推荐方案
        if capital < 100:
            capital_strategy = "零成本启动：利用现有技能和免费平台"
        elif capital < 1000:
            capital_strategy = "低成本启动：购买必要工具/软件"
        else:
            capital_strategy = "可投资于设备、广告或库存"
        
        # 时间分配建议
        time_allocation = {
            "技能提升": hours * 0.3,
            "客户获取": hours * 0.4,
            "项目执行": hours * 0.3
        }
        
        return {
            "generated_at": datetime.now().isoformat(),
            "user_profile": {
                "skills": skills,
                "initial_capital": f"¥{capital}",
                "weekly_hours": hours,
                "platforms": platforms if platforms else ["通用平台"]
            },
            "recommended_opportunities": list(set(opportunities))[:5],  # 去重并取前5
            "capital_strategy": capital_strategy,
            "time_allocation": time_allocation,
            "platform_recommendations": self._recommend_platforms(skills, platforms),
            "first_week_action_plan": self._create_first_week_plan(opportunities)
        }
    
    def _recommend_platforms(self, skills: List[str], preferred: List[str]) -> List[Dict[str, str]]:
        """推荐平台"""
        platforms = [
            {"name": "Upwork", "type": "国际自由职业", "适合": ["编程", "设计", "写作", "翻译"]},
            {"name": "Fiverr", "type": "微型服务", "适合": ["设计", "视频剪辑", "写作"]},
            {"name": "淘宝服务市场", "type": "国内电商", "适合": ["设计", "编程", "文案"]},
            {"name": "抖音创作者中心", "type": "内容创作", "适合": ["视频剪辑", "营销"]},
            {"name": "小红书品牌合作", "type": "社交电商", "适合": ["写作", "设计", "营销"]},
            {"name": "知识星球", "type": "知识付费", "适合": ["写作", "数据分析", "编程"]}
        ]
        
        # 过滤匹配的平台
        recommended = []
        for platform in platforms:
            if any(skill in platform["适合"] for skill in skills):
                recommended.append(platform)
        
        # 如果用户有偏好，优先显示
        if preferred:
            preferred_platforms = [p for p in platforms if p["name"] in preferred]
            recommended = preferred_platforms + [p for p in recommended if p not in preferred_platforms]
        
        return recommended[:4]  # 返回最多4个
    
    def _create_first_week_plan(self, opportunities: List[str]) -> List[str]:
        """创建第一周行动计划"""
        if not opportunities:
            return []
        
        primary_opportunity = opportunities[0]
        
        return [
            f"Day 1-2: 研究{primary_opportunity}市场需求和定价",
            f"Day 3: 创建作品集/案例（至少3个示例）",
            f"Day 4: 注册1-2个推荐平台，完善个人资料",
            f"Day 5: 发布第一个服务/产品，设置合理价格",
            f"Day 6: 主动联系5个潜在客户",
            f"Day 7: 复盘优化，准备第二周计划"
        ]
    
    def _estimate_earnings(self, skills: List[str], hours: float) -> Dict[str, Any]:
        """估算收入"""
        # 基于技能的市场价格估算
        skill_rates = {
            "编程": {"hourly": 100, "monthly": 8000},
            "设计": {"hourly": 80, "monthly": 6000},
            "写作": {"hourly": 60, "monthly": 4000},
            "视频剪辑": {"hourly": 70, "monthly": 5000},
            "翻译": {"hourly": 50, "monthly": 3500},
            "营销": {"hourly": 90, "monthly": 7000},
            "数据分析": {"hourly": 110, "monthly": 9000}
        }
        
        # 计算平均时薪
        relevant_rates = [skill_rates.get(skill, {"hourly": 40, "monthly": 3000})["hourly"] for skill in skills]
        avg_hourly = sum(relevant_rates) / len(relevant_rates) if relevant_rates else 40
        
        weekly_hours = hours
        monthly_hours = weekly_hours * 4
        
        return {
            "estimated_hourly_rate": f"¥{avg_hourly:.0f}",
            "weekly_earnings": f"¥{avg_hourly * weekly_hours:.0f}",
            "monthly_earnings": f"¥{avg_hourly * monthly_hours:.0f}",
            "note": "基于市场平均价格估算，实际收入取决于技能水平、市场需求和个人执行力"
        }
    
    def _get_next_steps(self, plan: Dict[str, Any]) -> List[str]:
        """获取下一步行动"""
        return [
            "1. 确认技能匹配度，选择1-2个主要方向",
            "2. 注册推荐平台，完善个人资料",
            "3. 按照第一周计划开始执行",
            "4. 每周复盘调整策略",
            "5. 积累案例后逐步提高报价"
        ]

# 导出工具类
Tool = MicroBusinessGenerator