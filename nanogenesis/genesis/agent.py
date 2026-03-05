"""
NanoGenesis 主类 - 整合所有核心组件 (Unified)
"""

import sys
import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging
import json
import asyncio

sys.path.insert(0, str(Path(__file__).parent.parent))

from genesis.core.base import PerformanceMetrics, Message, MessageRole
from genesis.core.registry import ToolRegistry
from genesis.core.loop import AgentLoop
from genesis.core.context import SimpleContextBuilder # Type hinting
from genesis.memory import SQLiteMemoryStore, SessionManager  # Type hinting
from genesis.core.mission import MissionManager # Type hinting
from genesis.core.cognition import CognitiveProcessor # Type hinting
from genesis.core.scheduler import AgencyScheduler # Type hinting
from genesis.core.provider_manager import ProviderRouter # Type hinting

from genesis.core.config import config
from genesis.core.trust_anchor import TrustAnchorManager

from genesis.core.workshops import WorkshopManager
from genesis.core.manager import Manager
from genesis.core.op_executor import OpExecutor

logger = logging.getLogger(__name__)


class NanoGenesis:
    """
    NanoGenesis - 自进化的轻量级智能 Agent (单脑架构版)
    Genesis Core 2.0 Refactored
    """
    
    def __init__(
        self,
        user_id: str,
        config: Any,
        tools: ToolRegistry,
        context: Any,
        provider_router: Any,
        memory: Any = None,
        session_manager: Any = None,
        mission_manager: Any = None,
        scheduler: Any = None,
        cognition: Any = None,
        trust_anchor: Any = None,
        optimization_components: Dict[str, Any] = None,
        max_iterations: int = 10,
        enable_optimization: bool = True
    ):
        """
        初始化 (Dependency Injection)
        Use GenesisFactory to create instances.
        """
        self.user_id = user_id
        self.config = config
        self.tools = tools
        
        # --- PHASE 3: VISUAL CORTEX ---
        # Auto-register VisualTool if not present
        from genesis.tools.visual_tool import VisualTool
        if "visual" not in self.tools:
            self.tools.register(VisualTool())
        
        self.context = context
        self.provider_router = provider_router
        self.cloud_provider = provider_router # Compatibility
        self.memory = memory
        self.session_manager = session_manager
        self.mission_manager = mission_manager
        self.scheduler = scheduler
        self.cognition = cognition
        self.trust_anchor = trust_anchor
        self.max_iterations = max_iterations
        self.enable_optimization = enable_optimization
        
        # Unpack Optimization Components
        self.optimization_components = optimization_components or {}
        self.prompt_optimizer = self.optimization_components.get('prompt_optimizer')
        self.behavior_optimizer = self.optimization_components.get('behavior_optimizer')
        self.tool_optimizer = self.optimization_components.get('tool_optimizer')
        self.profile_evolution = self.optimization_components.get('profile_evolution')
        self.adaptive_learner = self.optimization_components.get('adaptive_learner')

        # Wire up Decision Transparency callback
        self.loop = AgentLoop(
            tools=self.tools,
            context=self.context,
            provider=self.cloud_provider,
            max_iterations=max_iterations
        )
        self.loop.on_tool_call = self._log_tool_reason
        
        # 性能监控 & 日志
        self.metrics_history = []
        self.reasoning_log: list = []

        # --- Genesis V2: Manager + Workshop System ---
        active_provider = getattr(provider_router, 'get_active_provider', lambda: provider_router)()
        self.workshops = WorkshopManager()
        self._v2_executor = OpExecutor(full_registry=self.tools, provider=active_provider)
        self._v2_manager = Manager(
            workshops=self.workshops,
            provider=active_provider,
            registry=self.tools,
        )
        self._v2_manager.set_executor(self._v2_executor)
        logger.debug("✓ Genesis V2 Manager wired")
        # --- End V2 wiring ---

        logger.debug(f"✓ NanoGenesis 2.0 Agent Assembled")
        self._history_loaded = False
    
    async def process(
        self,
        user_input: Union[str, Any], # Supports SensoryPacket
        user_context: Optional[str] = None,
        problem_type: str = "general",
        step_callback: Optional[Any] = None,
        use_v2: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        处理用户输入。

        use_v2=True (default): Genesis V2 路径 — Manager + Workshop + OpExecutor
        use_v2=False:          Legacy V1 路径  — Ouroboros Loop (保留备用)
        """
        if use_v2:
            return await self._process_v2(user_input, step_callback=step_callback)
        # --- Legacy V1 path (extracted to agent_v1.py) ---
        from genesis.agent_v1 import process_v1
        return await process_v1(self, user_input, user_context, problem_type, step_callback, **kwargs)
    def _check_and_optimize(self) -> Dict[str, Any]:
        """Check if self-optimization is needed"""

        if not self.enable_optimization:
            return {}
        # For now, just return basic stats or delegate to components
        return {
            "adaptive_learner": "active" if self.adaptive_learner else "inactive",
            "optimization": "enabled"
        }

    def _error_response(self, error_msg: str) -> Dict[str, Any]:
        """Generate standardized error response"""
        logger.error(error_msg)
        return {
            "response": f"❌ {error_msg}",
            "metrics": None,
            "success": False,
            "optimization_info": {}
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            'total_interactions': len(self.metrics_history),
            'optimization_enabled': self.enable_optimization
        }
        
        if self.metrics_history:
            # Filter out None metrics (from bridged/failed interactions)
            valid_metrics = [m for m in self.metrics_history if m]
            if valid_metrics:
                total_tokens = sum(m.total_tokens for m in valid_metrics)
                total_time = sum(m.total_time for m in valid_metrics)
                success_count = sum(1 for m in valid_metrics if m.success)
                
                stats.update({
                    'avg_tokens': total_tokens / len(valid_metrics),
                    'avg_time': total_time / len(valid_metrics),
                    'success_rate': success_count / len(valid_metrics),
                    'total_tools_used': sum(len(m.tools_used) for m in valid_metrics)
                })
        
        # 优化器统计
        if self.enable_optimization:
            if self.prompt_optimizer:
                stats['prompt_optimizer'] = self.prompt_optimizer.get_stats()
            
            if self.behavior_optimizer:
                stats['behavior_optimizer'] = self.behavior_optimizer.get_stats()
            
            if self.tool_optimizer:
                stats['tool_optimizer'] = self.tool_optimizer.get_stats()
            
            if self.profile_evolution:
                stats['user_profile'] = self.profile_evolution.get_stats()
        
        return stats
    
    def get_optimization_report(self) -> str:
        """生成优化报告"""
        stats = self.get_stats()
        
        lines = [
            "=" * 60,
            "NanoGenesis 优化报告",
            "=" * 60,
            f"\n总交互次数: {stats['total_interactions']}",
        ]
        
        if stats['total_interactions'] > 0:
            lines.extend([
                f"平均 Token: {stats['avg_tokens']:.0f}",
                f"平均耗时: {stats['avg_time']:.2f}s",
                f"成功率: {stats['success_rate']:.1%}",
            ])
        
        if self.enable_optimization:
            lines.append("\n自优化统计:")
            
            if 'prompt_optimizer' in stats:
                po = stats['prompt_optimizer']
                lines.extend([
                    f"\n提示词优化:",
                    f"  - 优化次数: {po['total_optimizations']}",
                    f"  - 采用次数: {po['adopted_count']}",
                    f"  - 平均 Token 节省: {po['avg_token_saved']:.1%}",
                ])
            
            if 'behavior_optimizer' in stats:
                bo = stats['behavior_optimizer']
                lines.extend([
                    f"\n行为优化:",
                    f"  - 策略数量: {bo['total_strategies']}",
                    f"  - 平均成功率: {bo['avg_success_rate']:.1%}",
                    f"  - 总使用次数: {bo['total_uses']}",
                ])
            
            if 'tool_optimizer' in stats:
                to = stats['tool_optimizer']
                lines.extend([
                    f"\n工具优化:",
                    f"  - 问题类型: {to['problem_types']}",
                    f"  - 成功率: {to['success_rate']:.1%}",
                    f"  - 缓存最优序列: {to['cached_optimal']}",
                ])
            
            if 'user_profile' in stats:
                up = stats['user_profile']
                lines.extend([
                    f"\n用户画像:",
                    f"  - 专业领域: {', '.join(up['expertise']) if up['expertise'] else '未知'}",
                    f"  - 偏好工具: {', '.join(up['preferred_tools'][:3]) if up['preferred_tools'] else '未知'}",
                ])
        
        lines.append("=" * 60)
        
        return '\n'.join(lines)
    
    def get_reasoning_log(self) -> list:
        """获取决策推理日志 (Decision Transparency)"""
        return self.reasoning_log

    # ─── Genesis V2 Entry Point ──────────────────────────────────────────────────

    async def _process_v2(self, user_input: Union[str, Any], step_callback: Optional[Any] = None) -> Dict[str, Any]:
        """
        Genesis V2 执行路径。
        路由决策（chat vs task）完全由 Manager._decide_route() 负责，无硬编码分类逻辑。
        """
        import time
        start = time.time()

        # Handle SensoryPacket input for logging
        loggable_input = user_input
        if hasattr(user_input, "text_content"):
            loggable_input = user_input.text_content()
            if hasattr(user_input, "items"):
                # Add attachment note
                count = sum(1 for i in user_input.items if i.type != 'text')
                if count > 0:
                    loggable_input += f" [With {count} attachments]"

        # 提取最近对话上下文（最多 8 条，每条截 200 字）
        recent_context = ""
        try:
            if hasattr(self, "context") and self.context is not None:
                history = self.context.get_history() if hasattr(self.context, "get_history") else []
                if history:
                    lines = []
                    for msg in history[-8:]:
                        role = getattr(msg, "role", "unknown")
                        role_str = role.value if hasattr(role, "value") else str(role)
                        content = getattr(msg, "content", "") or ""
                        if content:
                            lines.append(f"{role_str}: {str(content)[:200]}")
                    recent_context = "\n".join(lines)
        except Exception:
            pass

        # 记录用户消息到对话历史（供下一轮 recent_context 使用）
        try:
            if hasattr(self, "context") and self.context is not None:
                self.context.add_to_history(Message(role=MessageRole.USER, content=loggable_input))
        except Exception:
            pass

        result = await self._v2_manager.process(user_input, step_callback=step_callback, recent_context=recent_context)
        result["elapsed"] = round(time.time() - start, 2)
        result.setdefault("path", "v2")

        pending = self.workshops.stats().get("pending_lessons", 0)
        if pending:
            result["pending_lessons"] = pending
            result["pending_lessons_hint"] = (
                f"有 {pending} 条待审核知识，调用 agent.review_workshop_lessons() 查看"
            )

        # 兼容 web_ui.py 期望的 result['response'] 字段
        if result.get("success"):
            out = result.get("output") or {}
            result["response"] = (
                out.get("summary") if isinstance(out, dict) else str(out)
            ) or "任务已完成"
            logger.info(
                f"✅ V2 complete in {result['elapsed']}s "
                f"(attempts={result.get('attempts', 1)}, "
                f"tokens={result.get('tokens_used', 0)})"
            )
        else:
            result["response"] = result.get("error") or result.get("message") or "任务执行失败"
            logger.warning(
                f"🔴 V2 circuit broken: {result.get('error', 'unknown')} "
                f"(elapsed={result['elapsed']}s)"
            )

        # 记录助手回复到对话历史
        try:
            if hasattr(self, "context") and self.context is not None:
                self.context.add_to_history(Message(role=MessageRole.ASSISTANT, content=result["response"]))
        except Exception:
            pass

        return result

    def review_workshop_lessons(self) -> str:
        """
        返回待审核知识队列的可读摘要。
        用法：print(agent.review_workshop_lessons())
        """
        return self.workshops.format_pending_review()
    
    def clear_reasoning_log(self):
        """清空推理日志"""
        self.reasoning_log = []
    
    def _log_tool_reason(self, tool_name: str, tool_args: dict):
        """记录工具调用原因 (Callback for AgentLoop)"""
        from datetime import datetime
        entry = {
            "timestamp": datetime.now().isoformat(),
            "tool": tool_name,
            "args_summary": str(tool_args)[:100],  # Truncate for readability
        }
        self.reasoning_log.append(entry)
        logger.debug(f"📝 Logged tool call: {tool_name}")
