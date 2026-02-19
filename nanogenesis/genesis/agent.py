"""
NanoGenesis 主类 - 整合所有核心组件 (Unified)
"""

import sys
import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging
import json

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
        memory: SQLiteMemoryStore,
        session_manager: SessionManager,
        mission_manager: MissionManager, # Injected
        scheduler: AgencyScheduler,
        cognition: CognitiveProcessor,
        trust_anchor: TrustAnchorManager,
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
        
        logger.debug(f"✓ NanoGenesis 2.0 Agent Assembled")
        self._history_loaded = False
    
    async def process(
        self,
        user_input: str,
        user_context: Optional[str] = None,
        problem_type: str = "general",
        step_callback: Optional[Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        处理用户输入（单脑架构 + 纯粹元认知协议 + 流式执行）
        
        Refactored for "Body Swap":
        - 移除 [ACQUISITION_PLAN] 等硬编码分支
        - 启用 AdaptiveLearner 自适应
        - 启用 Loop 直接工具调用
        """
        import time
        process_start_time = time.time()
        
        # Load compressed history (Long-term memory)
        if hasattr(self, "_history_loaded") and not self._history_loaded:
             if hasattr(self.context, "load_compressed_history"):
                 await self.context.load_compressed_history()
             self._history_loaded = True
        
        # 0. 准备基底 Prompt (Persona)
        base_prompt = ""
        if self.adaptive_learner:
            base_prompt = self.adaptive_learner.generate_adaptive_prompt()
        else:
            base_prompt = self.context.system_prompt
            
        if self.context.get_history_length() == 0:
            if await self.session_manager.restore_last_session():
                history = await self.session_manager.get_full_history()
                for item in history:
                    role = MessageRole.USER if item['role'] == 'user' else MessageRole.ASSISTANT
                    # Skip tool outputs for now or handle them if needed, mostly we need the conversation flow
                    self.context.add_to_history(Message(role=role, content=item['content']))
                logger.info(f"🧠 Session Hydrated: {len(history)} turns loaded from SQLite")
            else:
                 logger.info(f"✨ New Session Started: {self.session_manager.session_id}")

        # --- Genesis Triad Pipeline ---
        
        # --- Ouroboros Loop (The Navigator) ---
        MAX_RETRIES = 3
        MAX_DAISY_CHAIN = 5
        execution_history = []
        final_response = None
        final_metrics = None
        final_success = False
        final_optimization_info = {}

        loop_count = 0
        error_count = 0
        current_input = user_input
        accumulated_response = ""
        
        while loop_count < MAX_DAISY_CHAIN:
            loop_count += 1
            logger.info(f"🔄 Ouroboros Loop: Iteration {loop_count} (Errors: {error_count})")
            
            # 1. 洞察阶段 (Awareness Phase)
            if loop_count == 1:
                # Delegate to Cognitive Processor
                oracle_output = await self.cognition.awareness_phase(current_input)
                self.reasoning_log.append({
                    "timestamp": time.time(),
                    "stage": "AWARENESS",
                    "content": oracle_output
                })
                logger.info(f"✓ 洞察完成: {oracle_output.get('core_intent', 'Unknown')}")
            
            # 2. 战略阶段 (Strategy Phase)
            current_context = user_context or ""
            
            # [Fix Amnesia] Inject Conversation History into Strategy Context
            if self.context.get_history_length() > 0:
                history_text = "\n【近期对话历史 (Recent Conversation)】\n"
                # Access _message_history directly or add a getter. 
                # Since we are inside Agent which owns Context, we can iterate.
                # Take last 15 messages to provide sufficient context.
                recent_msgs = self.context._message_history[-15:]
                for msg in recent_msgs:
                    role_str = "User" if msg.role == MessageRole.USER else "Assistant"
                    history_text += f"- {role_str}: {msg.content[:200]}...\n" # Truncate long messages
                current_context += history_text

            if execution_history:
                current_context += f"\n\n[Previous Execution Failures]:\n{json.dumps(execution_history, indent=2, ensure_ascii=False)}"
            
            # --- PRUDENT COGNITION (Perception Layer) ---
            # Phase 1.5: World Model Snapshot
            # Run fast local checks before planning
            from genesis.core.capability import CapabilityScanner
            from genesis.core.entropy import EntropyMonitor
            
            # Lazy init monitor with higher tolerance (Relaxed Mode)
            if not hasattr(self, 'entropy_monitor'):
                self.entropy_monitor = EntropyMonitor(window_size=6)
                
            world_model_snapshot = CapabilityScanner.scan()
            
            # --- ENTROPY CHECK (Loop Breaker) ---
            # Capture current state vector: (LastOutput + CWD + ActiveMission)
            # Use oracle_output or last_tool_result as proxy for output state
            last_tool_out = str(oracle_output) # Using Oracle's view of recent history
            cwd = world_model_snapshot.get('cwd', 'unknown') # CapabilityScanner doesn't return CWD yet? 
            # Actually, let's use a simpler proxy: The concatenation of recent tool outputs from history
            recent_tool_out = ""
            if execution_history:
                 recent_tool_out = str(execution_history[-1])
            
            active_mission_id = "root"
            if hasattr(self, 'mission_manager'):
                 am = self.mission_manager.get_active_mission()
                 if am: active_mission_id = am.id
                 
            self.entropy_monitor.capture(recent_tool_out, cwd, active_mission_id)
            
            # --- DYNAMIC ENTROPY (Soft Interrupt) ---
            # Instead of returning, we gather the signal and inject it into cognition
            entropy_analysis = self.entropy_monitor.analyze_entropy()
            if entropy_analysis.get('status') == 'stagnant':
                logger.warning(f"⚠️ High Entropy Detected: {entropy_analysis}")

            # --- MISSION CONTEXT TREE INTEGRATION ---
            # Ensure Active Mission Exists
            mission_lineage = []
            active_mission = None
            if hasattr(self, 'mission_manager'):
                active_mission = self.mission_manager.get_active_mission()
                if not active_mission:
                    # Auto-create Root Mission for current intent
                    core_intent = oracle_output.get("core_intent", "General Task")
                    active_mission = self.mission_manager.create_mission(core_intent)
                    logger.info(f"🌱 Created New Root Mission: {active_mission.objective}")
                
                mission_lineage = self.mission_manager.get_mission_lineage(active_mission.id)

            # Retrieve Active Jobs (Async System)
            active_jobs = []
            if hasattr(self, 'tools'):
                shell_tool = self.tools.get('shell')
                if shell_tool and hasattr(shell_tool, 'job_manager') and shell_tool.job_manager:
                    active_jobs = shell_tool.job_manager.list_jobs(active_only=True)

            # Delegate to Cognitive Processor
            step_callback("strategy", "制定战略...")
            strategic_blueprint = await self.cognition.strategy_phase(
                user_input=current_input, 
                oracle_output=oracle_output, 
                user_context=current_context,
                adaptive_stats=self.adaptive_learner.get_stats() if self.adaptive_learner else {},
                active_mission=active_mission,
                mission_lineage=mission_lineage,
                world_model=world_model_snapshot, # Inject World Model
                active_jobs=active_jobs, # Inject Active Jobs
                entropy_analysis=entropy_analysis # Inject Entropy Signal
            )
            
            self.reasoning_log.append({
                "timestamp": time.time(),
                "stage": "STRATEGY",
                "content": strategic_blueprint
            })
            
            # --- Clarification Protocol (The Short Circuit) ---
            if "[CLARIFICATION_REQUIRED]" in strategic_blueprint:
                logger.info("⚠️ 战略阶段请求澄清，中断执行")
                return {
                    'response': accumulated_response + ("\n\n" if accumulated_response else "") + strategic_blueprint, 
                    'metrics': None,
                    'success': True, 
                    'optimization_info': {'status': 'clarification_requested'}
                }

            logger.info("✓ 战略蓝图已生成")
            
            # 3. 执行阶段 (Execution Phase)
            self.context.update_system_prompt(f"{base_prompt}\n\n{strategic_blueprint}")
            self.loop.provider = self.cloud_provider
            
            try:
                # 让 Loop 处理思考、调用工具、再思考、最终回复
                response, metrics = await self.loop.run(
                    user_input=current_input,
                    step_callback=step_callback,
                    user_context=user_context,
                    raw_memory=oracle_output.get("memory_pull", []),
                    **kwargs
                )
                
                final_metrics = metrics
                final_success = metrics.success
                final_optimization_info = self._check_and_optimize() if self.enable_optimization else {}
                
                if metrics.success:
                    # 0. Check for Cognitive Escalation (Strategic Interrupt)
                    if "[STRATEGIC_INTERRUPT_SIGNAL]" in response:
                        logger.warning(f"🔄 Strategic Interrupt Received: {response}")
                        # Force loop back to Strategy Phase
                        # Clean signal for context
                        clean_msg = response.replace("[STRATEGIC_INTERRUPT_SIGNAL]", "").strip()
                        execution_history.append(f"ESCALATION: {clean_msg}")
                        accumulated_response += f"\n\n[ESCALATION] {clean_msg}\n\n"
                        error_count = 0 # Reset error count as this is a controlled escalation
                        continue
                    
                    # 1. Check Tool Calls (Preferred)
                    next_instruction = None
                    if metrics.tool_calls:
                        for tc in metrics.tool_calls:
                            if tc['function']['name'] == 'chain_next':
                                try:
                                    args = json.loads(tc['function']['arguments'])
                                    next_instruction = args.get('instruction')
                                    logger.info(f"🔗 Daisy Chain Triggered via Tool: {next_instruction}")
                                    break
                                except:
                                    pass
                    
                    # 2. Check Text Regex (Legacy Fallback)
                    if not next_instruction and ">> NEXT:" in response:
                        import re
                        match = re.search(r">> NEXT:\s*(.+)", response)
                        if match:
                            next_instruction = match.group(1).strip()
                            logger.info(f"🔗 Daisy Chain Triggered via Text: {next_instruction}")

                    if next_instruction:
                        # Append to accumulator
                        accumulated_response += response + "\n\n---\n\n"
                        
                        # Update Input for next loop
                        current_input = next_instruction
                        execution_history = [] # Clear history as previous step succeeded
                        error_count = 0 # Reset error count for new task
                        continue
                    
                    # Mission Accomplished (No chain)
                    accumulated_response += response
                    logger.info("✓ Ouroboros Loop: Mission Accomplished")
                    break
                    
                else:
                    error_count += 1
                    logger.warning(f"⚠️ Ouroboros Loop: Error Attempt {error_count} Failed.")
                    error_entry = f"Attempt {error_count} Failed. Last output: {response[-200:] if response else 'No response'}"
                    execution_history.append(error_entry)
                    
                    if error_count >= MAX_RETRIES:
                        accumulated_response += response or "Error: Max retries exceeded."
                        logger.error("❌ Ouroboros Loop: Max Retries Exceeded.")
                        break
            
            except Exception as e:
                logger.error(f"大脑执行严重失败: {e}")
                execution_history.append(str(e))
                error_count += 1
                if error_count >= MAX_RETRIES:
                    return self._error_response(f"System Critical: Cloud Brain Failure - {e}")

        # --- Memory Update: Append current turn to session context ---
        # 必须手动回写到 context，否则下一轮对话会丢失上下文
        self.context.add_to_history(Message(role=MessageRole.USER, content=user_input))
        self.context.add_to_history(Message(role=MessageRole.ASSISTANT, content=response))

        # 3. 记录与学习 (The Evolution)
        optimization_info = {}
        
        # 3.1 自适应学习 (观察交互)
        if self.adaptive_learner:
            # 简单判断用户反馈 (这里假设没有显式反馈，或者从 response 中推断? 
            # 暂时只记录 message 和 response，user_reaction 留给下一轮? 
            # 实际上我们需要独立的 feedback 机制。这里先记录本次交互。)
            self.adaptive_learner.observe_interaction(
                user_message=user_input,
                assistant_response=response
            )
            optimization_info['adaptive_learning'] = 'observed'
            
        # 3.1.5 Dynamic Profile Extraction (New Phase 7)
        if self.profile_evolution:
            # Fire and forget (or await if fast enough)
            # We treat this as part of the cognitive cycle.
            try:
                new_prefs = await self.profile_evolution.extract_dynamic_preferences(user_input)
                if new_prefs:
                    logger.info(f"👤 Detected New Preferences: {new_prefs}")
                    optimization_info['new_preferences'] = new_prefs
            except Exception as e:
                logger.warning(f"Preference extraction failed: {e}")

        self.metrics_history.append(final_metrics)
        self.last_metrics = final_metrics # 为记忆整合提供上下文
        
        # 触发历史记录压缩
        # 触发历史记录压缩
        if self.context.compression_engine:
            try:
                await self.context.compress_history()
            except Exception as e:
                logger.warning(f"压缩失败: {e}")
        
        # 3.2 其它优化器 (保持兼容)
        if self.enable_optimization:
            if self.tool_optimizer and final_metrics:
                self.tool_optimizer.record_sequence(
                    problem_type,
                    final_metrics.tools_used,
                    final_success,
                    {'tokens': final_metrics.total_tokens, 'time': final_metrics.total_time, 'iterations': final_metrics.iterations}
                )
            
            # 使用 AdaptiveLearner 替代旧的 UserProfileEvolution
            # 但为了保持 stats 接口兼容，我们可能需要保留 self.profile_evolution 引用?
            # 暂时让它共存，或者完全替换。鉴于 AdaptiveLearner 更强，我们主要关注它。
            
            # 3.3 记忆整合 (Consolidation) - Delegate to Cognition
            if final_success:
                 await self.cognition.consolidate_memory(user_input, response, final_metrics)
        
        # ═══ 地基层：会话持久化 (Session Persistence) ═══
        # Fix Amnesia: Save turn to SQLite SessionManager
        tools_list = final_metrics.tools_used if final_metrics else []
        await self.session_manager.save_turn(user_input, response, tools_list)
        
        # 4. 锚点信任: 标记响应来源 (Anchored Trust)
        tagged_response = response
        if final_metrics and final_metrics.tools_used:
            # Check if any external tools were used
            external_tools = ['web_search', 'browser']
            used_external = any(t.lower() in external_tools for t in final_metrics.tools_used)
            if used_external:
                from genesis.core.trust_anchor import TrustLevel
                disclaimer = self.trust_anchor.get_disclaimer(TrustLevel.L3_EXTERNAL)
                if disclaimer:
                    tagged_response = f"{response}\n\n{disclaimer}"
            
        return {
            'response': tagged_response,
            'metrics': final_metrics,
            'success': final_success,
            'optimization_info': optimization_info
        }

    # Removed _awareness_phase, _strategy_phase, _consolidate_memory logic as they are now in CognitiveProcessor


    # ═══════════════════════════════════════════════════════════
    # 地基层：对话持久化 (Conversation Persistence)
    # ═══════════════════════════════════════════════════════════
    
    # ═══════════════════════════════════════════════════════════
    # End of Agent
    # ═══════════════════════════════════════════════════════════


    # ═══════════════════════════════════════════════════════════
    # 认知自治 (Cognitive Autonomy)
    # ═══════════════════════════════════════════════════════════

    async def autonomous_step(self, mission) -> str:
        """
        Execute a single autonomous step for a given mission.
        Run by GenesisDaemon in the background.
        """
        logger.info(f"🤖 Creating Autonomous Context for Mission: {mission.objective}")
        
        # 1. Construct Context
        # We need to inform the model about its current mission and status.
        mission_context = f"""
[MISSION_CONTROL_OVERRIDE]
You are running in AUTONOMOUS MODE (Guardian Daemon).
Current Mission Objective: "{mission.objective}"
Mission Status: {mission.status}
Context Snapshot: {json.dumps(mission.context_snapshot, ensure_ascii=False)}

TASK:
1. Review the objective and current context.
2. Decide the NEXT STEP to advance the mission.
3. Execute necessary tools (e.g., read code, run tests, write files).
4. If you need to stop for now, update the context snapshot.
5. DO NOT wait for user input. You ARE the user.
"""
        # 2. Re-use process() but with specific inputs
        # We simulate a "User" prompt that triggers the agent to act.
        trigger_prompt = "Status Report: Resuming mission. What is the next immediate action?"
        
        # 3. Execution
        result = await self.process(
            user_input=trigger_prompt,
            user_context=mission_context,
            problem_type="mission",
            # We don't have a UI callback here, maybe log to file?
            # step_callback=... (optional)
        )
        
        # 4. Update Mission State
        if result['success']:
            # We should update the snapshot with something useful.
            # Maybe the last tool output or the agent's final thought?
            new_snapshot = mission.context_snapshot or {}
            new_snapshot['last_run'] = datetime.datetime.now().isoformat()
            new_snapshot['last_output'] = result['response'][:200]
            
            # TODO: How to persist this back? 
            # The Daemon has the MissionManager. It should handle the update based on result.
            # But here we return a string or dict?
            return result['response']
        else:
            raise Exception(f"Autonomous step failed: {result['response']}")

    async def _memory_replay(self):
        """深度记忆整合 - 记忆回放 (Memory Replay)
        
        每 N 次交互触发一次，回顾最近的 K 条记忆，
        让 LLM 合成跨交互的元模式 (Meta-Pattern)。
        """
        if not self.memory or len(self.memory.memories) < 5:
            return
            
        # 获取最近的 K 条记忆
        k = min(10, len(self.memory.memories))
        recent_memories = self.memory.memories[-k:]
        
        # 构建回顾 Prompt
        memories_text = ""
        for i, mem in enumerate(recent_memories, 1):
            content = mem.get('content', '')[:200]  # Truncate
            memories_text += f"{i}. {content}...\n"
        
        replay_prompt = f"""
You are analyzing patterns across multiple past interactions.

Recent Memories:
{memories_text}

Task:
1. Identify recurring themes or topics (e.g., "User frequently asks about Docker").
2. Note any contradictions or corrections.
3. Synthesize a high-level "Meta-Pattern" that summarizes what you've learned about the user.

Output JSON only:
{{
    "meta_pattern": "one sentence summary of pattern",
    "themes": ["theme1", "theme2"],
    "user_intent": "inferred high-level goal of user"
}}
"""
        try:
            messages = [{"role": "user", "content": replay_prompt}]
            response = await self.cloud_provider.chat(messages=messages)
            
            import json
            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            result = json.loads(content)
            
            # Store meta-pattern as high-level memory
            meta_pattern = result.get("meta_pattern", "")
            if meta_pattern:
                metadata = {
                    "type": "meta_pattern",
                    "themes": result.get("themes", []),
                    "user_intent": result.get("user_intent", "")
                }
                await self.memory.add(f"[META-PATTERN] {meta_pattern}", metadata=metadata)
                logger.info(f"🧠 Meta-Pattern Synthesized: {meta_pattern}")
                
        except Exception as e:
            logger.warning(f"Memory Replay 失败: {e}")
    
    def _infer_solution_type(self, response: str) -> str:
        """推断解决方案类型"""
        response_lower = response.lower()
        
        if any(word in response_lower for word in ['config', 'yml', 'yaml', 'json', 'toml']):
            return 'config'
        elif any(word in response_lower for word in ['code', 'python', 'def ', 'class ']):
            return 'code'
        else:
            return 'unknown'
    
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
