import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

from typing import Dict, List, Any, Optional
import json
import re

class BrainstormSkill:
    """结构化头脑风暴技能，模拟 obra/superpowers 的 brainstorming 模块功能"""
    
    def __init__(self):
        self.name = "brainstorm_skill"
        self.description = "结构化头脑风暴工具，用于复杂问题的系统性分析"
        self.frameworks = {
            "5_whys": "通过连续问5个'为什么'来深入挖掘根本原因",
            "swot": "优势、劣势、机会、威胁分析",
            "scamper": "替代、合并、适应、修改、放大、缩小、用其他用途、反转、重组",
            "six_thinking_hats": "六顶思考帽：白帽(事实)、红帽(情感)、黑帽(谨慎)、黄帽(乐观)、绿帽(创意)、蓝帽(控制)",
            "first_principles": "第一性原理：从最基本的原理出发推导解决方案",
            "cost_benefit": "成本效益分析框架",
            "risk_matrix": "风险矩阵：概率 vs 影响分析"
        }
    
    def execute(self, problem_statement: str, framework: str = "structured") -> Dict[str, Any]:
        """
        执行结构化头脑风暴
        
        Args:
            problem_statement: 问题陈述
            framework: 使用的框架 (可选: structured, 5_whys, swot, scamper, six_thinking_hats)
        
        Returns:
            包含分析结果的字典
        """
        
        # 分析问题类型
        problem_type = self._analyze_problem_type(problem_statement)
        
        # 根据选择的框架执行分析
        if framework == "5_whys":
            analysis = self._five_whys_analysis(problem_statement)
        elif framework == "swot":
            analysis = self._swot_analysis(problem_statement)
        elif framework == "scamper":
            analysis = self._scamper_analysis(problem_statement)
        elif framework == "six_thinking_hats":
            analysis = self._six_thinking_hats_analysis(problem_statement)
        elif framework == "first_principles":
            analysis = self._first_principles_analysis(problem_statement)
        else:
            # 默认结构化分析
            analysis = self._structured_analysis(problem_statement)
        
        # 生成建议和行动计划
        recommendations = self._generate_recommendations(analysis, problem_type)
        
        # 估算 Token 消耗
        token_estimate = self._estimate_token_usage(problem_statement, analysis)
        
        return {
            "problem_statement": problem_statement,
            "problem_type": problem_type,
            "framework_used": framework,
            "analysis": analysis,
            "recommendations": recommendations,
            "action_plan": self._create_action_plan(recommendations),
            "token_estimate": token_estimate,
            "available_frameworks": list(self.frameworks.keys())
        }
    
    def _analyze_problem_type(self, problem: str) -> str:
        """分析问题类型"""
        problem_lower = problem.lower()
        
        if any(word in problem_lower for word in ["optimize", "improve", "efficiency", "performance"]):
            return "optimization"
        elif any(word in problem_lower for word in ["design", "architecture", "structure"]):
            return "design"
        elif any(word in problem_lower for word in ["cost", "budget", "expense", "token"]):
            return "cost_reduction"
        elif any(word in problem_lower for word in ["collaboration", "workflow", "process"]):
            return "process_improvement"
        elif any(word in problem_lower for word in ["risk", "security", "failure"]):
            return "risk_management"
        else:
            return "general_problem_solving"
    
    def _structured_analysis(self, problem: str) -> Dict[str, Any]:
        """执行结构化分析"""
        return {
            "problem_decomposition": self._decompose_problem(problem),
            "root_cause_analysis": self._identify_root_causes(problem),
            "constraints_identification": self._identify_constraints(problem),
            "stakeholder_analysis": self._identify_stakeholders(problem),
            "success_metrics": self._define_success_metrics(problem)
        }
    
    def _five_whys_analysis(self, problem: str) -> Dict[str, Any]:
        """5 Why 分析"""
        whys = []
        current_problem = problem
        
        for i in range(5):
            if i == 0:
                why = f"Why is '{current_problem}' a problem?"
            else:
                why = f"Why does that happen? (Level {i+1})"
            
            whys.append({
                "question": why,
                "potential_answer": f"This requires deeper investigation into underlying causes at level {i+1}"
            })
            current_problem = f"Root cause level {i+1}"
        
        return {
            "method": "5_whys_root_cause_analysis",
            "analysis_chain": whys,
            "likely_root_cause": "Multiple interconnected factors requiring systemic solution"
        }
    
    def _swot_analysis(self, problem: str) -> Dict[str, Any]:
        """SWOT 分析"""
        return {
            "strengths": [
                "Existing multi-agent architecture provides modularity",
                "Clear role separation (Insight/Judge/Execute)",
                "Tool integration capability",
                "Memory management system"
            ],
            "weaknesses": [
                "Potential token redundancy in inter-agent communication",
                "Synchronization overhead between agents",
                "Decision latency in complex scenarios"
            ],
            "opportunities": [
                "Implement message compression techniques",
                "Add caching layer for frequent queries",
                "Optimize agent handoff protocols",
                "Introduce hierarchical decision making"
            ],
            "threats": [
                "Increased complexity leading to higher maintenance cost",
                "Over-engineering reducing system responsiveness",
                "API rate limits and cost constraints"
            ]
        }
    
    def _scamper_analysis(self, problem: str) -> Dict[str, Any]:
        """SCAMPER 创意分析"""
        return {
            "substitute": [
                "Replace verbose explanations with concise templates",
                "Substitute synchronous communication with batched async messages"
            ],
            "combine": [
                "Combine Insight and Judge phases for simple queries",
                "Merge similar tool calls into single operations"
            ],
            "adapt": [
                "Adapt message routing based on query complexity",
                "Adapt agent activation based on workload"
            ],
            "modify": [
                "Modify token allocation based on task priority",
                "Modify agent response format to be more compact"
            ],
            "put_to_other_uses": [
                "Use memory system for caching frequent responses",
                "Repurpose monitoring tools for token usage tracking"
            ],
            "eliminate": [
                "Eliminate redundant validation steps",
                "Remove unnecessary formatting from agent outputs"
            ],
            "reverse": [
                "Reverse decision flow for simple queries (Execute first)",
                "Invert priority: optimize for common cases, not edge cases"
            ]
        }
    
    def _six_thinking_hats_analysis(self, problem: str) -> Dict[str, Any]:
        """六顶思考帽分析"""
        return {
            "white_hat_facts": [
                "Current multi-agent architecture uses 3 agents",
                "Each agent consumes tokens for processing",
                "Inter-agent communication adds overhead",
                "Tool calls have separate token costs"
            ],
            "red_hat_emotions": [
                "Frustration with slow complex queries",
                "Concern about rising API costs",
                "Desire for more efficient collaboration",
                "Satisfaction with current modular design"
            ],
            "black_hat_caution": [
                "Over-optimization could break existing workflows",
                "Aggressive caching might lead to stale responses",
                "Reduced communication could cause coordination failures",
                "Premature optimization is a common pitfall"
            ],
            "yellow_hat_optimism": [
                "Significant token savings possible (30-50%)",
                "Improved response times for users",
                "Scalability benefits for larger deployments",
                "Learning opportunity for system optimization"
            ],
            "green_hat_creativity": [
                "Implement adaptive agent activation",
                "Create token-aware routing system",
                "Develop context compression algorithms",
                "Design hierarchical decision trees"
            ],
            "blue_hat_control": [
                "Need phased implementation plan",
                "Require metrics for before/after comparison",
                "Should establish rollback procedures",
                "Must maintain backward compatibility"
            ]
        }
    
    def _first_principles_analysis(self, problem: str) -> Dict[str, Any]:
        """第一性原理分析"""
        return {
            "fundamental_truths": [
                "Token cost is proportional to input + output length",
                "Each agent processes information independently",
                "Communication between agents requires message passing",
                "Tool calls have fixed overhead regardless of complexity"
            ],
            "assumptions_challenged": [
                "All queries need all three agents",
                "Every message needs full context",
                "All tool calls are necessary",
                "Current architecture is optimal"
            ],
            "reconstructed_solution": [
                "Agent activation should be query-dependent",
                "Context should be compressed for simple queries",
                "Tool calls should be batched when possible",
                "Memory should cache frequent patterns"
            ]
        }
    
    def _decompose_problem(self, problem: str) -> List[str]:
        """问题分解"""
        return [
            "Agent communication overhead",
            "Redundant processing across agents",
            "Inefficient context management",
            "Suboptimal tool call patterns",
            "Lack of token-aware routing"
        ]
    
    def _identify_root_causes(self, problem: str) -> List[str]:
        """识别根本原因"""
        return [
            "Fixed three-agent workflow for all queries",
            "Full context replication between agents",
            "No message compression or summarization",
            "Tool calls without consideration of token cost",
            "Lack of adaptive agent activation"
        ]
    
    def _identify_constraints(self, problem: str) -> List[str]:
        """识别约束条件"""
        return [
            "Must maintain backward compatibility",
            "Cannot change core agent architecture",
            "Limited ability to modify underlying LLM",
            "Real-time response requirements",
            "Budget constraints on API usage"
        ]
    
    def _identify_stakeholders(self, problem: str) -> List[Dict[str, str]]:
        """识别利益相关者"""
        return [
            {"role": "end_users", "interest": "Fast, accurate responses"},
            {"role": "system_administrators", "interest": "Cost-effective operation"},
            {"role": "developers", "interest": "Maintainable architecture"},
            {"role": "business_owners", "interest": "ROI on AI investment"}
        ]
    
    def _define_success_metrics(self, problem: str) -> Dict[str, str]:
        """定义成功指标"""
        return {
            "token_reduction": "30-50% reduction in average token usage",
            "response_time": "20% improvement in complex query response time",
            "cost_savings": "Monthly API cost reduction proportional to usage",
            "user_satisfaction": "No degradation in response quality",
            "system_complexity": "Minimal increase in maintenance overhead"
        }
    
    def _generate_recommendations(self, analysis: Dict[str, Any], problem_type: str) -> List[Dict[str, Any]]:
        """生成建议"""
        recommendations = []
        
        # 基于问题类型的建议
        if problem_type == "optimization":
            recommendations.extend([
                {
                    "priority": "high",
                    "recommendation": "Implement adaptive agent activation",
                    "rationale": "Not all queries need all three agents",
                    "expected_impact": "Reduce token usage by 30% for simple queries"
                },
                {
                    "priority": "high",
                    "recommendation": "Add message compression layer",
                    "rationale": "Reduce context duplication between agents",
                    "expected_impact": "Save 20-40% on inter-agent communication"
                },
                {
                    "priority": "medium",
                    "recommendation": "Implement token-aware routing",
                    "rationale": "Route queries to most cost-effective agent path",
                    "expected_impact": "Optimize cost-performance tradeoff"
                }
            ])
        
        # 基于分析结果的建议
        if "root_cause_analysis" in analysis:
            recommendations.append({
                "priority": "medium",
                "recommendation": "Add caching for frequent query patterns",
                "rationale": "Reduce redundant processing of similar queries",
                "expected_impact": "Lower token cost for repetitive tasks"
            })
        
        return recommendations
    
    def _create_action_plan(self, recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """创建行动计划"""
        action_plan = []
        
        high_priority = [r for r in recommendations if r["priority"] == "high"]
        medium_priority = [r for r in recommendations if r["priority"] == "medium"]
        
        week = 1
        for rec in high_priority:
            action_plan.append({
                "phase": f"Week {week}",
                "action": f"Implement: {rec['recommendation']}",
                "owner": "Development Team",
                "success_criteria": rec["expected_impact"],
                "dependencies": "None"
            })
            week += 1
        
        for rec in medium_priority:
            action_plan.append({
                "phase": f"Week {week}",
                "action": f"Design and test: {rec['recommendation']}",
                "owner": "Architecture Team",
                "success_criteria": f"Proof of concept showing {rec['expected_impact']}",
                "dependencies": "High priority implementations complete"
            })
            week += 1
        
        return action_plan
    
    def _estimate_token_usage(self, problem: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """估算 Token 消耗"""
        problem_length = len(problem.split())
        analysis_complexity = len(str(analysis)) / 1000  # 粗略估算
        
        return {
            "input_tokens": problem_length * 1.3,  # 估算
            "analysis_tokens": analysis_complexity * 750,
            "output_tokens": 500,  # 报告生成
            "total_estimated": (problem_length * 1.3) + (analysis_complexity * 750) + 500,
            "cost_assumption": "Based on GPT-4 pricing (~$0.03/1K tokens output)",
            "estimated_cost_usd": "~$0.02 - $0.05 per brainstorming session"
        }


# 工具类定义
class Tool:
    def __init__(self):
        self.brainstorm = BrainstormSkill()
    
    @property
    def name(self):
        return "brainstorm_tool"
    
    @property
    def description(self):
        return "结构化头脑风暴工具，基于 obra/superpowers 的 brainstorming 模块理念"
    
    @property
    def parameters(self):
        return {
            "type": "object",
            "properties": {
                "problem_statement": {
                    "type": "string",
                    "description": "要分析的问题陈述"
                },
                "framework": {
                    "type": "string",
                    "description": "使用的分析框架",
                    "enum": ["structured", "5_whys", "swot", "scamper", "six_thinking_hats", "first_principles"],
                    "default": "structured"
                }
            },
            "required": ["problem_statement"]
        }
    
    def execute(self, problem_statement: str, framework: str = "structured") -> Dict[str, Any]:
        """执行头脑风暴分析"""
        return self.brainstorm.execute(problem_statement, framework)