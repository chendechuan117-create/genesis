import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

from typing import Dict, List, Any, Optional
import json
from datetime import datetime

class ProfitStrategyGenerator(Tool):
    """赚钱策略生成器 - 基于用户背景生成个性化赚钱方案"""
    
    name = "profit_strategy_generator"
    description = "基于用户技能、资源和目标生成个性化赚钱策略"
    
    parameters = {
        "type": "object",
        "properties": {
            "user_skills": {
                "type": "array",
                "items": {"type": "string"},
                "description": "用户的技能列表（如：编程、设计、写作、营销等）"
            },
            "available_resources": {
                "type": "array", 
                "items": {"type": "string"},
                "description": "可用资源（如：电脑、网络、时间、资金、人脉等）"
            },
            "time_commitment": {
                "type": "string",
                "enum": ["part_time", "full_time", "weekends_only", "flexible"],
                "description": "时间投入程度"
            },
            "income_target": {
                "type": "string",
                "enum": ["extra_income", "replace_job", "scale_business", "passive_income"],
                "description": "收入目标类型"
            },
            "risk_tolerance": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "风险承受能力"
            }
        },
        "required": ["user_skills", "available_resources"]
    }
    
    def __init__(self):
        super().__init__()
        # 赚钱机会数据库
        self.opportunity_matrix = {
            "programming": {
                "name": "编程技能变现",
                "strategies": [
                    {
                        "name": "自由职业开发",
                        "description": "在Upwork/Fiverr等平台接项目",
                        "income_potential": "中高",
                        "time_to_income": "1-4周",
                        "required_skills": ["编程"],
                        "resources_needed": ["电脑", "网络"],
                        "risk_level": "低",
                        "action_steps": [
                            "1. 创建作品集（GitHub项目）",
                            "2. 注册自由职业平台账号",
                            "3. 从简单项目开始积累评价",
                            "4. 逐步提高报价"
                        ]
                    },
                    {
                        "name": "开发SaaS产品",
                        "description": "创建小型软件即服务产品",
                        "income_potential": "高",
                        "time_to_income": "1-3个月",
                        "required_skills": ["编程", "产品思维"],
                        "resources_needed": ["电脑", "网络", "少量资金"],
                        "risk_level": "中",
                        "action_steps": [
                            "1. 识别细分市场需求",
                            "2. 开发MVP（最小可行产品）",
                            "3. 定价策略（免费增值或订阅制）",
                            "4. 通过内容营销获取用户"
                        ]
                    }
                ]
            },
            "writing": {
                "name": "写作技能变现",
                "strategies": [
                    {
                        "name": "内容创作服务",
                        "description": "为企业或个人提供文案、博客、社交媒体内容",
                        "income_potential": "中",
                        "time_to_income": "1-2周",
                        "required_skills": ["写作"],
                        "resources_needed": ["电脑", "网络"],
                        "risk_level": "低",
                        "action_steps": [
                            "1. 创建写作样本集",
                            "2. 在内容平台建立个人品牌",
                            "3. 联系潜在客户（企业、博主）",
                            "4. 提供试写服务"
                        ]
                    }
                ]
            },
            "design": {
                "name": "设计技能变现",
                "strategies": [
                    {
                        "name": "UI/UX设计服务",
                        "description": "为网站、APP提供界面设计",
                        "income_potential": "中高",
                        "time_to_income": "2-4周",
                        "required_skills": ["设计"],
                        "resources_needed": ["电脑", "设计软件"],
                        "risk_level": "低",
                        "action_steps": [
                            "1. 创建设计作品集（Dribbble/Behance）",
                            "2. 学习Figma等设计工具",
                            "3. 在自由职业平台接单",
                            "4. 提供设计系统服务"
                        ]
                    }
                ]
            },
            "marketing": {
                "name": "营销技能变现",
                "strategies": [
                    {
                        "name": "数字营销顾问",
                        "description": "帮助企业优化SEO、社交媒体营销",
                        "income_potential": "中高",
                        "time_to_income": "1-3个月",
                        "required_skills": ["营销"],
                        "resources_needed": ["电脑", "网络", "分析工具"],
                        "risk_level": "中",
                        "action_steps": [
                            "1. 建立个人营销案例库",
                            "2. 在LinkedIn建立专业形象",
                            "3. 提供免费咨询获取案例",
                            "4. 制定结果导向的收费模式"
                        ]
                    }
                ]
            }
        }
        
        # 风险评估矩阵
        self.risk_assessment = {
            "low": ["自由职业开发", "内容创作服务", "UI/UX设计服务"],
            "medium": ["开发SaaS产品", "数字营销顾问"],
            "high": ["创业融资", "高风险投资"]
        }
        
        # 时间投入匹配
        self.time_matching = {
            "part_time": ["自由职业开发", "内容创作服务"],
            "full_time": ["开发SaaS产品", "数字营销顾问"],
            "weekends_only": ["内容创作服务"],
            "flexible": ["自由职业开发", "UI/UX设计服务"]
        }
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        """执行策略生成"""
        try:
            user_skills = kwargs.get("user_skills", [])
            available_resources = kwargs.get("available_resources", [])
            time_commitment = kwargs.get("time_commitment", "flexible")
            income_target = kwargs.get("income_target", "extra_income")
            risk_tolerance = kwargs.get("risk_tolerance", "medium")
            
            # 1. 匹配技能到机会
            matched_strategies = []
            
            for skill in user_skills:
                skill_lower = skill.lower()
                for category, category_data in self.opportunity_matrix.items():
                    if category in skill_lower or any(cat_word in skill_lower for cat_word in ["code", "program", "write", "design", "market"]):
                        for strategy in category_data["strategies"]:
                            # 检查资源匹配
                            resources_match = all(resource in available_resources 
                                                for resource in strategy["resources_needed"])
                            
                            if resources_match:
                                matched_strategies.append({
                                    **strategy,
                                    "matched_skill": skill,
                                    "category": category_data["name"]
                                })
            
            # 2. 根据风险承受能力过滤
            if risk_tolerance in self.risk_assessment:
                matched_strategies = [
                    s for s in matched_strategies 
                    if s["name"] in self.risk_assessment[risk_tolerance]
                ]
            
            # 3. 根据时间投入过滤
            if time_commitment in self.time_matching:
                matched_strategies = [
                    s for s in matched_strategies
                    if s["name"] in self.time_matching[time_commitment]
                ]
            
            # 4. 根据收入目标排序
            income_priority = {
                "extra_income": ["自由职业开发", "内容创作服务"],
                "replace_job": ["开发SaaS产品", "数字营销顾问"],
                "scale_business": ["开发SaaS产品"],
                "passive_income": ["开发SaaS产品"]
            }
            
            if income_target in income_priority:
                priority_list = income_priority[income_target]
                matched_strategies.sort(
                    key=lambda x: priority_list.index(x["name"]) 
                    if x["name"] in priority_list else len(priority_list)
                )
            
            # 5. 生成个性化建议
            if not matched_strategies:
                # 如果没有匹配的策略，提供通用建议
                generic_strategies = [
                    {
                        "name": "技能学习+变现",
                        "description": "先学习一项高需求技能，然后变现",
                        "income_potential": "中",
                        "time_to_income": "2-6个月",
                        "required_skills": ["学习能力"],
                        "resources_needed": ["电脑", "网络", "时间"],
                        "risk_level": "低",
                        "action_steps": [
                            "1. 选择高需求技能（如：Python编程、UI设计）",
                            "2. 通过免费/付费课程学习（Coursera/Udemy）",
                            "3. 完成实际项目建立作品集",
                            "4. 在自由职业平台开始接单"
                        ],
                        "matched_skill": "学习能力",
                        "category": "通用策略"
                    }
                ]
                matched_strategies = generic_strategies
            
            # 6. 生成执行路线图
            execution_roadmap = []
            for i, strategy in enumerate(matched_strategies[:3]):  # 取前3个最佳策略
                roadmap = {
                    "strategy_name": strategy["name"],
                    "priority": i + 1,
                    "timeline": [
                        {"week": "第1周", "tasks": strategy["action_steps"][:2]},
                        {"week": "第2-4周", "tasks": strategy["action_steps"][2:]}
                    ],
                    "expected_outcome": f"预计{strategy['time_to_income']}内开始产生收入",
                    "income_range": self._estimate_income_range(strategy["income_potential"])
                }
                execution_roadmap.append(roadmap)
            
            # 7. 生成最终报告
            result = {
                "generated_at": datetime.now().isoformat(),
                "user_profile": {
                    "skills": user_skills,
                    "resources": available_resources,
                    "time_commitment": time_commitment,
                    "income_target": income_target,
                    "risk_tolerance": risk_tolerance
                },
                "matched_strategies": matched_strategies[:5],  # 返回前5个策略
                "recommended_strategy": matched_strategies[0] if matched_strategies else None,
                "execution_roadmap": execution_roadmap,
                "next_steps": [
                    "选择1个策略专注执行",
                    "准备必要的资源（工具、账号等）",
                    "设定每周执行计划",
                    "记录进展并调整策略"
                ]
            }
            
            return {
                "success": True,
                "result": result,
                "message": f"成功生成{len(matched_strategies)}个赚钱策略"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "策略生成失败"
            }
    
    def _estimate_income_range(self, potential_level: str) -> str:
        """估算收入范围"""
        ranges = {
            "低": "每月 ¥1,000 - ¥5,000",
            "中": "每月 ¥5,000 - ¥20,000", 
            "中高": "每月 ¥20,000 - ¥50,000",
            "高": "每月 ¥50,000+"
        }
        return ranges.get(potential_level, "根据执行情况而定")