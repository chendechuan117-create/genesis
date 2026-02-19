import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

#!/usr/bin/env python3
"""
信息敏感度分析器 - 扫描环境、识别机会、推荐切入点
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional
import re

class InformationSensitivityAnalyzer:
    """信息敏感度分析器 - 扫描当前环境寻找最佳切入点"""
    
    name = "information_sensitivity_analyzer"
    description = "分析当前环境的信息敏感度，识别最佳商业切入点和机会"
    parameters = {
        "type": "object",
        "properties": {
            "scan_depth": {
                "type": "string",
                "enum": ["quick", "deep", "comprehensive"],
                "description": "扫描深度"
            },
            "focus_area": {
                "type": "string",
                "description": "重点关注领域（可选）"
            }
        },
        "required": ["scan_depth"]
    }
    
    def __init__(self):
        self.opportunities = []
        self.risk_factors = []
        self.recommendations = []
        
    def scan_system_environment(self) -> Dict[str, Any]:
        """扫描系统环境"""
        env_info = {
            "system": os.uname().sysname if hasattr(os, 'uname') else "Unknown",
            "python_version": sys.version,
            "current_dir": os.getcwd(),
            "user": os.getenv("USER", "unknown"),
            "timestamp": datetime.now().isoformat()
        }
        
        # 检查常见开发工具
        dev_tools = []
        for tool in ["git", "docker", "node", "npm", "python3", "pip3"]:
            try:
                os.system(f"which {tool} > /dev/null 2>&1")
                dev_tools.append(tool)
            except:
                pass
                
        env_info["dev_tools"] = dev_tools
        return env_info
    
    def analyze_opportunities(self, env_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """基于环境分析机会"""
        opportunities = []
        
        # 机会1：技术栈相关服务
        if len(env_info["dev_tools"]) >= 3:
            opportunities.append({
                "name": "开发者工具服务",
                "description": "基于现有技术栈提供自动化开发工具",
                "potential": "高",
                "ai_automation_level": "90%",
                "user_involvement": "收款设置、模板定义",
                "estimated_time_to_market": "1-3天",
                "revenue_model": "SaaS订阅、API调用"
            })
        
        # 机会2：数据监控服务
        opportunities.append({
            "name": "实时数据监控",
            "description": "7x24小时数据监控与警报服务",
            "potential": "高",
            "ai_automation_level": "95%",
            "user_involvement": "监控目标设置、报警联系人",
            "estimated_time_to_market": "2-5天",
            "revenue_model": "按监控目标收费、企业套餐"
        })
        
        # 机会3：内容自动化
        opportunities.append({
            "name": "内容生成工厂",
            "description": "自动化内容创作、优化、发布",
            "potential": "中高",
            "ai_automation_level": "85%",
            "user_involvement": "内容模板、发布渠道",
            "estimated_time_to_market": "3-7天",
            "revenue_model": "按字数/篇数收费、包月服务"
        })
        
        # 机会4：API代理服务
        opportunities.append({
            "name": "智能API代理",
            "description": "AI驱动的API调用优化、缓存、监控",
            "potential": "高",
            "ai_automation_level": "80%",
            "user_involvement": "API密钥管理、定价设置",
            "estimated_time_to_market": "5-10天",
            "revenue_model": "按调用次数、企业授权"
        })
        
        return opportunities
    
    def analyze_risks(self) -> List[Dict[str, Any]]:
        """分析风险因素"""
        risks = [
            {
                "risk": "技术依赖",
                "severity": "中",
                "mitigation": "多引擎备份、本地缓存"
            },
            {
                "risk": "合规问题",
                "severity": "高",
                "mitigation": "明确服务条款、数据隐私声明"
            },
            {
                "risk": "市场竞争",
                "severity": "中",
                "mitigation": "差异化定位、技术优势"
            },
            {
                "risk": "资源限制",
                "severity": "低",
                "mitigation": "渐进式扩展、云服务弹性"
            }
        ]
        return risks
    
    def generate_recommendations(self, opportunities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """生成具体推荐"""
        recommendations = []
        
        # 按潜力排序
        sorted_opps = sorted(opportunities, 
                           key=lambda x: {"高": 3, "中高": 2, "中": 1}.get(x["potential"], 0),
                           reverse=True)
        
        for i, opp in enumerate(sorted_opps[:3], 1):
            recommendations.append({
                "rank": i,
                "opportunity": opp["name"],
                "why_now": f"AI自动化水平达{opp['ai_automation_level']}，用户参与度最低",
                "first_step": f"创建{opp['name']}原型，测试核心功能",
                "timeline": opp["estimated_time_to_market"],
                "success_metrics": [
                    "7天内完成原型",
                    "获取第一批测试用户",
                    "验证收入模型"
                ]
            })
        
        return recommendations
    
    def execute(self, scan_depth: str = "quick", focus_area: Optional[str] = None) -> Dict[str, Any]:
        """执行分析"""
        
        print(f"🔍 开始信息敏感度分析 - 深度: {scan_depth}")
        if focus_area:
            print(f"📌 重点关注: {focus_area}")
        
        # 1. 扫描环境
        print("📊 扫描系统环境...")
        env_info = self.scan_system_environment()
        
        # 2. 分析机会
        print("💡 分析商业机会...")
        opportunities = self.analyze_opportunities(env_info)
        
        # 3. 分析风险
        print("⚠️  评估风险因素...")
        risks = self.analyze_risks()
        
        # 4. 生成推荐
        print("🎯 生成具体推荐...")
        recommendations = self.generate_recommendations(opportunities)
        
        # 5. 生成行动计划
        print("🚀 制定行动计划...")
        action_plan = self.generate_action_plan(recommendations)
        
        return {
            "environment_scan": env_info,
            "opportunities": opportunities,
            "risk_assessment": risks,
            "top_recommendations": recommendations,
            "action_plan": action_plan,
            "analysis_timestamp": datetime.now().isoformat()
        }
    
    def generate_action_plan(self, recommendations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成72小时行动计划"""
        action_plan = {
            "timeframe": "72小时启动计划",
            "phase_1_24h": {
                "goal": "确定方向并创建原型",
                "actions": [
                    "选择排名第一的推荐机会",
                    "创建最小可行产品(MVP)原型",
                    "设置基础监控和日志"
                ]
            },
            "phase_2_24h": {
                "goal": "测试与获取反馈",
                "actions": [
                    "部署到测试环境",
                    "邀请3-5个测试用户",
                    "收集初步反馈数据"
                ]
            },
            "phase_3_24h": {
                "goal": "优化与准备发布",
                "actions": [
                    "根据反馈优化核心功能",
                    "设置收款和用户管理系统",
                    "准备发布文档和营销材料"
                ]
            },
            "success_criteria": [
                "原型功能完整运行",
                "获得至少3个积极用户反馈",
                "收入流程测试通过"
            ]
        }
        return action_plan
    
    def format_report(self, analysis_result: Dict[str, Any]) -> str:
        """格式化分析报告"""
        report = []
        report.append("=" * 60)
        report.append("📈 信息敏感度分析报告")
        report.append("=" * 60)
        
        # 环境摘要
        report.append("\n🔧 环境摘要:")
        env = analysis_result["environment_scan"]
        report.append(f"  系统: {env.get('system', 'Unknown')}")
        report.append(f"  用户: {env.get('user', 'unknown')}")
        report.append(f"  开发工具: {', '.join(env.get('dev_tools', []))}")
        
        # 机会分析
        report.append("\n💡 识别到的机会 (按潜力排序):")
        for i, opp in enumerate(analysis_result["opportunities"], 1):
            report.append(f"  {i}. {opp['name']}")
            report.append(f"     描述: {opp['description']}")
            report.append(f"     潜力: {opp['potential']} | AI自动化: {opp['ai_automation_level']}")
            report.append(f"     用户参与: {opp['user_involvement']}")
            report.append(f"     收入模式: {opp['revenue_model']}")
        
        # 推荐
        report.append("\n🎯 推荐切入点:")
        for rec in analysis_result["top_recommendations"]:
            report.append(f"  #{rec['rank']}: {rec['opportunity']}")
            report.append(f"     理由: {rec['why_now']}")
            report.append(f"     第一步: {rec['first_step']}")
            report.append(f"     时间: {rec['timeline']}")
        
        # 行动计划
        plan = analysis_result["action_plan"]
        report.append(f"\n🚀 {plan['timeframe']}:")
        for phase, phase_info in [(k, v) for k, v in plan.items() if k.startswith('phase_')]:
            report.append(f"  {phase.replace('_', ' ').title()}:")
            report.append(f"     目标: {phase_info['goal']}")
            for action in phase_info['actions']:
                report.append(f"     • {action}")
        
        # 风险提示
        report.append("\n⚠️  风险提示:")
        for risk in analysis_result["risk_assessment"]:
            report.append(f"  {risk['risk']}: 严重性-{risk['severity']} | 缓解-{risk['mitigation']}")
        
        report.append("\n" + "=" * 60)
        report.append("💡 建议: 立即开始 Phase 1，72小时内验证可行性")
        report.append("=" * 60)
        
        return "\n".join(report)