"""
NanoGenesis 主类 - 整合所有核心组件 (Unified)
"""

import sys
import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging

sys.path.insert(0, str(Path(__file__).parent))

from core.base import PerformanceMetrics, Message, MessageRole
from core.registry import ToolRegistry
from core.loop import AgentLoop
from core.context import SimpleContextBuilder
from core.memory import QmdMemory
from core.scheduler import AgencyScheduler
from core.provider import LiteLLMProvider, NativeHTTPProvider, LITELLM_AVAILABLE
from core.provider_local import OllamaProvider  # Re-imported for Embeddings only
from core.config import config
from core.trust_anchor import TrustAnchorManager
from tools.chain_next_tool import ChainNextTool

from optimization.prompt_optimizer import PromptOptimizer
from optimization.behavior_optimizer import BehaviorOptimizer
from optimization.tool_optimizer import ToolUsageOptimizer
from optimization.profile_evolution import UserProfileEvolution
from intelligence.adaptive_learner import AdaptiveLearner

logger = logging.getLogger(__name__)


class NanoGenesis:
    """
    NanoGenesis - 自进化的轻量级智能 Agent (单脑架构版)
    
    核心特性：
    1. 单脑架构 (Unified Brain): DeepSeek V3 全权接管
    2. 省 Token - 多层缓存优化 + 提示词自优化 (Compression Protocol)
    3. 能干活 - 工具 + 智能诊断 + 策略学习
    4. 会自我迭代 - 四重自优化机制
    5. 向量记忆 (Vector Memory) - 语义检索
    6. 时间感知 (Time Agency) - 后台调度
    """
    
    def __init__(
        self,
        user_id: str = "default_user",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "deepseek/deepseek-chat",
        gemini_key: Optional[str] = None,
        gemini_url: Optional[str] = None,
        max_iterations: int = 10,
        enable_optimization: bool = True
    ):
        """初始化"""
        self.user_id = user_id
        self.enable_optimization = enable_optimization
        self.config = config
        
        # 1. 核心组件基础
        self.tools = ToolRegistry()
        self.context = SimpleContextBuilder()
        
        # 解析配置
        final_api_key = api_key or self.config.deepseek_api_key
        
        # 2. 云端大脑 (Cloud Brain) - Multi-Provider Support
        self.providers = {}
        self.active_provider_name = 'antigravity' # Default to Antigravity (Gemini 2.5)
        
        # Primary: DeepSeek (NativeHTTP)
        if final_api_key:
            logger.info("初始化 Primary Provider: DeepSeek (NativeHTTP)")
            self.providers['deepseek'] = NativeHTTPProvider(
                api_key=final_api_key,
                base_url=base_url,
                default_model=model
            )
        elif LITELLM_AVAILABLE:
            logger.info("初始化 Primary Provider: LiteLLM")
            self.providers['deepseek'] = LiteLLMProvider(
                api_key=api_key,
                base_url=base_url,
                default_model=model
            )
        else:
            logger.warning("无 Primary Key，使用 MockLLMProvider")
            from core.provider import MockLLMProvider
            self.providers['deepseek'] = MockLLMProvider()

        # Backup: Gemini (via Proxy)
        final_gemini_key = gemini_key or getattr(self.config, 'gemini_api_key', None)
        final_gemini_url = gemini_url or getattr(self.config, 'gemini_base_url', "http://127.0.0.1:8045/v1")
        
        if final_gemini_key:
            logger.info(f"初始化 Backup Provider: Gemini (Proxy at {final_gemini_url})")
            self.providers['gemini'] = NativeHTTPProvider(
                api_key=final_gemini_key,
                base_url=final_gemini_url,
                default_model="gemini-1.5-flash" 
            )
        
        # Extension: Antigravity Tools (Surgical Insertion)
        logger.info("初始化 Extension Provider: Antigravity Tools")
        self.providers['antigravity'] = NativeHTTPProvider(
            api_key="sk-8bf1cea5032d4ec0bfd421630814bff0",
            base_url="http://127.0.0.1:8045/v1",
            default_model="gemini-2.5-flash"
        )
        
        # Set initial provider
        self.cloud_provider = self.providers[self.active_provider_name]
        
        # 注入 Provider 到 ContextBuilder (用于压缩)
        self.context.set_provider(self.cloud_provider)

        # 3. 初始化 QMD 记忆 (SQLite + Semantic)
        self.memory = QmdMemory()
        
        # 4. 初始化 Agency 调度器 (Heartbeat)
        self.scheduler = AgencyScheduler(self.tools)
        
        # 5. 默认使用云端大脑初始化 Loop
        self.loop = AgentLoop(
            tools=self.tools,
            context=self.context,
            provider=self.cloud_provider,
            max_iterations=max_iterations
        )
        
        # 5b. Wire up Decision Transparency callback
        self.loop.on_tool_call = self._log_tool_reason
        
        # 6. 自优化组件
        if enable_optimization:
            self.prompt_optimizer = PromptOptimizer(
                provider=self.cloud_provider,
                optimize_interval=50
            )
            self.behavior_optimizer = BehaviorOptimizer(provider=self.cloud_provider)
            self.tool_optimizer = ToolUsageOptimizer()
            
            # Memento Protocol Tool
            self.tools.register(ChainNextTool())
            
            self.profile_evolution = UserProfileEvolution(user_id)
            # 初始化 AdaptiveLearner (OpenClaw-style)
            self.adaptive_learner = AdaptiveLearner(
                 storage_path=self.config.workspace_root / "data" / "adaptive_learning.json"
            )
        else:
            self.prompt_optimizer = None
            self.behavior_optimizer = None
            self.tool_optimizer = None
            self.profile_evolution = None
            self.adaptive_learner = None
        
        # 7. 性能监控
        self.metrics_history = []
        
        # 8. 决策透明度 (Decision Transparency)
        self.reasoning_log: list = []
        
        # 9. 锚点信任 (Anchored Trust)
        self.trust_anchor = TrustAnchorManager()
        
        # 8. 注册工具
        self._register_tools()
        
        # 9. 初始化系统提示词
        self._initialize_system_prompt()
        
        # 10. 加载元认知协议
        self._load_meta_cognition_protocol()
        
        # 11. 加载近期对话记忆 (地基层) — 重启后恢复上下文
        self._load_recent_conversations()
        
        logger.debug(f"✓ NanoGenesis 初始化完成 (单脑架构, 优化: {enable_optimization})")

    def _switch_provider(self, target: str):
        """Switch active provider (e.g., deepseek -> gemini)"""
        if target not in self.providers:
            logger.error(f"Cannot switch to unknown provider: {target}")
            return
            
        logger.warning(f"⚠️ Switching Provider: {self.active_provider_name} -> {target}")
        self.active_provider_name = target
        self.cloud_provider = self.providers[target]
        self.context.set_provider(self.cloud_provider)
        # Also update loop provider if loop exists
        if hasattr(self, 'loop'):
            self.loop.provider = self.cloud_provider

    async def _chat_with_failover(self, messages: List[Dict], **kwargs) -> Any:
        """Wrapper for chat with auto-failover"""
        try:
            return await self.cloud_provider.chat(messages=messages, **kwargs)
        except Exception as e:
            # If primary failed and we have backup
            # Generic Failover Logic
            available = list(self.providers.keys())
            current = self.active_provider_name
            
            # Determine backup candidate
            backup = None
            if current == 'deepseek':
                # Prefer antigravity, then gemini
                if 'antigravity' in self.providers: backup = 'antigravity'
                elif 'gemini' in self.providers: backup = 'gemini'
            elif current in ['antigravity', 'gemini']:
                if 'deepseek' in self.providers: backup = 'deepseek'
            
            if backup:
                logger.error(f"Provider {current} Failed: {e}. Failover -> {backup}")
                self._switch_provider(backup)
                try:
                    return await self.cloud_provider.chat(messages=messages, **kwargs)
                except Exception as e2:
                    logger.error(f"Backup Provider {backup} also failed: {e2}")
                    raise e2
            else:
                raise e

    def _load_meta_cognition_protocol(self):
        """加载元认知协议 (Pure Metacognition)"""
        try:
            # 1. 加载裁决者协议 (Strategist)
            strategist_path = Path(__file__).parent / "intelligence/prompts/pure_metacognition_protocol.txt"
            if strategist_path.exists():
                with open(strategist_path, "r", encoding="utf-8") as f:
                    self.meta_protocol = f.read()
                logger.info("✓ 已加载裁决者协议 (Strategist Protocol)")
            else:
                self.meta_protocol = None
                logger.warning("裁决者协议文件不存在")

            # 2. 加载洞察者协议 (Oracle / Intent Recognition)
            oracle_path = Path(__file__).parent / "intelligence/prompts/intent_recognition.txt"
            if oracle_path.exists():
                with open(oracle_path, "r", encoding="utf-8") as f:
                    self.intent_prompt = f.read()
                logger.info("✓ 已加载洞察者协议 (Oracle Protocol)")
            else:
                self.intent_prompt = None
                logger.warning("洞察者协议文件不存在")
                
        except Exception as e:
            self.meta_protocol = None
            self.intent_prompt = None
            logger.warning(f"加载元认知协议失败: {e}")

    def _register_tools(self):
        """注册所有工具"""
        try:
            from tools.file_tools import (
                ReadFileTool, WriteFileTool,
                AppendFileTool, ListDirectoryTool
            )
            from tools.shell_tool import ShellTool
            from tools.web_tool import WebSearchTool
            from tools.browser_tool import BrowserTool
            from tools.memory_tool import MemoryTool
            from tools.skill_creator_tool import SkillCreatorTool
            from tools.scheduler_tool import SchedulerTool
            
            self.tools.register(ReadFileTool())
            self.tools.register(WriteFileTool())
            self.tools.register(AppendFileTool())
            self.tools.register(ListDirectoryTool())
            self.tools.register(ShellTool(use_sandbox=False))  # Disable Sandbox to allow Host interaction
            self.tools.register(WebSearchTool())
            self.tools.register(BrowserTool())
            self.tools.register(MemoryTool(self.memory))
            self.tools.register(SkillCreatorTool(self.tools))  # Register SkillCreator
            self.tools.register(SchedulerTool(self.scheduler)) # Register SchedulerTool
            
            logger.info(f"✓ 已注册 {len(self.tools)} 个工具")
        except Exception as e:
            logger.warning(f"注册工具时出错: {e}")
            import traceback
            traceback.print_exc()
    
    def _initialize_system_prompt(self):
        """初始化系统提示词"""
        # 1. 基础: 用户画像生成
        if self.enable_optimization and self.profile_evolution:
            adaptive_prompt = self.profile_evolution.generate_adaptive_prompt()
            self.context.update_system_prompt(adaptive_prompt)
            
        # 2. 进阶: 加载历史优化结果 (覆盖画像生成的默认Prompt)
        # 这确保了"吃一堑长一智"——如果系统之前自我优化过，就使用进化后的版本
        if self.enable_optimization and self.prompt_optimizer:
            optimized_prompt = self.prompt_optimizer.get_latest_optimized_prompt()
            if optimized_prompt:
                self.context.update_system_prompt(optimized_prompt)
                logger.info("✓ 已加载自进化后的系统提示词")
        
        # 记录初始提示词
        if self.prompt_optimizer:
            self.prompt_optimizer.current_system_prompt = self.context.system_prompt
    
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
        # 0. 准备基底 Prompt (Persona)
        base_prompt = ""
        if self.adaptive_learner:
            base_prompt = self.adaptive_learner.generate_adaptive_prompt()
        else:
            base_prompt = self.context.system_prompt
            
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
        
        while loop_count < MAX_DAISY_CHAIN:
            loop_count += 1
            logger.info(f"🔄 Ouroboros Loop: Iteration {loop_count} (Errors: {error_count})")
            
            # 1. 洞察阶段 (Awareness Phase) - 仅在第一轮运行
            if loop_count == 1:
                oracle_output = await self._awareness_phase(current_input)
                self.reasoning_log.append({
                    "timestamp": time.time(),
                    "stage": "AWARENESS",
                    "content": oracle_output
                })
                logger.info(f"✓ 洞察完成: {oracle_output.get('core_intent', 'Unknown')}")
            
            # 2. 战略阶段 (Strategy Phase)
            # 将执行历史注入战略上下文
            current_context = user_context or ""
            if execution_history:
                current_context += f"\n\n[Previous Execution Failures]:\n{json.dumps(execution_history, indent=2, ensure_ascii=False)}"
            
            strategic_blueprint = await self._strategy_phase(current_input, oracle_output, current_context)
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
                    # Check for Daisy Chain (Memento Protocol) - Tool Based
                    next_instruction = None
                    
                    # 1. Check Tool Calls (Preferred)
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

        self.metrics_history.append(metrics)
        self.last_metrics = metrics # 为记忆整合提供上下文
        
        # 触发历史记录压缩
        if self.context.compression_engine:
            await self.context.compress_history()
        
        # 3.2 其它优化器 (保持兼容)
        if self.enable_optimization:
            if self.tool_optimizer:
                self.tool_optimizer.record_sequence(
                    problem_type,
                    metrics.tools_used,
                    success,
                    {'tokens': metrics.total_tokens, 'time': metrics.total_time, 'iterations': metrics.iterations}
                )
            
            # 使用 AdaptiveLearner 替代旧的 UserProfileEvolution
            # 但为了保持 stats 接口兼容，我们可能需要保留 self.profile_evolution 引用?
            # 暂时让它共存，或者完全替换。鉴于 AdaptiveLearner 更强，我们主要关注它。
            
            # 3.3 记忆整合 (Consolidation)
            if success:
                # 异步或同步执行? 由于是最后一步，同步await即可
                await self._consolidate_memory(user_input, response)
        
        # ═══ 地基层：无条件持久化对话 ═══
        # 不管评分高低，每次对话都完整保存
        await self._persist_conversation(user_input, response, metrics)
        
        # 4. 锚点信任: 标记响应来源 (Anchored Trust)
        tagged_response = response
        if metrics and metrics.tools_used:
            # Check if any external tools were used
            external_tools = ['web_search', 'browser']
            used_external = any(t.lower() in external_tools for t in metrics.tools_used)
            if used_external:
                from core.trust_anchor import TrustLevel
                disclaimer = self.trust_anchor.get_disclaimer(TrustLevel.L3_EXTERNAL)
                if disclaimer:
                    tagged_response = f"{response}\n\n{disclaimer}"
            
        return {
            'response': tagged_response,
            'metrics': metrics,
            'success': success,
            'optimization_info': optimization_info
        }

    async def _awareness_phase(self, user_input: str) -> Dict[str, Any]:
        """第一人格：洞察者 (The Oracle) - 意图识别与资源扫描"""
        if not self.intent_prompt:
            return {"core_intent": "General Request", "problem_type": "general", "resource_map": {}}
            
        # 填充模板
        prompt = self.intent_prompt.replace("{{user_input}}", user_input)
        
        try:
            # 这是一个轻量级调用，不做 ReAct 循环
            response = await self._chat_with_failover(
                messages=[{"role": "user", "content": prompt}],
                # 尽量让输出为 JSON
                response_format={"type": "json_object"} if "json" in prompt.lower() else None
            )
            
            # 解析 JSON 输出
            import json
            content = response.content
            # 处理可能的 markdown 块
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            result = json.loads(content)
            
            # --- QMD Memory Enrichment ---
            memory_hits = []
            if result.get("memory_keywords"):
                keywords = result["memory_keywords"]
                # 执行记忆拉取
                queries = keywords if isinstance(keywords, list) else [keywords]
                for q in queries:
                    hits = await self.memory.search(q, limit=3)
                    memory_hits.extend(hits)
            
            # 去重并排序
            unique_hits = {h['path']: h for h in memory_hits}.values()
            result["memory_pull"] = sorted(unique_hits, key=lambda x: x['score'], reverse=True)[:5]
            
            # --- Decision Cache Enrichment ---
            decision_hits = []
            for q in (queries if 'queries' in locals() else [user_input]):
                 d_hits = await self.memory.search(q, limit=2, collection="_decisions")
                 decision_hits.extend(d_hits)
            
            unique_decisions = {h['path']: h for h in decision_hits}.values()
            formatted_decisions = []
            for d in unique_decisions:
                import json
                meta = json.loads(d.get('metadata', '{}')) if isinstance(d.get('metadata'), str) else d.get('metadata', {})
                formatted_decisions.append({
                    "insight": meta.get("insight", ""),
                    "outcome": meta.get("outcome", ""),
                    "action": meta.get("action", "")
                })
            result["decision_history"] = formatted_decisions[:3]
            
            return result
        except Exception as e:
            logger.warning(f"洞察阶段失败: {e}")
            return {"core_intent": user_input[:30], "problem_type": "general", "resource_map": {}}

    async def _strategy_phase(self, user_input: str, oracle_output: Dict[str, Any], user_context: str = None) -> str:
        """第二人格：裁决者 (The Strategist) - 元认知战略制定"""
        if not self.meta_protocol:
            return ""
            
        # 填充模板
        tools_desc = []
        for tool in self.tools.get_definitions():
            tools_desc.append(f"- {tool['function']['name']}: {tool['function']['description']}")
        tools_str = "\n".join(tools_desc)
        
        # 格式化决策经验
        decisions = oracle_output.get("decision_history", [])
        dec_str = ""
        if decisions:
            dec_str = "历史相似决策参考：\n"
            for d in decisions:
                dec_str += f"- [经验] {d.get('insight')} (结果: {d.get('outcome')})\n"
        else:
            dec_str = "暂无相关历史决策经验。"

        protocol_filled = self.meta_protocol.replace("{{oracle_output}}", str(oracle_output))\
                                          .replace("{{problem}}", user_input)\
                                          .replace("{{context}}", user_context or "")\
                                          .replace("{{user_profile}}", str(self.adaptive_learner.get_stats() if self.adaptive_learner else {}))\
                                          .replace("{{decision_experience}}", dec_str)\
                                          .replace("{{tools}}", tools_str)
        
        try:
            # 战略制定调用
            response = await self._chat_with_failover(
                messages=[{"role": "user", "content": protocol_filled}]
            )
            return response.content
        except Exception as e:
            logger.warning(f"战略阶段失败: {e}")
            return "Proceed with caution and follow standard ReAct instructions."

    def _error_response(self, msg: str) -> Dict[str, Any]:
        return {
            'response': f"Error: {msg}",
            'metrics': None,
            'success': False,
            'optimization_info': {}
        }
    
    async def _check_and_optimize(self) -> Dict[str, Any]:
        """检查并执行优化"""
        optimization_info = {}
        
        # 1. 提示词优化
        if self.prompt_optimizer and self.prompt_optimizer.should_optimize():
            result = await self.prompt_optimizer.optimize(self.context.system_prompt)
            
            if result and result.adopted:
                # 采用新提示词
                self.context.update_system_prompt(result.new_prompt)
                self.prompt_optimizer.current_system_prompt = result.new_prompt
                
                optimization_info['prompt_optimized'] = {
                    'token_saved': result.improvement['token_saved'],
                    'reason': result.reason
                }
                
                logger.info(f"✓ 提示词已优化: {result.reason}")
        
        # 2. 行为优化（策略库优化）
        if self.behavior_optimizer:
            if len(self.behavior_optimizer.strategies) > 0 and \
               len(self.behavior_optimizer.strategies) % 20 == 0:
                self.behavior_optimizer.optimize_strategies()
                optimization_info['strategies_optimized'] = True
        
        # 3. 用户画像进化
        if self.profile_evolution:
            changes = self.profile_evolution.evolve()
            if changes:
                # 更新系统提示词
                new_prompt = self.profile_evolution.generate_adaptive_prompt()
                self.context.update_system_prompt(new_prompt)
                
                optimization_info['profile_evolved'] = changes
                logger.info(f"✓ 用户画像已进化: {list(changes.keys())}")
        
        return optimization_info

    async def _consolidate_memory(self, user_input: str, response: str):
        """记忆整合协议 (Memory Consolidation Protocol)"""
        if not self.memory:
            return

        # 1. 快速过滤 (Heuristic)
        if len(user_input) < 5 or len(response) < 10:
            return
            
        # 2. 元评价与决策提取 (Meta-Evaluation & Decision Extraction)
        eval_prompt = f"""
Analyze the following interaction to extract a "Decision Event" (AX-Pair).

User Query: {user_input}
Assistant Response: {response}

Tasks:
1. Rate Significance (0-10) based on complexity and novelty.
2. If Score >= 7, define the Decision Event:
   - Situation (S): The core problem and system context.
   - Action (A): The specific solution path or tool sequence chosen.
   - Outcome (R): 'success', 'fail', or 'partial'.
   - Insight: The key pattern or rule learned for future similar situations.

Output JSON only:
{{
    "score": int,
    "reason": "short explanation",
    "decision": {{
        "situation": "S",
        "action": "A",
        "outcome": "success/fail/partial",
        "insight": "key learned pattern"
    }}
}}
"""
        try:
            # 使用 provider 调用 LLM
            messages = [{"role": "user", "content": eval_prompt}]
            eval_response = await self._chat_with_failover(messages=messages)
            
            # 解析 JSON
            import json
            content = eval_response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            result = json.loads(content)
            
            if result.get("score", 0) >= 7:
                # 3. 存入决策缓存 (Minimalist Decision Cache)
                dec = result.get("decision", {})
                if dec:
                    await self.memory.add_decision(
                        situation=dec.get("situation", user_input),
                        action=dec.get("action", ""),
                        outcome=dec.get("outcome", "success"),
                        insight=dec.get("insight", ""),
                        cost={"tokens": getattr(self.last_metrics, 'total_tokens', 0)}
                    )
                    logger.info(f"🧠 决策流形已更新: {dec.get('insight', 'New Pattern')}")
            else:
                logger.debug(f"🗑️ 交互价值较低，跳过决策缓存 (Score: {result.get('score')})")
                
        except Exception as e:
            logger.warning(f"记忆整合失败: {e}")

    # ═══════════════════════════════════════════════════════════
    # 地基层：对话持久化 (Conversation Persistence)
    # ═══════════════════════════════════════════════════════════
    
    async def _persist_conversation(self, user_input: str, response: str, metrics=None):
        """无条件持久化每次对话（双写：SQLite + Markdown 日志）"""
        import time as _time
        now = datetime.datetime.now()
        
        # 构建对话记录
        tools_info = ""
        if metrics and metrics.tools_used:
            tools_info = f"\n工具调用: {', '.join(metrics.tools_used)}"
        
        conversation_entry = (
            f"## {now.strftime('%H:%M:%S')}\n\n"
            f"**用户**: {user_input}\n\n"
            f"**Genesis**: {response[:500]}{'...' if len(response) > 500 else ''}"
            f"{tools_info}\n\n---\n\n"
        )
        
        # === 写入 1: Markdown 日志文件 ===
        try:
            log_dir = Path.home() / ".nanogenesis" / "conversations"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"{now.strftime('%Y-%m-%d')}.md"
            
            if not log_file.exists():
                header = f"# Genesis 对话日志 - {now.strftime('%Y年%m月%d日')}\n\n"
                log_file.write_text(header, encoding='utf-8')
            
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(conversation_entry)
            
            logger.debug(f"📝 对话已写入日志: {log_file.name}")
        except Exception as e:
            logger.warning(f"日志写入失败: {e}")
        
        # === 写入 2: QmdMemory (SQLite + 语义向量) ===
        if self.memory:
            try:
                # 用较短的摘要存入 SQLite，便于语义搜索
                content_for_db = f"用户: {user_input}\nGenesis: {response[:300]}{tools_info}"
                path = f"conversations/{now.strftime('%Y-%m-%d/%H%M%S')}"
                await self.memory.add(
                    content=content_for_db,
                    path=path,
                    collection="conversations",
                    title=user_input[:60],
                    metadata={
                        "type": "conversation",
                        "timestamp": now.isoformat(),
                        "tools": metrics.tools_used if metrics else [],
                        "tokens": metrics.total_tokens if metrics else 0
                    }
                )
                logger.debug(f"💾 对话已存入 QmdMemory: {path}")
            except Exception as e:
                logger.warning(f"QmdMemory 写入失败: {e}")

    def _load_recent_conversations(self):
        """启动时加载近期对话日志到上下文（像 OpenClaw 读 memory/YYYY-MM-DD.md）"""
        log_dir = Path.home() / ".nanogenesis" / "conversations"
        if not log_dir.exists():
            logger.debug("无历史对话日志")
            return
        
        # 读取今天 + 昨天的日志
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)
        
        recent_content = ""
        for d in [yesterday, today]:
            log_file = log_dir / f"{d.strftime('%Y-%m-%d')}.md"
            if log_file.exists():
                try:
                    text = log_file.read_text(encoding='utf-8')
                    # 只取最近的对话（最后 2000 字符），避免 token 爆炸
                    if len(text) > 2000:
                        text = "...（早期对话已省略）\n" + text[-2000:]
                    recent_content += text + "\n"
                except Exception as e:
                    logger.warning(f"读取日志失败 {log_file}: {e}")
        
        if recent_content:
            # 注入到 context 的 recent_context 属性
            self.context._recent_conversation_context = recent_content.strip()
            loaded_lines = recent_content.count('\n')
            logger.info(f"🧠 已加载近期对话记忆 ({loaded_lines} 行)")
        else:
            self.context._recent_conversation_context = ""
            logger.debug("无近期对话可加载")

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
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            'total_interactions': len(self.metrics_history),
            'optimization_enabled': self.enable_optimization
        }
        
        if self.metrics_history:
            total_tokens = sum(m.total_tokens for m in self.metrics_history)
            total_time = sum(m.total_time for m in self.metrics_history)
            success_count = sum(1 for m in self.metrics_history if m.success)
            
            stats.update({
                'avg_tokens': total_tokens / len(self.metrics_history),
                'avg_time': total_time / len(self.metrics_history),
                'success_rate': success_count / len(self.metrics_history),
                'total_tools_used': sum(len(m.tools_used) for m in self.metrics_history)
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
