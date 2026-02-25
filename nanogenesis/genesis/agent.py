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
                # 选项感知扩展：当用户输入是单字母/数字时，尝试还原其选项上下文
                awareness_input = self._expand_option_input(current_input)
                
                # --- Entity B: Context Packager Phase ---
                # Packager uses read-only tools to scan the environment and gather precise context
                # so the Executor doesn't have to waste tokens probing blindly.
                from genesis.core.packager import ContextPackager
                packager = ContextPackager(self.cloud_provider)
                logger.info("📦 Packager Phase: Scouting environment...")
                
                mission_payload = await packager.build_payload(awareness_input, step_callback)
                logger.info(f"📦 Payload Generated ({len(mission_payload)} chars)")
                
                # 取最近 3 条对话历史，作为 Oracle 的上下文锚点
                # 解决 awareness_phase 为孤立 LLM 调用、无法感知上轮对话的问题
                _recent_ctx = []
                try:
                    if hasattr(self, 'context') and self.context:
                        _hist = self.context.get_history()
                        for _m in _hist[-6:]:  # 最近 6 条（3轮对话）
                            _role = getattr(_m, 'role', None) or (_m.get('role') if isinstance(_m, dict) else None)
                            _content = getattr(_m, 'content', None) or (_m.get('content') if isinstance(_m, dict) else None)
                            if _role in ('user', 'assistant') and _content:
                                _recent_ctx.append({'role': _role, 'content': str(_content)})
                except Exception:
                    pass
                
                # Delegate to Cognitive Processor
                oracle_output = await self.cognition.awareness_phase(awareness_input, recent_context=_recent_ctx)
                self.reasoning_log.append({
                    "timestamp": time.time(),
                    "stage": "AWARENESS",
                    "content": oracle_output
                })
                logger.info(f"✓ 洞察完成: {oracle_output.get('core_intent', 'Unknown')}")

                
                # 1.5 知识存量盘点 (Knowledge Inventory)
                # 在战略阶段前，先激活 LLM 对现有工具/库/命令的记忆
                # 机制：把训练数据里的已知方案物理上放入上下文，而非让 LLM 空白生成
                try:
                    problem_type = oracle_output.get("problem_type", "general")
                    core_intent = oracle_output.get("core_intent", current_input)
                    inventory_prompt = (
                        f"任务类型：{problem_type}\n"
                        f"核心意图：{core_intent}\n\n"
                        f"在提出任何解决方案之前，基于你的训练数据，列举你已知的、"
                        f"用于解决「{core_intent}」类任务的现有工具、命令行程序、成熟库或框架。\n"
                        f"按成熟度从高到低排序，每项一行，格式：[工具名] - [用途]。\n"
                        f"只列举真实存在的工具，不要发明。最多列 6 个。"
                    )
                    inventory_resp = await self.cognition.chat(
                        messages=[{"role": "user", "content": inventory_prompt}]
                    )
                    known_solutions = inventory_resp.content.strip() if inventory_resp else ""
                    oracle_output["known_solutions"] = known_solutions
                    logger.info(f"📚 知识存量盘点完成 ({len(known_solutions)} chars)")
                except Exception as inv_err:
                    logger.warning(f"知识盘点跳过: {inv_err}")
                    oracle_output["known_solutions"] = ""
            
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
            
            # Inject Mission Payload from Entity B into the Executor's context
            if loop_count == 1 and 'mission_payload' in locals():
                current_context += f"\n\n[📦 Context Packager Payload (Entity B)]\n{mission_payload}\n"
            
            # 注入知识存量盘点结果（让 strategy_phase 看到已知工具清单，再生成方案）
            known_solutions = oracle_output.get("known_solutions", "")
            if known_solutions:
                current_context += (
                    f"\n\n[📚 知识存量锚点 - 已知现有工具/方案 (由知识库检索)]\n"
                    f"{known_solutions}\n"
                    f"→ 优先从以上已有工具中选择，非必要不从零编写代码。"
                )
            
            # --- PRUDENT COGNITION (Perception Layer) ---
            # Phase 1.5: World Model Snapshot
            # Run fast local checks before planning
            from genesis.core.capability import CapabilityScanner
            from genesis.core.entropy import EntropyMonitor
            
            # Lazy init monitor with higher tolerance (Relaxed Mode)
            if not hasattr(self, 'entropy_monitor'):
                self.entropy_monitor = EntropyMonitor(window_size=6)
            else:
                # 每次新对话开始时重置，避免携带上次会话的历史误触发 stagnant
                self.entropy_monitor.reset()

                
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
            if step_callback:
                if asyncio.iscoroutinefunction(step_callback):
                    await step_callback("strategy", "制定战略...")
                else:
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
            
            # --- Decode strategy using the Protocol Decoder (No hardcoded strings!) ---
            from genesis.intelligence.protocol_decoder import ProtocolDecoder
            intent_type, intent_content, _ = ProtocolDecoder.decode_strategy(strategic_blueprint)

            # --- Clarification Protocol (The Short Circuit) ---
            if intent_type == "clarification":
                logger.info("⚠️ 战略阶段请求澄清，中断执行")
                return {
                    'response': accumulated_response + ("\n\n" if accumulated_response else "") + intent_content, 
                    'metrics': None,
                    'success': True, 
                    'optimization_info': {'status': 'clarification_requested'}
                }

            # --- 3D Mission Tree: Capability Forge (The Z-Axis Jump) ---
            if intent_type == "forge":
                logger.warning("🔨 [自进化触发] 战略阶段判定缺少关键能力，启动 Z 轴分支 (Capability Forge)")
                
                if hasattr(self, 'mission_manager') and active_mission:
                    # 派生子任务 (Z轴)
                    forge_mission = self.mission_manager.create_mission(
                        objective=f"[FORGE] 获取新能力: \n{intent_content}",
                        parent_id=active_mission.id
                    )
                    active_mission = forge_mission
                    logger.info(f"🌿 成功折叠主线，派生能力锻造子任务: {forge_mission.id}")
                
                # 告知本轮的 A (Executor) 立即去打造这个工具
                current_input = (
                    f"CRITICAL OVERRIDE - CAPABILITY FORGE REQUIRED.\n"
                    f"You must acquire or create a new tool to proceed.\n"
                    f"Forge Details:\n{intent_content}\n"
                    f"Action Required: Use `skill_creator` to write the script OR `github_skill_search` to find it."
                )
                
                # We log it, but do not exit. We let the loop run the forge task.
                accumulated_response += f"\n\n[CAPABILITY_FORGE_INITIATED]\n{intent_content}\n\n"
                
                # Skip the standard loop metrics tracking for this purely internal phase jump
                # (Or let it run normally so the executor handles it). We let it run normally!
                logger.info("✓ 战略蓝图已变轨为能力锻造指令")
            else:
                logger.info("✓ 战略蓝图已生成")
            
            # --- 决策日志：记录本轮锚点选择 ---
            _decision_id = None
            try:
                if hasattr(self, 'mission_manager') and active_mission:
                    _anchor_options = []
                    _known = oracle_output.get("known_solutions", "")
                    if _known:
                        # 从知识存量盘点里提取工具名（每行格式 "[工具名] - 用途"）
                        _anchor_options = [
                            line.strip().split(" - ")[0].strip("[]").strip()
                            for line in _known.splitlines()
                            if line.strip() and " - " in line
                        ][:6]
                    _chosen = strategic_blueprint[:150].replace("\n", " ")
                    _problem_type = oracle_output.get("problem_type", "general")
                    _decision_id = self.mission_manager.log_decision(
                        mission_id=active_mission.id,
                        problem_type=_problem_type,
                        anchor_options=_anchor_options,
                        chosen_anchor=_chosen,
                    )
                    logger.debug(f"📋 决策已记录 (id={_decision_id}, type={_problem_type})")
            except Exception as _dl_err:
                logger.debug(f"决策日志跳过: {_dl_err}")
            

            # 移除毁掉缓存的 ContextualPromptFilter (它会打乱段落，破坏 Prefix Hash)
            # 移除对 system_prompt 的动态注入，保持 system 消息从一开始到最后都是静态的！
            
            # 组合所有的动态上下文，塞给最新的一条 user_context，借此来保持系统提示词干净且强命中。
            final_user_context = f"{user_context}\n\n[战略蓝图]\n{strategic_blueprint}"
            if _decision_id:
                final_user_context += f"\n[记录决策ID: {_decision_id} ({_problem_type})]"
                
            self.loop.provider = self.cloud_provider
            
            try:
                # 让 Loop 处理思考、调用工具、再思考、最终回复
                response, metrics = await self.loop.run(
                    user_input=current_input,
                    step_callback=step_callback,
                    user_context=final_user_context,
                    raw_memory=oracle_output.get("memory_pull", []),
                    **kwargs
                )
                
                final_metrics = metrics
                final_success = metrics.success
                final_optimization_info = self._check_and_optimize() if self.enable_optimization else {}
                
                if metrics.success:
                    # 0. Check for Cognitive Escalation (Strategic Interrupt)
                    exec_intent_type, clean_msg, _ = ProtocolDecoder.decode_execution(response)
                    if exec_intent_type == "interrupt":
                        logger.warning(f"🔄 Strategic Interrupt Received: {clean_msg}")
                        # Force loop back to Strategy Phase
                        # Clean signal for context
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
                    # 决策日志：标记成功
                    if _decision_id is not None and hasattr(self, 'mission_manager'):
                        try: self.mission_manager.update_decision_outcome(_decision_id, 'success')
                        except: pass
                    break
                    
                else:
                    error_count += 1
                    logger.warning(f"⚠️ Ouroboros Loop: Error Attempt {error_count} Failed.")
                    error_entry = f"Attempt {error_count} Failed. Last output: {response[-200:] if response else 'No response'}"
                    execution_history.append(error_entry)
                    
                    if error_count >= MAX_RETRIES:
                        # --- MISSION TREE BACKTRACKING ---
                        # 优先尝试任务树回溯，而非直接终止
                        backtracked = False
                        if response and "[STRATEGIC_INTERRUPT]" in response:
                            interrupt_detail = response.replace("[STRATEGIC_INTERRUPT]", "").strip()
                            
                            # 尝试从任务树爬回父节点
                            if hasattr(self, 'mission_manager'):
                                active_mission = self.mission_manager.get_active_mission()
                                if active_mission and active_mission.parent_id:
                                    logger.warning(f"🔄 任务树回溯：从 '{active_mission.objective[:50]}' 爬回父节点...")
                                    parent_mission = self.mission_manager.backtrack_to_parent(
                                        active_mission.id,
                                        error_summary=interrupt_detail
                                    )
                                    if parent_mission:
                                        # 获取所有已失败子路径（让下次 strategy 排除它们）
                                        failed_paths = self.mission_manager.get_failed_children(parent_mission.id)
                                        failed_hint = ""
                                        if failed_paths:
                                            failed_hint = (
                                                f"\n\n[BACKTRACK CONTEXT] 以下路径已尝试并失败，禁止再次选择：\n"
                                                + "\n".join(f"- {p}" for p in failed_paths)
                                            )
                                        
                                        # 决策日志：标记回溯（这是深度反思的锚点事件）
                                        if _decision_id is not None:
                                            try: self.mission_manager.update_decision_outcome(_decision_id, 'backtracked')
                                            except: pass
                                        # 触发锚点级深度反思（非阻塞）
                                        try:
                                            adaptive = self.optimization_components.get('adaptive_learner') if hasattr(self, 'optimization_components') else None
                                            if adaptive and hasattr(adaptive, 'trigger_anchor_reflection'):
                                                recent_decisions = self.mission_manager.get_recent_decisions(limit=15)
                                                asyncio.create_task(
                                                    adaptive.trigger_anchor_reflection(
                                                        llm_chat_fn=self.cognition.chat,
                                                        decisions=recent_decisions,
                                                    )
                                                )
                                        except Exception as _ar_err:
                                            logger.debug(f"锚点反思跳过: {_ar_err}")
                                        
                                        # 重置循环状态，用父任务目标重试
                                        error_count = 0
                                        current_input = parent_mission.objective + failed_hint
                                        execution_history = []
                                        logger.info(f"↩️ 回溯成功，重试父任务: {parent_mission.objective[:50]}")
                                        backtracked = True
                        
                        if not backtracked:
                            # --- AUTO-DEBRIEF: 无法回溯（根节点），主动汇报协议 ---
                            if response and "[STRATEGIC_INTERRUPT]" in response:
                                logger.warning("🔔 AUTO-DEBRIEF: 根节点中断，生成用户说明")
                                interrupt_detail = response.replace("[STRATEGIC_INTERRUPT]", "").strip()
                                accumulated_response += (
                                    f"⚠️ **执行被自动熔断中断**\n\n"
                                    f"**发生了什么**：我在尝试执行任务时触发了安全熔断机制。具体原因：{interrupt_detail}\n\n"
                                    f"**为什么停下来**：为了避免陷入无意义的重复循环、消耗更多资源，系统主动中断了本次执行。\n\n"
                                    f"**接下来怎么办**：\n"
                                    f"1. 如果是工具连续失败（如权限不足、环境问题），请告知我换一种方法，或者授予必要权限。\n"
                                    f"2. 如果是策略问题，我可以重新制定执行方案。\n"
                                    f"3. 您可以直接告诉我如何继续，我会立即重启执行。"
                                )
                            else:
                                accumulated_response += response or "Error: Max retries exceeded."
                            logger.error("❌ Ouroboros Loop: Max Retries Exceeded.")
                            break
            
            except Exception as e:
                logger.error(f"大脑执行严重失败: {e}")
                execution_history.append(str(e))
                error_count += 1
                if error_count >= MAX_RETRIES:
                    return self._error_response(f"System Critical: Cloud Brain Failure - {e}")

        # --- Phase 3: The Packager (Conscious Wrapper) ---
        # The Stateless Executor has finished. Now we wake up the conversational brain
        # to look at what the executor did, and package it into a nice response for the user.
        logger.info("📦 Entering Packager Phase: Generating conversational response based on raw execution data.")
        
        packager_prompt = (
            "You are the Conversational Packager for NanoGenesis.\n"
            "An unconscious, stateless tool executor has just run a series of actions based on the user's request.\n"
            f"User Original Request: {current_input}\n"
            "--------------------\n"
            "Raw Execution Trace:\n"
            f"{accumulated_response}\n"
            "--------------------\n"
            "Your Task: Read the raw trace above. If the executor succeeded, tell the user what was done in a natural, polite way. "
            "If the executor failed (e.g. error, missing tools), explain to the user what went wrong and ask how they want to proceed. "
            "DO NOT HALLUCINATE TOOL CALLS OR ACTIONS THAT ARE NOT IN THE TRACE."
        )
        
        try:
            # We use cognition.chat to act as the packager, injecting the current conversation memory
            # so it remembers the user profile and previous chats.
            packager_messages = []
            if hasattr(self, 'context') and self.context:
                if hasattr(self.context, 'system_prompt') and self.context.system_prompt:
                     packager_messages.append({'role': 'system', 'content': self.context.system_prompt})
                     
                _hist = self.context.get_history()
                for _m in _hist[-10:]:
                    _role = getattr(_m, 'role', None) or (_m.get('role') if isinstance(_m, dict) else None)
                    _content = getattr(_m, 'content', None) or (_m.get('content') if isinstance(_m, dict) else None)
                    if _role in ('user', 'assistant') and _content:
                         packager_messages.append({'role': _role, 'content': str(_content)})
                         
            packager_messages.append({'role': 'user', 'content': packager_prompt})
            
            if step_callback:
                if asyncio.iscoroutinefunction(step_callback):
                    await step_callback("strategy", "正在整理执行结果并组织语言回答...")
                else:
                    step_callback("strategy", "正在整理执行结果并组织语言回答...")
                    
            packager_response = await self.cognition.chat(messages=packager_messages)
            packaged_output = packager_response.content
        except Exception as e:
            logger.warning(f"Packager failed to format response: {e}")
            # Fallback to the raw trace if the packager fails
            packaged_output = "【执行跟踪日志】\n" + accumulated_response

        # --- Memory Update: Append current turn to session context ---
        # 必须手动回写到 context，否则下一轮对话会丢失上下文
        self.context.add_to_history(Message(role=MessageRole.USER, content=user_input))
        self.context.add_to_history(Message(role=MessageRole.ASSISTANT, content=packaged_output))

        # Re-assign response to packaged_output for the rest of the flow
        response = packaged_output

        # 3. 记录与学习 (The Evolution)
        optimization_info = {}
        
        # --- NEW PHASE: Cognitive Extraction (Sub-Agent insights) & The Handshake Protocol ---
        import re
        extracted_insight = None
        for msg in self.context._message_history:
            # Look for the new async sub-agent reflection format
            # Or the old OPERATIONAL_METRICS format for backwards compatibility
            if msg.role == MessageRole.TOOL and isinstance(msg.content, str):
                if "<reflection>" in msg.content or "<OPERATIONAL_METRICS>" in msg.content:
                    # Look for anything resembling a cognitive insight, wisdom, or summary
                    # Since we relaxed the YAML rule, we use a broader heuristic or just capture the essence
                    # For now, let's catch the specific marker if the sub-agent adhered to it
                    insight_match = re.search(r"(?:cognitive_insight|insight|规律):?\s*([^\n]+)", msg.content, re.IGNORECASE)
                    if insight_match:
                        extracted_insight = insight_match.group(1).strip()
                        
        if extracted_insight and self.adaptive_learner:
            logger.info(f"🧠 Cognitive Insight Detected (Waiting for Handshake): {extracted_insight}")
            # Do NOT add it automatically. Initiate Handshake Protocol!
            handshake_msg = (
                f"\n\n---\n"
                f"🤝 **【系统优化握手请求】**\n"
                f"在刚刚的后台探针任务中，子代理总结出了一条可能提升系统未来效率的规律：\n"
                f"> *\"{extracted_insight}\"*\n"
                f"**您是否允许我将这条规律刻入 Genesis 的潜意识基因库？(回复 是/Y 或 否/N)**"
            )
            response += handshake_msg
            
            # Save the pending insight into the context so the next turn can catch it
            self.context.pending_insight = extracted_insight
                    
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
        
        # ═══ 自适应学习：记录交互 + 按需触发 LLM 反思 ═══
        try:
            adaptive = self.optimization_components.get('adaptive_learner') if hasattr(self, 'optimization_components') else None
            if adaptive:
                adaptive.observe_interaction(
                    user_message=user_input,
                    assistant_response=response[:400],
                )
                # 非阻塞触发反思（每 N 次交互执行一次 LLM 自反思调用）
                if adaptive.should_reflect():
                    asyncio.create_task(
                        adaptive.trigger_reflection(llm_chat_fn=self.cognition.chat)
                    )
        except Exception as _al_err:
            logger.debug(f"AdaptiveLearner 跳过: {_al_err}")
        
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

    async def autonomous_step(self, active_mission: Any) -> Dict[str, Any]:
        """
        Execute a single autonomous step for the daemon.
        Bypasses Awareness Phase (Intent is known).
        Uses Metacognition (Entropy) to prevent loops.
        """
        import time
        import os
        from genesis.core.base import Message, MessageRole
        # from genesis.core.entropy import EntropyMonitor # Already imported
        
        logger.info(f"🤖 Autonomous Step for Mission: {active_mission.objective}")
        
        # 0. Setup
        start_time = time.time()
        cwd = os.getcwd()
        
        # 1. World Model Scan
        from genesis.core.capability import CapabilityScanner
        world_model_snapshot = CapabilityScanner.scan()
        
        # 2. Entropy Check
        # Lazy init monitor if not present (simulating process() behavior)
        if not hasattr(self, 'entropy_monitor'):
             from genesis.core.entropy import EntropyMonitor
             self.entropy_monitor = EntropyMonitor(window_size=6)
        else:
             self.entropy_monitor.reset()  # 新请求，重置熵历史

        # Capture previous state (if any) - actually we capture AFTER execution usually, 
        # but here we capture the 'before' state or result of 'previous' step.
        # Let's rely on standard capture at end of loop.
        
        entropy_analysis = self.entropy_monitor.analyze_entropy()
        if entropy_analysis.get('status') == 'stagnant':
            logger.warning(f"⚠️ Guardian: High Entropy Detected: {entropy_analysis}")
            
        # 3. Strategy Phase (The Brain)
        # We need to construct a 'user_input' that represents the current state/goal
        # Since there is no user, the 'problem' is the Mission Objective + Last Status
        
        last_out = "None"
        if self.context.get_history_length() > 0:
             last_out = str(self.context._message_history[-1].content)[:200]
             
        current_input = f"Mission: {active_mission.objective}. Status: {active_mission.status}. Last Output: {last_out}"
        
        # Retrieve Active Jobs for context
        active_jobs = []
        if hasattr(self, 'tools'):
            shell_tool = self.tools.get('shell')
            if shell_tool and hasattr(shell_tool, 'job_manager'):
                active_jobs = shell_tool.job_manager.list_jobs(active_only=True)

        # Build History Text manually
        history_txt = ""
        if self.context.get_history_length() > 0:
             recent = self.context._message_history[-10:]
             for m in recent:
                 role = "User" if m.role == MessageRole.USER else "Assistant"
                 history_txt += f"{role}: {str(m.content)[:100]}\n"

        strategic_plan = await self.cognition.strategy_phase(
            user_input=current_input,
            oracle_output={"core_intent": active_mission.objective}, # Mock Oracle
            user_context=history_txt,
            active_mission=active_mission,
            mission_lineage=[], # Could fetch if needed
            world_model=world_model_snapshot,
            active_jobs=active_jobs,
            entropy_analysis=entropy_analysis
        )
        
        # 4. Execution (Single Turn)
        # We use a simplified loop or just call the LLM directly?
        # We need to ACT (Helper function or direct LLM call?)
        # Let's use the core loop mechanism but restricted to 1 turn if possible, 
        # or just reuse the 'chat' capability.
        # But 'process' does a lot of wiring. 
        # For robustness, we'll manually execute the "Thought -> Act" cycle here.
        
        # 4.1 Ask LLM for Action
        # We supplement the strategic plan into the system prompt or history?
        # Strategy Phase returns a "System Prompt" extension or "Thought"?
        # Actually strategy_phase returns a STRING response from the Strategist Persona.
        # We treat that as the 'Plan'.
        
        prompt = f"""
        [AUTONOMOUS MODE]
        Objective: {active_mission.objective}
        Strategic Plan: {strategic_plan}
        
        Execute the next logical step. Use tools if necessary.
        """
        
        # 4.2 Call LLM (using context pipeline)
        # We leverage context.build_messages to get System Prompt + History + Our Prompt
        messages = await self.context.build_messages(user_input=prompt)
        
        # Add "Active Jobs" context manually if needed, or rely on strategy_plan
        # created above which already included it? 
        # The prompt includes 'strategic_plan' which saw active_jobs.
        
        try:
            # Need to convert internal Messages to Dicts for provider
            provider_messages = []
            for i, msg in enumerate(messages):
                msg_dict = msg.to_dict()
                
                if msg_dict["role"] == "tool":
                    prev_msg = provider_messages[-1] if provider_messages else None
                    is_orphan = True
                    if prev_msg and prev_msg.get("role") == "assistant" and prev_msg.get("tool_calls"):
                        target_id = msg_dict.get("tool_call_id")
                        if target_id and any(tc.get("id") == target_id for tc in prev_msg.get("tool_calls", [])):
                            is_orphan = False
                            
                    if is_orphan:
                        logger.debug(f"Sanitizing orphaned tool payload {msg_dict.get('tool_call_id', 'unknown')} -> user")
                        msg_dict["role"] = "user"
                        msg_dict["content"] = f"[System Observation (Tool Result)]:\n{msg_dict.get('content', '')}"
                        if "tool_call_id" in msg_dict: del msg_dict["tool_call_id"]
                        if "name" in msg_dict: del msg_dict["name"]
                        
                provider_messages.append(msg_dict)
            
            response = await self.provider_router.chat_with_failover(
                messages=provider_messages,
                tools=self.tools.get_definitions(),
                model=None
            )
            
            # 4.3 Handle Response (Tool Call or Text)
            # Log raw response
            self.context.add_to_history(Message(role=MessageRole.ASSISTANT, content=response.content or ""))
            
            # Handle Tools
            tool_outputs = []
            if getattr(response, 'tool_calls', None):
                for tool_call in response.tool_calls:
                    # ToolCall object from base.py is flat: id, name, arguments
                    t_name = tool_call.name
                    t_args = tool_call.arguments
                    if isinstance(t_args, str):
                        import json
                        try: t_args = json.loads(t_args)
                        except: pass
                        
                    logger.info(f"🛠️ Guardian Executing: {t_name} {t_args}")
                    
                    tool_instance = self.tools.get(t_name)
                    if tool_instance:
                        try:
                            result = await tool_instance.execute(**t_args)
                        except Exception as e:
                            result = f"Error: {e}"
                    else:
                        result = f"Error: Tool {t_name} not found"
                        
                    tool_outputs.append(f"Tool {t_name} result: {result}")
                    
                    # Add to history
                    self.context.add_to_history(Message(role=MessageRole.TOOL, content=str(result), tool_call_id=tool_call.id))
                    
                    # Capture Entropy
                    self.entropy_monitor.capture(str(result), cwd, active_mission.id)
            
            return {
                "status": "success",
                "output": response.content,
                "tools_executed": len(tool_outputs)
            }
            
        except Exception as e:
            logger.error(f"Guardian Step Failed: {e}")
            return {"status": "error", "error": str(e)}

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
    
    def _expand_option_input(self, user_input: str) -> str:
        """
        选项感知扩展器 (Option Context Expander)

        当用户输入是单字母/数字（如 'c'、'2'）时，检查最近的 assistant 消息
        是否包含结构化选项菜单（选项A / 选项B / **A:** 等格式）。
        如果是，则在 user_input 前面拼入选项上下文，让 awareness_phase 能正确解析。

        非选项回复场景不受影响（返回原 user_input）。
        """
        stripped = user_input.strip()
        # 只对极短的回复（1-2个字符）做扩展
        if len(stripped) > 2:
            return user_input

        option_char = stripped.lower()
        is_option_like = (
            (len(option_char) == 1 and option_char in 'abcde12345')
            or option_char in ('a', 'b', 'c', 'd', 'e', '1', '2', '3', '4', '5')
        )
        if not is_option_like:
            return user_input

        # 从 context 里找最近的 assistant 消息
        last_assistant_msg = ""
        try:
            if hasattr(self, 'context') and self.context:
                history = self.context.get_history()  # 返回 Message 列表
                for msg in reversed(history):
                    role = getattr(msg, 'role', None) or (msg.get('role') if isinstance(msg, dict) else None)
                    content = getattr(msg, 'content', None) or (msg.get('content') if isinstance(msg, dict) else None)
                    if role == 'assistant' and content:
                        last_assistant_msg = content
                        break
        except Exception:
            return user_input

        # 检查是否包含选项菜单关键词
        menu_signals = ['选项A', '选项B', '选项C', '**A:', '**B:', '**C:', '**1.', '**2.', '**3.', 'option a', 'option b']
        has_menu = any(sig.lower() in last_assistant_msg.lower() for sig in menu_signals)
        if not has_menu:
            return user_input

        # 拼入上下文
        expanded = (
            f"[上下文：你在上一条回复中给出了以下选项菜单]\n"
            f"{last_assistant_msg[:800]}\n\n"
            f"[用户回复：{user_input.strip().upper()}]\n"
            f"用户选择了选项 {user_input.strip().upper()}，请按该选项执行。"
        )
        logger.debug(f"🔧 选项感知：扩展输入 '{user_input}' → 包含菜单上下文")
        return expanded

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
