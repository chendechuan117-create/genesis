import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

from typing import Dict, Any, List
import json
from datetime import datetime

class BusinessModelGen:
    """商业模型生成器 - 为AI系统设计可执行的盈利方案"""
    
    def __init__(self):
        self.name = "business_model_gen"
        self.description = "为AI系统生成结构化商业模型和收益实现方案"
        self.parameters = {
            "target_market": "目标市场（如：开发者、中小企业、个人用户）",
            "available_resources": "可用资源（如：API能力、数据处理、自动化）", 
            "revenue_goal": "收入目标（如：月收入$1000）",
            "risk_tolerance": "风险承受度（低/中/高）",
            "time_horizon": "时间范围（如：3个月）"
        }
    
    def execute(self, target_market: str = "个人用户", 
                available_resources: str = "AI对话、文件操作、网络搜索",
                revenue_goal: str = "$1000/月",
                risk_tolerance: str = "中",
                time_horizon: str = "3个月") -> Dict[str, Any]:
        """执行商业模型生成"""
        
        # 生成商业模型
        model = self._generate_business_model(
            target_market, available_resources, revenue_goal, risk_tolerance, time_horizon
        )
        
        # 生成执行计划
        execution_plan = self._generate_execution_plan(model)
        
        # 生成财务预测
        financial_forecast = self._generate_financial_forecast(revenue_goal, time_horizon)
        
        return {
            "business_model": model,
            "execution_plan": execution_plan,
            "financial_forecast": financial_forecast,
            "next_steps": self._get_next_steps(model)
        }
    
    def _generate_business_model(self, target_market: str, resources: str, 
                                revenue_goal: str, risk_tolerance: str, 
                                time_horizon: str) -> Dict[str, Any]:
        """生成商业模型画布"""
        
        # 基于风险承受度选择商业模式
        if risk_tolerance == "低":
            model_type = "订阅服务"
            pricing = "$9.99-49.99/月"
        elif risk_tolerance == "高":
            model_type = "项目制服务"
            pricing = "$500-5000/项目"
        else:
            model_type = "混合模式"
            pricing = "基础订阅 + 增值服务"
        
        # 价值主张
        value_propositions = {
            "核心价值": [
                "24/7 AI助手服务",
                "自动化工作流",
                "数据分析和处理",
                "代码生成和调试"
            ],
            "差异化价值": [
                "本地化部署能力",
                "多工具集成",
                "自定义技能扩展",
                "实时网络搜索"
            ]
        }
        
        # 收入流
        revenue_streams = []
        if model_type == "订阅服务":
            revenue_streams = [
                "个人订阅：$9.99/月",
                "团队订阅：$49.99/月", 
                "企业订阅：$299/月"
            ]
        elif model_type == "项目制服务":
            revenue_streams = [
                "定制开发：$1000-5000/项目",
                "系统集成：$500-2000/次",
                "数据服务：$300-1000/报告"
            ]
        else:
            revenue_streams = [
                "基础功能：免费",
                "高级功能：$19.99/月",
                "API调用：$0.01/100次",
                "定制服务：按需定价"
            ]
        
        # 成本结构
        cost_structure = [
            "服务器成本：$50-200/月",
            "API调用成本：$0-100/月",
            "维护成本：$100/月（人工）",
            "营销成本：$200/月"
        ]
        
        # 关键指标
        key_metrics = [
            "月活跃用户数",
            "用户留存率", 
            "平均收入每用户",
            "客户获取成本",
            "毛利率"
        ]
        
        return {
            "模型类型": model_type,
            "目标市场": target_market,
            "可用资源": resources,
            "定价策略": pricing,
            "价值主张": value_propositions,
            "收入流": revenue_streams,
            "成本结构": cost_structure,
            "关键指标": key_metrics,
            "收入目标": revenue_goal,
            "时间范围": time_horizon
        }
    
    def _generate_execution_plan(self, model: Dict[str, Any]) -> List[Dict[str, Any]]:
        """生成执行计划"""
        
        plan = [
            {
                "阶段": "第1周",
                "任务": "市场验证",
                "具体行动": [
                    "创建简单的落地页展示AI能力",
                    "在技术社区发布免费试用",
                    "收集10个潜在用户反馈"
                ],
                "交付物": "市场验证报告"
            },
            {
                "阶段": "第2-4周", 
                "任务": "MVP开发",
                "具体行动": [
                    "基于反馈确定核心功能",
                    "开发最小可行产品",
                    "设置支付系统",
                    "创建用户文档"
                ],
                "交付物": "可用的MVP版本"
            },
            {
                "阶段": "第2-3个月",
                "任务": "用户获取",
                "具体行动": [
                    "启动付费计划",
                    "内容营销（博客、教程）",
                    "合作伙伴拓展",
                    "用户推荐计划"
                ],
                "交付物": "10个付费用户"
            },
            {
                "阶段": "第3个月+",
                "任务": "规模化",
                "具体行动": [
                    "优化产品体验",
                    "扩展功能模块",
                    "自动化营销流程",
                    "探索企业市场"
                ],
                "交付物": "稳定收入流"
            }
        ]
        
        return plan
    
    def _generate_financial_forecast(self, revenue_goal: str, time_horizon: str) -> Dict[str, Any]:
        """生成财务预测"""
        
        # 解析收入目标
        goal_value = 1000  # 默认$1000
        if "$" in revenue_goal:
            try:
                goal_value = float(revenue_goal.replace("$", "").replace("/月", "").replace("/月", ""))
            except:
                pass
        
        # 基于时间范围的预测
        if "3个月" in time_horizon:
            months = 3
        elif "6个月" in time_horizon:
            months = 6
        elif "12个月" in time_horizon:
            months = 12
        else:
            months = 3
        
        monthly_forecast = []
        cumulative_revenue = 0
        
        for month in range(1, months + 1):
            if month == 1:
                revenue = goal_value * 0.1  # 第一个月10%
            elif month == 2:
                revenue = goal_value * 0.3  # 第二个月30%
            else:
                revenue = goal_value * 0.6 / (months - 2)  # 剩余月份平均
            
            costs = 350  # 固定成本
            profit = revenue - costs
            cumulative_revenue += revenue
            
            monthly_forecast.append({
                "月份": f"第{month}个月",
                "收入": f"${revenue:.2f}",
                "成本": f"${costs:.2f}",
                "利润": f"${profit:.2f}",
                "累计收入": f"${cumulative_revenue:.2f}"
            })
        
        return {
            "预测周期": f"{months}个月",
            "月度预测": monthly_forecast,
            "总收入目标": f"${goal_value * months:.2f}",
            "平均月成本": "$350",
            "盈亏平衡点": "第2个月末"
        }
    
    def _get_next_steps(self, model: Dict[str, Any]) -> List[str]:
        """获取下一步行动"""
        
        return [
            "1. 立即行动：创建产品展示页面",
            "2. 技术准备：设置支付网关和用户系统",
            "3. 市场测试：在Reddit/HackerNews发布免费试用",
            "4. 数据收集：记录用户使用情况和反馈",
            "5. 迭代优化：基于数据调整产品功能",
            "6. 规模化：自动化营销和用户支持"
        ]


# 导出工具类
Tool = BusinessModelGen