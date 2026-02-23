import uuid
import logging
from typing import Dict, Any

from genesis.core.base import Tool

logger = logging.getLogger(__name__)

class SpawnSubAgentTool(Tool):
    """
    Spawns an isolated sub-agent to handle complex or parallelizable tasks.
    """
    
    @property
    def name(self) -> str:
        return "spawn_sub_agent"
    
    @property
    def description(self) -> str:
        return """创建一个完全被隔离的子代理 (Sub-Agent) 分身来执行特定的复杂任务。
这相当于你把一个独立的任务交给了一个全新的、拥有与你同样能力的分身去完成，然后你只需等待它的最终汇报。主上下文不会被子代理的思考过程污染。
适用于：复杂长文本分析、试错性极强的探索任务，或者需要高度专注的单线程任务。"""
        
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mission_description": {
                    "type": "string",
                    "description": "交给子代理的具体任务描述 (尽量详尽，告诉它需要做什么，去哪找，最后输出什么)"
                },
                "sub_agent_name": {
                    "type": "string",
                    "description": "给这个分身起个名字 (如 'DeepCodeAnalyzer_1')",
                    "default": "SubAgent"
                }
            },
            "required": ["mission_description"]
        }
        
    async def execute(self, mission_description: str, sub_agent_name: str = "SubAgent") -> str:
        # Import inside to prevent circular dependency during tool registration
        from genesis.core.factory import GenesisFactory
        from genesis.tools.sub_agent_manager import SubAgentManager
        import asyncio
        
        uid = str(uuid.uuid4())[:8]
        full_name = f"{sub_agent_name}_{uid}"
        task_id = f"task_{uid}"
        
        logger.info(f"🧬 Spawning Async Sub-Agent: {full_name} for mission [{task_id}]...")
        
        try:
            # Create a completely isolated agent instance using the main engine's factory
            # Since SessionManager generates a new UUID if not explicitly loaded, this agent
            # starts with a completely blank memory slate and blank context buffers.
            sub_agent = GenesisFactory.create_common(
                user_id=full_name,
                enable_optimization=False, # Disable meta-recursive loop optimization for clones
                max_iterations=8 # Limit sub-agent lifespan to prevent infinite nested loops
            )
            
            # CRITICAL: Force the sub-agent into the Consumables Pool (Phase 4)
            consumable_provider = sub_agent.provider_router.get_consumable_provider()
            sub_agent.provider_router.active_provider = consumable_provider
            sub_agent.provider_router.active_provider_name = "consumables_pool"
            sub_agent.loop.provider = consumable_provider
            
            # Explicitly enforce Sub-Agent Directives into its localized context (Relaxed Phase 4)
            sub_protocol = (
                "\n\n【Sub-Agent Override Protocol (Evolution Probe)】\n"
                "1. You are an asynchronous Sub-Agent spawned by the Prime Genesis Node.\n"
                "2. Your ONLY purpose is to fulfill the MISSION given to you and report back.\n"
                "3. Provide extremely detailed, conclusive findings as your final output.\n"
                "4. DO NOT ask the user for confirmation. Make executive decisions on your own.\n"
                "5. VERY IMPORTANT: Start your final summarizing reply with a <reflection> block detailing your process, "
                "followed by the clear final text summarizing your results/insights. "
                "The Prime Node will extract the insights directly from your text.\n"
            )
            sub_agent.context.system_prompt += sub_protocol
            
            # Define the coroutine wrapper
            async def run_probe():
                try:
                    logger.info(f"🚀 Sub-Agent {full_name} Starting...")
                    result = await sub_agent.process(
                        user_input=f"YOUR MISSION: {mission_description}",
                        problem_type="sub_mission"
                    )
                    final_report = "Unable to retrieve final state."
                    messages = result.get('messages', [])
                    if messages:
                        last_msg = messages[-1]
                        if hasattr(last_msg, 'content'):
                            final_report = last_msg.content
                        elif isinstance(last_msg, dict):
                            final_report = last_msg.get('content', str(last_msg))
                    return final_report
                except Exception as e:
                    logger.error(f"子代理 {full_name} 后台执行崩溃: {e}")
                    raise e
            
            # Create asyncio task and hand it over to the Manager
            coro_task = asyncio.create_task(run_probe())
            manager = SubAgentManager()
            manager.register_task(task_id, coro_task)
            
            return f"✅ 异步子代理 '{full_name}' 已挂载并开始执行！\n[Task ID]: {task_id}\n\n主脑现在已**彻底解放**。您可以立刻去处理其他任务（或结束当前思考）。当您需要检查结果时，请调用 `check_sub_agent` 并传入 `{task_id}`。"
            
        except Exception as e:
            logger.error(f"子代理 {full_name} 后台挂载失败: {e}", exc_info=True)
            return f"Error: 子代理派生或挂载后台时遭遇物理崩溃 - {str(e)}"
