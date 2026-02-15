import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

from typing import Dict, List, Any
import json

class ComparativeAnalysisTool:
    name = "comparative_analysis_tool"
    description = "对比分析不同AI架构方案，生成结构化对比报告"
    parameters = {
        "type": "object",
        "properties": {
            "architecture_a": {
                "type": "string",
                "description": "第一个架构名称"
            },
            "architecture_b": {
                "type": "string", 
                "description": "第二个架构名称"
            },
            "user_context": {
                "type": "string",
                "description": "用户的具体场景和需求"
            }
        },
        "required": ["architecture_a", "architecture_b", "user_context"]
    }

    def execute(self, architecture_a: str, architecture_b: str, user_context: str) -> Dict[str, Any]:
        """执行对比分析"""
        
        # 架构知识库
        architectures = {
            "Genesis Triad": {
                "description": "三引擎协同架构（主备+本地代理）",
                "core_concept": "智能体作为独立决策实体",
                "strengths": [
                    "高可用性（主备切换）",
                    "本地化执行能力",
                    "自主决策框架",
                    "工具自生成能力",
                    "系统级集成"
                ],
                "weaknesses": [
                    "架构复杂度较高",
                    "需要本地部署",
                    "学习曲线较陡"
                ],
                "best_for": [
                    "需要系统级控制的场景",
                    "本地自动化任务",
                    "自主决策需求",
                    "工具链扩展"
                ],
                "revenue_model": [
                    "自动化服务订阅",
                    "决策即服务",
                    "架构授权"
                ],
                "implementation_cost": "中等（需要本地环境）",
                "scalability": "垂直扩展（单机多引擎）"
            },
            "AI Agentic Workflow": {
                "description": "基于工作流的智能体编排架构",
                "core_concept": "任务分解与流程自动化",
                "strengths": [
                    "标准化工作流",
                    "易于集成现有系统",
                    "可视化编排",
                    "团队协作友好",
                    "云原生部署"
                ],
                "weaknesses": [
                    "依赖外部API",
                    "自主性有限",
                    "系统级控制弱",
                    "工具扩展复杂"
                ],
                "best_for": [
                    "业务流程自动化",
                    "内容生成流水线",
                    "数据分析工作流",
                    "团队协作场景"
                ],
                "revenue_model": [
                    "SaaS订阅",
                    "按使用量计费",
                    "企业定制"
                ],
                "implementation_cost": "低到中等（云服务）",
                "scalability": "水平扩展（分布式）"
            }
        }
        
        # 获取架构信息
        arch_a_info = architectures.get(architecture_a, {})
        arch_b_info = architectures.get(architecture_b, {})
        
        if not arch_a_info or not arch_b_info:
            return {
                "error": f"未知架构。可用架构: {list(architectures.keys())}"
            }
        
        # 生成对比矩阵
        comparison_matrix = []
        for dimension in ["strengths", "weaknesses", "best_for", "revenue_model", "implementation_cost", "scalability"]:
            comparison_matrix.append({
                "dimension": dimension.replace("_", " ").title(),
                architecture_a: arch_a_info.get(dimension, []),
                architecture_b: arch_b_info.get(dimension, [])
            })
        
        # 场景适配度分析
        scenario_analysis = self._analyze_scenario_fit(user_context, arch_a_info, arch_b_info)
        
        # 推荐决策
        recommendation = self._generate_recommendation(user_context, arch_a_info, arch_b_info)
        
        return {
            "comparison_summary": {
                architecture_a: {
                    "description": arch_a_info["description"],
                    "core_concept": arch_a_info["core_concept"]
                },
                architecture_b: {
                    "description": arch_b_info["description"],
                    "core_concept": arch_b_info["core_concept"]
                }
            },
            "comparison_matrix": comparison_matrix,
            "scenario_analysis": scenario_analysis,
            "recommendation": recommendation,
            "next_steps": [
                "根据你的具体需求选择架构",
                "考虑混合方案的可能性",
                "从小规模试点开始"
            ]
        }
    
    def _analyze_scenario_fit(self, context: str, arch_a: Dict, arch_b: Dict) -> Dict[str, Any]:
        """分析场景适配度"""
        
        context_keywords = context.lower()
        
        # 关键词匹配
        genesis_keywords = ["本地", "系统", "自主", "工具", "控制", "执行", "实体", "决策"]
        agentic_keywords = ["工作流", "流程", "协作", "团队", "云", "api", "自动化", "集成"]
        
        genesis_score = sum(1 for kw in genesis_keywords if kw in context_keywords)
        agentic_score = sum(1 for kw in agentic_keywords if kw in context_keywords)
        
        return {
            "context_analysis": context,
            "genesis_triad_fit_score": genesis_score,
            "ai_agentic_fit_score": agentic_score,
            "key_matches": {
                "Genesis Triad": [kw for kw in genesis_keywords if kw in context_keywords],
                "AI Agentic Workflow": [kw for kw in agentic_keywords if kw in context_keywords]
            }
        }
    
    def _generate_recommendation(self, context: str, arch_a: Dict, arch_b: Dict) -> Dict[str, Any]:
        """生成推荐建议"""
        
        # 基于场景分析
        scenario_fit = self._analyze_scenario_fit(context, arch_a, arch_b)
        
        if scenario_fit["genesis_triad_fit_score"] > scenario_fit["ai_agentic_fit_score"]:
            recommended = "Genesis Triad"
            reason = "你的场景更强调本地控制、自主决策和系统级集成"
        elif scenario_fit["ai_agentic_fit_score"] > scenario_fit["genesis_triad_fit_score"]:
            recommended = "AI Agentic Workflow"
            reason = "你的场景更适合标准化工作流、团队协作和云原生部署"
        else:
            recommended = "混合方案"
            reason = "两种架构各有优势，可以考虑结合使用"
        
        return {
            "recommended_architecture": recommended,
            "reason": reason,
            "considerations": [
                "技术栈熟悉度",
                "部署复杂度",
                "长期维护成本",
                "团队技能匹配"
            ]
        }