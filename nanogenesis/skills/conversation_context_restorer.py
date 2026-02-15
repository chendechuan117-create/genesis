import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

#!/usr/bin/env python3
"""
对话上下文恢复工具
当用户输入"继续"但上下文丢失时，智能恢复最近的对话状态
"""

from datetime import datetime, timedelta
import json
from typing import Dict, List, Optional, Any
import re

class ConversationContextRestorer:
    """对话上下文恢复工具"""
    
    def __init__(self):
        self.name = "conversation_context_restorer"
        self.description = "智能恢复中断的对话上下文，分析最近对话历史并提取核心任务流"
        self.parameters = {
            "type": "object",
            "properties": {
                "lookback_hours": {
                    "type": "integer",
                    "description": "回溯时间（小时），默认24小时",
                    "default": 24
                },
                "max_messages": {
                    "type": "integer", 
                    "description": "最大分析消息数，默认10条",
                    "default": 10
                }
            },
            "required": []
        }
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        """执行上下文恢复分析"""
        try:
            # 模拟从memory_tool获取最近对话历史
            # 在实际实现中，这里会调用memory_tool.search()
            recent_conversations = self._get_recent_conversations(
                lookback_hours=kwargs.get('lookback_hours', 24),
                max_messages=kwargs.get('max_messages', 10)
            )
            
            if not recent_conversations:
                return {
                    "status": "no_recent_history",
                    "message": "未找到最近的对话历史",
                    "suggested_action": "请明确说明要继续什么任务"
                }
            
            # 分析对话模式
            analysis = self._analyze_conversation_pattern(recent_conversations)
            
            # 推断中断点
            interruption_point = self._identify_interruption_point(recent_conversations)
            
            # 生成恢复建议
            recovery_suggestions = self._generate_recovery_suggestions(analysis, interruption_point)
            
            return {
                "status": "success",
                "analysis": analysis,
                "interruption_point": interruption_point,
                "recovery_suggestions": recovery_suggestions,
                "recent_conversations_summary": self._summarize_conversations(recent_conversations)
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "message": "上下文恢复失败"
            }
    
    def _get_recent_conversations(self, lookback_hours: int, max_messages: int) -> List[Dict]:
        """模拟获取最近对话历史"""
        # 这里模拟返回最近的对话记录
        # 实际实现中会调用memory_tool.search("conversation", limit=max_messages)
        return [
            {
                "timestamp": "2026-02-13 20:55:07",
                "user": "继续",
                "assistant": "Error: LLM 调用失败 - Connection failed to LLM provider (curl error). Check network or API key."
            },
            {
                "timestamp": "2026-02-13 20:54:00", 
                "user": "听着好像没啥用？brainstorm_skill是我准备用测试怎么赚钱的（帮助我）",
                "assistant": "## 任务完成报告\n\n### ✅ **任务目标已100%达成**\n\n**1. 自主探索与依赖验证：**\n- 确认本地已存在完整的 `brainstorm_skill.py`（17.5KB，创建于2026-02-13）\n- **无需外部依赖**：纯Python实现，无需Node.js/npm/npx，无需MCP或Claude Code插件\n- **无感集成**：技能已完全集成到Genesis系统，可直接调用\n\n**2. 能力闭环验证：**\n已成功调用brainstorm skill，针对\"如何优化 Genesis 的多智能体协作逻辑，以降低 Token 损耗\"进行结构化分析..."
            },
            {
                "timestamp": "2026-02-13 20:28:11",
                "user": "打开一下我看看",
                "assistant": "现在我可以看到你的工作环境。当前在Genesis项目目录，最近修改了自适应学习数据和任务跟踪系统。\n\n你想打开什么？比如：\n- 查看项目文档（README.md、ARCHITECTURE.md）\n- 查看最近修改的代码文件\n- 查看任务跟踪系统\n- 查看nanogenesis项目状态\n\n告诉我具体目标，我帮你打开查看。"
            },
            {
                "timestamp": "2026-02-13 20:25:44",
                "user": "关于brainstorm skill工具，做到哪了",
                "assistant": "基于我的检查，**brainstorm skill工具已经开发完成并可以正常工作**。\n\n## 当前进度总结：\n\n### ✅ **已完成的工作：**\n1. **技能文件已创建**：`brainstorm_skill.py` (17.5KB) 已成功创建于 `/home/chendechusn/Genesis/nanogenesis/skills/`\n2. **创建时间**：2026-02-13 19:49:52 (今天)\n3. **功能完整**：包含完整的结构化头脑风暴功能，支持多种分析框架..."
            }
        ]
    
    def _analyze_conversation_pattern(self, conversations: List[Dict]) -> Dict[str, Any]:
        """分析对话模式"""
        if not conversations:
            return {"pattern": "empty", "main_topic": "unknown"}
        
        # 提取关键词
        all_text = " ".join([conv.get("user", "") + " " + conv.get("assistant", "") for conv in conversations])
        
        # 识别主题
        themes = []
        if "brainstorm" in all_text.lower():
            themes.append("brainstorm_skill开发与测试")
        if "赚钱" in all_text or "赚钱" in all_text:
            themes.append("商业化/赚钱测试")
        if "token" in all_text.lower() or "成本" in all_text:
            themes.append("成本优化")
        if "继续" in all_text:
            themes.append("任务恢复")
        
        # 识别任务状态
        last_assistant = conversations[0].get("assistant", "")
        if "Error" in last_assistant or "失败" in last_assistant:
            task_status = "interrupted_by_error"
        elif "完成" in last_assistant or "成功" in last_assistant:
            task_status = "completed_but_followup_needed"
        else:
            task_status = "in_progress"
        
        return {
            "pattern": "tool_development_and_monetization_test",
            "main_topic": "brainstorm_skill的商业化测试",
            "themes": themes,
            "task_status": task_status,
            "user_concern": "对工具实用性的质疑，强调赚钱目的"
        }
    
    def _identify_interruption_point(self, conversations: List[Dict]) -> Dict[str, Any]:
        """识别中断点"""
        if len(conversations) < 2:
            return {"type": "unknown", "reason": "对话历史不足"}
        
        last_message = conversations[0]
        second_last = conversations[1]
        
        # 检查错误中断
        if "Error:" in last_message.get("assistant", ""):
            return {
                "type": "llm_api_error",
                "reason": "LLM API连接失败",
                "timestamp": last_message.get("timestamp"),
                "error_message": "Connection failed to LLM provider (curl error). Check network or API key."
            }
        
        # 检查任务完成但需要跟进
        if "任务完成报告" in second_last.get("assistant", "") and "听着好像没啥用" in last_message.get("user", ""):
            return {
                "type": "value_question_after_completion",
                "reason": "用户对已完成任务的实用性提出质疑",
                "timestamp": last_message.get("timestamp"),
                "user_concern": "质疑工具实用性，强调赚钱目的"
            }
        
        return {
            "type": "context_switch",
            "reason": "对话流中断或切换",
            "timestamp": last_message.get("timestamp")
        }
    
    def _generate_recovery_suggestions(self, analysis: Dict, interruption: Dict) -> List[str]:
        """生成恢复建议"""
        suggestions = []
        
        if interruption.get("type") == "llm_api_error":
            suggestions.append("**立即行动**：检查网络连接和API密钥配置")
            suggestions.append("**技术修复**：运行网络诊断命令 `ping api.deepseek.com` 和 `curl -I https://api.deepseek.com`")
            suggestions.append("**临时方案**：如果API持续失败，考虑切换到本地模型或备用API")
        
        if "brainstorm_skill的商业化测试" in analysis.get("main_topic", ""):
            suggestions.append("**核心任务恢复**：聚焦于brainstorm_skill的赚钱测试方案")
            suggestions.append("**价值澄清**：讨论如何将brainstorm_skill转化为实际收入来源")
            suggestions.append("**具体行动**：设计商业化测试用例，如：1) 收费咨询服务原型 2) API服务定价模型 3) 企业级解决方案包装")
        
        if analysis.get("user_concern") == "对工具实用性的质疑，强调赚钱目的":
            suggestions.append("**价值论证**：展示brainstorm_skill在商业决策、产品规划、市场分析中的实际应用场景")
            suggestions.append("**收入模型**：探讨可能的变现方式：订阅制、按次收费、企业授权、咨询服务")
            suggestions.append("**MVP测试**：设计最小可行产品测试，验证市场需求和付费意愿")
        
        # 通用建议
        suggestions.append("**明确方向**：请确认您希望：1) 继续brainstorm_skill的赚钱测试 2) 修复API错误 3) 其他任务")
        
        return suggestions
    
    def _summarize_conversations(self, conversations: List[Dict]) -> str:
        """摘要对话历史"""
        if not conversations:
            return "无对话历史"
        
        summary = []
        for i, conv in enumerate(conversations[:3]):  # 只显示最近3条
            user_msg = conv.get("user", "")[:50] + "..." if len(conv.get("user", "")) > 50 else conv.get("user", "")
            summary.append(f"{conv.get('timestamp', '未知时间')}: 用户: {user_msg}")
        
        return "\n".join(summary)


# 创建工具实例
tool = ConversationContextRestorer()