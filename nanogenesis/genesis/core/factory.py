
import logging
from pathlib import Path
from typing import Optional

from genesis.agent import NanoGenesis
from genesis.core.registry import ToolRegistry
from genesis.core.context import SimpleContextBuilder
from genesis.memory import SQLiteMemoryStore, SessionManager
from genesis.core.cognition import CognitiveProcessor
from genesis.core.scheduler import AgencyScheduler
from genesis.core.provider_manager import ProviderRouter
from genesis.core.config import config
from genesis.core.trust_anchor import TrustAnchorManager
from genesis.tools.chain_next_tool import ChainNextTool

from genesis.optimization.prompt_optimizer import PromptOptimizer
from genesis.optimization.behavior_optimizer import BehaviorOptimizer
from genesis.optimization.tool_optimizer import ToolUsageOptimizer
from genesis.optimization.profile_evolution import UserProfileEvolution
from genesis.intelligence.adaptive_learner import AdaptiveLearner

# Tools
from genesis.tools.file_tools import (
    ReadFileTool, WriteFileTool,
    AppendFileTool, ListDirectoryTool
)
from genesis.tools.shell_tool import ShellTool
from genesis.tools.web_tool import WebSearchTool
from genesis.tools.browser_tool import BrowserTool
from genesis.tools.memory_tool import SaveMemoryTool, SearchMemoryTool
from genesis.tools.skill_creator_tool import SkillCreatorTool
from genesis.tools.scheduler_tool import SchedulerTool
from genesis.tools.system_health_tool import SystemHealthTool
from genesis.tools.douyin_tool import DouyinAnalysisTool

logger = logging.getLogger(__name__)

class GenesisFactory:
    """
    Factory for creating NanoGenesis instances.
    Handles component initialization and dependency injection.
    """

    @staticmethod
    def create_common(
        user_id: str = "default_user",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "deepseek/deepseek-chat",
        gemini_key: Optional[str] = None,
        gemini_url: Optional[str] = None,
        max_iterations: int = 10,
        enable_optimization: bool = True
    ) -> NanoGenesis:
        """
        Create a standard instance of NanoGenesis with all default components.
        """
        # 1. Configuration & Providers
        provider_router = ProviderRouter(
            config=config,
            api_key=api_key,
            base_url=base_url,
            model=model
        )
        # Note: Gemini args currently handled by config/router defaults, logic preserved.

        # 2. Memory Systems
        memory = SQLiteMemoryStore()
        session_manager = SessionManager()
        from genesis.core.mission import MissionManager
        mission_manager = MissionManager()
        
        # 3. Context & Tools
        tools = ToolRegistry()
        context = SimpleContextBuilder()
        context.set_provider(
            provider=provider_router.get_active_provider(),
            memory_store=memory,
            session_id=session_manager.session_id
        )

        # 4. Optimization Components
        optimization_components = {}
        if enable_optimization:
            optimization_components['prompt_optimizer'] = PromptOptimizer(
                provider=provider_router.get_active_provider(),
                optimize_interval=50
            )
            optimization_components['behavior_optimizer'] = BehaviorOptimizer(provider=provider_router.get_active_provider())
            optimization_components['tool_optimizer'] = ToolUsageOptimizer()
            optimization_components['profile_evolution'] = UserProfileEvolution(
                user_id,
                provider=provider_router.get_active_provider()
            )
            optimization_components['adaptive_learner'] = AdaptiveLearner(
                 storage_path=config.workspace_root / "data" / "adaptive_learning.json"
            )
            
            # Register specific optimization tools
            tools.register(ChainNextTool())
        
        # 5. Scheduler
        scheduler = AgencyScheduler(tools)
        
        # 6. Trust Anchor
        trust_anchor = TrustAnchorManager()

        # 7. Register Standard Tools
        GenesisFactory._register_standard_tools(tools, memory, scheduler, provider_router, context)

        # 8. Meta-Cognition Protocols
        meta_protocol, intent_prompt = GenesisFactory._load_protocols()

        # 9. Cognition
        # Note: CognitiveProcessor depends on `chat_func`.
        # Since we are constructing NanoGenesis, and NanoGenesis usually holds the `chat_with_failover`.
        # However, with providing `provider_router`, we can pass `provider_router.chat_with_failover` directly!
        cognition = CognitiveProcessor(
            chat_func=provider_router.chat_with_failover,
            memory=memory,
            intent_prompt=intent_prompt,
            meta_protocol=meta_protocol,
            tools_registry=tools
        )

        # 10. Assemble Agent
        agent = NanoGenesis(
            user_id=user_id,
            config=config,
            tools=tools,
            context=context,
            provider_router=provider_router,
            memory=memory,
            session_manager=session_manager,
            mission_manager=mission_manager,
            scheduler=scheduler,
            cognition=cognition,
            optimization_components=optimization_components,
            trust_anchor=trust_anchor,
            max_iterations=max_iterations,
            enable_optimization=enable_optimization
        )
        
        # 11. Post-Construction Initialization
        # (Start session, load history, etc. - previously in __init__)
        
        # Restore session
        if session_manager.restore_last_session_sync():
            logger.info(f"🔄 [Factory] Restored session: {session_manager.session_id}")
        else:
            logger.info(f"✨ [Factory] New session: {session_manager.session_id}")
            
        # Initialize System Prompt
        GenesisFactory._initialize_system_prompt(agent, context)

        return agent

    @staticmethod
    def _register_standard_tools(tools: ToolRegistry, memory: SQLiteMemoryStore, scheduler: AgencyScheduler, provider_router: ProviderRouter, context: SimpleContextBuilder):
        try:
            tools.register(ReadFileTool())
            tools.register(WriteFileTool())
            tools.register(AppendFileTool())
            tools.register(ListDirectoryTool())
            tools.register(ShellTool(use_sandbox=False))
            tools.register(WebSearchTool())
            tools.register(BrowserTool())
            tools.register(SaveMemoryTool(memory))
            tools.register(SearchMemoryTool(memory))
            tools.register(SkillCreatorTool(tools))
            tools.register(SchedulerTool(scheduler))
            tools.register(SystemHealthTool(provider_router, memory, tools, context, scheduler))
            tools.register(DouyinAnalysisTool())
            logger.info(f"✓ [Factory] Registered {len(tools)} tools")
        except Exception as e:
            logger.warning(f"Error registering tools: {e}")

    @staticmethod
    def _load_protocols():
        meta_protocol = None
        intent_prompt = None
        try:
            # Strategist
            # Note: We need to find the path relative to THIS file or Agent file.
            # Assuming standard structure relative to genesis package
            from genesis.agent import NanoGenesis # Import purely for path reference logic if needed, or use relative paths
            base_path = Path(__file__).parent.parent 
            
            strategist_path = base_path / "intelligence/prompts/pure_metacognition_protocol.txt"
            if strategist_path.exists():
                with open(strategist_path, "r", encoding="utf-8") as f:
                    meta_protocol = f.read()
            
            # Oracle
            oracle_path = base_path / "intelligence/prompts/intent_recognition.txt"
            if oracle_path.exists():
                with open(oracle_path, "r", encoding="utf-8") as f:
                    intent_prompt = f.read()
                    
        except Exception as e:
            logger.warning(f"Failed to load protocols: {e}")
            
        return meta_protocol, intent_prompt

    @staticmethod
    def _initialize_system_prompt(agent, context):
        """Initializes system prompt based on optimization components"""
        # This logic mimics the original _initialize_system_prompt in agent.py
        # But now requires access to the components we just built/passed to agent.
        
        opt_comps = agent.optimization_components # or pass dict directly
        
        if agent.enable_optimization and opt_comps.get('profile_evolution'):
            # Append profile to existing prompt instead of replacing it
            profile_ctx = opt_comps['profile_evolution'].get_profile_context()
            current_prompt = context.system_prompt
            new_prompt = f"{current_prompt}\n\n{profile_ctx}"
            context.update_system_prompt(new_prompt)
            
        if agent.enable_optimization and opt_comps.get('prompt_optimizer'):
            optimized_prompt = opt_comps['prompt_optimizer'].get_latest_optimized_prompt()
            if optimized_prompt:
                context.update_system_prompt(optimized_prompt)
                logger.info("✓ [Factory] Loaded optimized system prompt")
                
        # Record initial prompt
        if opt_comps.get('prompt_optimizer'):
             opt_comps['prompt_optimizer'].current_system_prompt = context.system_prompt
