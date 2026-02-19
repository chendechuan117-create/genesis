import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

#!/usr/bin/env python3
"""
个人方向与舒适区诊断工具
帮助用户通过结构化输入，清晰自己的方向和舒适区
"""

from typing import Dict, List, Any, Optional
import json
from datetime import datetime

class PersonalDirectionDiagnostic:
    """个人方向与舒适区诊断工具"""
    
    def __init__(self):
        self.name = "personal_direction_diagnostic"
        self.description = "通过结构化输入帮助用户清晰自己的方向和舒适区"
        
        # 诊断框架
        self.diagnostic_framework = {
            "current_state": {
                "skills": "当前掌握的技能（技术/软技能）",
                "interests": "真正感兴趣的事物（不是应该感兴趣的）", 
                "energy_patterns": "什么情况下精力充沛/耗尽",
                "avoidance_patterns": "本能回避的事物/情境"
            },
            "past_patterns": {
                "success_patterns": "过往成功经历中的共同模式",
                "failure_patterns": "失败经历中的共同模式",
                "flow_states": "进入心流状态的场景",
                "regret_decisions": "后悔的决策及其原因"
            },
            "values_identity": {
                "core_values": "最看重的3-5个价值观",
                "identity_statements": "'我是...'的陈述",
                "non_negotiables": "绝对不能妥协的事情",
                "legacy_desire": "希望留下什么影响"
            },
            "ideal_scenarios": {
                "ideal_day": "理想的一天如何度过",
                "ideal_work": "理想的工作状态描述",
                "ideal_environment": "理想的工作/生活环境",
                "energy_balance": "理想的工作/生活/学习比例"
            },
            "constraints_realities": {
                "current_constraints": "当前的限制因素（时间/金钱/技能）",
                "non_constraints": "其实不是限制的因素",
                "realistic_timeline": "现实的时间框架",
                "acceptable_risks": "愿意承担的风险程度"
            }
        }
        
        self.questions = self._generate_questions()
        
    def _generate_questions(self) -> Dict[str, List[str]]:
        """生成引导性问题"""
        return {
            "current_state": [
                "列出你真正擅长的3-5件事（不一定是工作技能）",
                "做什么事情时你会忘记时间？",
                "什么类型的工作让你感到精力耗尽？",
                "你本能地回避什么类型的任务或情境？"
            ],
            "past_patterns": [
                "回忆3个你感到'做得很好'的时刻，它们有什么共同点？",
                "回忆3个让你感到'这不对'的时刻，它们有什么共同点？",
                "什么情况下你会进入'心流'状态（完全沉浸）？",
                "你最后悔的职业/人生决策是什么？为什么？"
            ],
            "values_identity": [
                "如果只能选择3个价值观指导你的人生，会是哪三个？",
                "用'我是...'开头写5个关于自己的陈述",
                "在什么情况下你会说'这绝对不行'？",
                "你希望10年后人们如何描述你的贡献？"
            ],
            "ideal_scenarios": [
                "描述你理想的工作日（从起床到睡觉）",
                "理想的工作状态是怎样的？（独立/协作、创造/执行等）",
                "你理想的工作环境是什么样的？",
                "理想情况下，工作/生活/学习的时间比例是多少？"
            ],
            "constraints_realities": [
                "当前限制你的主要因素是什么？（具体点）",
                "哪些你认为是限制的因素，其实可能不是？",
                "现实的时间框架是怎样的？（3个月/6个月/1年）",
                "你愿意为改变承担多大的风险？"
            ]
        }
    
    def collect_inputs(self) -> Dict[str, Any]:
        """收集用户输入"""
        print("🎯 个人方向与舒适区诊断")
        print("=" * 60)
        print("这不是畅想未来，而是通过具体问题帮你清晰方向")
        print("请诚实回答，不需要'正确'答案，只需要'真实'答案\n")
        
        responses = {}
        
        for category, questions in self.questions.items():
            print(f"\n📋 {category.replace('_', ' ').title()}")
            print("-" * 40)
            
            category_responses = []
            for i, question in enumerate(questions, 1):
                print(f"\n{i}. {question}")
                response = input("你的回答: ").strip()
                if response:
                    category_responses.append(response)
            
            responses[category] = category_responses
        
        return responses
    
    def analyze_responses(self, responses: Dict[str, List[str]]) -> Dict[str, Any]:
        """分析用户回答，生成洞察"""
        analysis = {
            "comfort_zone_indicators": [],
            "direction_clues": [],
            "conflicts_tensions": [],
            "actionable_insights": []
        }
        
        # 分析当前状态
        if "current_state" in responses:
            current = responses["current_state"]
            if len(current) >= 2:
                # 寻找技能与兴趣的交集
                skills_text = current[0] if len(current) > 0 else ""
                interests_text = current[1] if len(current) > 1 else ""
                
                # 提取关键词
                skills_keywords = self._extract_keywords(skills_text)
                interests_keywords = self._extract_keywords(interests_text)
                
                # 寻找交集（潜在的舒适区）
                intersection = set(skills_keywords) & set(interests_keywords)
                if intersection:
                    analysis["comfort_zone_indicators"].append(
                        f"舒适区迹象：技能与兴趣的交集 → {', '.join(intersection)}"
                    )
        
        # 分析过去模式
        if "past_patterns" in responses:
            patterns = responses["past_patterns"]
            if len(patterns) >= 2:
                success_pattern = patterns[0] if len(patterns) > 0 else ""
                failure_pattern = patterns[1] if len(patterns) > 1 else ""
                
                # 对比成功与失败模式
                if success_pattern and failure_pattern:
                    analysis["direction_clues"].append(
                        f"方向线索：成功模式 '{success_pattern[:50]}...' vs 失败模式 '{failure_pattern[:50]}...'"
                    )
        
        # 分析价值观
        if "values_identity" in responses:
            values = responses["values_identity"]
            if len(values) >= 1:
                core_values = values[0] if len(values) > 0 else ""
                analysis["direction_clues"].append(
                    f"价值观指引：{core_values[:100]}..."
                )
        
        # 分析理想与现实
        if "ideal_scenarios" in responses and "constraints_realities" in responses:
            ideal = responses["ideal_scenarios"][0] if responses["ideal_scenarios"] else ""
            constraints = responses["constraints_realities"][0] if responses["constraints_realities"] else ""
            
            if ideal and constraints:
                analysis["conflicts_tensions"].append(
                    f"理想与现实：理想状态 '{ideal[:50]}...' vs 限制 '{constraints[:50]}...'"
                )
        
        # 生成行动建议
        if analysis["comfort_zone_indicators"]:
            comfort_zone = analysis["comfort_zone_indicators"][0]
            analysis["actionable_insights"].append(
                f"立即行动：在{comfort_zone}中寻找一个小项目开始"
            )
        
        if analysis["conflicts_tensions"]:
            analysis["actionable_insights"].append(
                "解决冲突：列出限制因素，区分哪些是真实的，哪些是想象的"
            )
        
        return analysis
    
    def _extract_keywords(self, text: str) -> List[str]:
        """从文本中提取关键词"""
        # 简单的关键词提取
        stop_words = {"的", "了", "在", "是", "我", "你", "他", "她", "它", "和", "与", "或"}
        words = text.split()
        keywords = [word for word in words if len(word) > 1 and word not in stop_words]
        return keywords[:10]  # 返回前10个关键词
    
    def generate_report(self, responses: Dict[str, Any], analysis: Dict[str, Any]) -> str:
        """生成诊断报告"""
        report = []
        report.append("=" * 60)
        report.append("🎯 个人方向与舒适区诊断报告")
        report.append("=" * 60)
        report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        # 1. 原始回答摘要
        report.append("📝 你的回答摘要")
        report.append("-" * 40)
        for category, answers in responses.items():
            report.append(f"\n{category.replace('_', ' ').title()}:")
            for i, answer in enumerate(answers, 1):
                if answer:
                    report.append(f"  {i}. {answer[:100]}{'...' if len(answer) > 100 else ''}")
        
        # 2. 分析洞察
        report.append("\n\n🔍 分析洞察")
        report.append("-" * 40)
        
        for insight_type, insights in analysis.items():
            if insights:
                report.append(f"\n{insight_type.replace('_', ' ').title()}:")
                for insight in insights:
                    report.append(f"  • {insight}")
        
        # 3. 具体建议
        report.append("\n\n🎯 具体建议")
        report.append("-" * 40)
        
        # 基于舒适区建议
        if analysis["comfort_zone_indicators"]:
            report.append("\n1. 舒适区强化:")
            report.append("   - 在已识别的舒适区内，每天投入30分钟")
            report.append("   - 寻找可以展示这些优势的小项目")
            report.append("   - 记录在这些活动中的能量变化")
        
        # 基于方向线索建议
        if analysis["direction_clues"]:
            report.append("\n2. 方向探索:")
            report.append("   - 每周尝试一个与方向线索相关的微小实验")
            report.append("   - 寻找这个方向上的榜样人物")
            report.append("   - 记录实验过程中的感受和反馈")
        
        # 基于冲突建议
        if analysis["conflicts_tensions"]:
            report.append("\n3. 冲突解决:")
            report.append("   - 将限制因素分为'真实限制'和'心理限制'")
            report.append("   - 为每个真实限制寻找3个可能的解决方案")
            report.append("   - 挑战至少一个心理限制")
        
        # 4. 下一步行动
        report.append("\n\n🚀 下一步行动（本周）")
        report.append("-" * 40)
        report.append("1. 选择一个最明显的舒适区迹象，开始一个小项目")
        report.append("2. 针对一个方向线索，进行30分钟的探索研究")
        report.append("3. 挑战一个你认为的限制，看看是否真的存在")
        report.append("4. 记录每天的能量峰值和低谷时间")
        
        return "\n".join(report)
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        """执行诊断"""
        try:
            print("🔍 启动个人方向与舒适区诊断...\n")
            
            # 收集用户输入
            responses = self.collect_inputs()
            
            # 分析回答
            analysis = self.analyze_responses(responses)
            
            # 生成报告
            report = self.generate_report(responses, analysis)
            
            # 保存结果
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"personal_direction_diagnostic_{timestamp}.txt"
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(report)
            
            print("\n" + "=" * 60)
            print("✅ 诊断完成！")
            print(f"报告已保存至: {filename}")
            print("=" * 60)
            
            # 显示关键洞察
            print("\n🔑 关键洞察:")
            for insight_type, insights in analysis.items():
                if insights:
                    print(f"\n{insight_type.replace('_', ' ').title()}:")
                    for insight in insights[:2]:  # 只显示前2个
                        print(f"  • {insight}")
            
            return {
                "success": True,
                "report_file": filename,
                "responses_summary": {k: len(v) for k, v in responses.items()},
                "key_insights": {k: v[:2] for k, v in analysis.items() if v}
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


# 工具定义
class PersonalDirectionDiagnosticTool:
    name = "personal_direction_diagnostic"
    description = "通过结构化输入帮助用户清晰自己的方向和舒适区"
    parameters = {
        "type": "object",
        "properties": {},
        "required": []
    }
    
    @staticmethod
    def execute(**kwargs):
        diagnostic = PersonalDirectionDiagnostic()
        return diagnostic.execute(**kwargs)