
import logging
from pathlib import Path
from typing import Optional

from genesis.agent import NanoGenesis
from genesis.core.registry import ToolRegistry
from genesis.core.context import SimpleContextBuilder
from genesis.core.provider_manager import ProviderRouter
from genesis.core.config import config


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
        NOTE: Requires V1 modules (intelligence/, optimization/) to be on sys.path.
        """
        # V1-only imports (lazy to avoid breaking V2-only mode)
        from genesis.memory import SQLiteMemoryStore, SessionManager
        from genesis.core.cognition import CognitiveProcessor
        from genesis.core.scheduler import AgencyScheduler
        from genesis.core.trust_anchor import TrustAnchorManager
        from genesis.tools.chain_next_tool import ChainNextTool
        from genesis.optimization.prompt_optimizer import PromptOptimizer
        from genesis.optimization.behavior_optimizer import BehaviorOptimizer
        from genesis.optimization.tool_optimizer import ToolUsageOptimizer
        from genesis.optimization.profile_evolution import UserProfileEvolution
        from genesis.intelligence.adaptive_learner import AdaptiveLearner

        # 1. Configuration & Providers
        print(">>> Step 1: Init ProviderRouter")
        provider_router = ProviderRouter(
            config=config,
            api_key=api_key,
            base_url=base_url,
            model=model
        )
        # Note: Gemini args currently handled by config/router defaults, logic preserved.

        # 2. Memory Systems
        print(">>> Step 2: Init Memory Systems")
        memory = SQLiteMemoryStore()
        session_manager = SessionManager()
        from genesis.core.mission import MissionManager
        mission_manager = MissionManager()
        
        # 3. Context & Tools
        print(">>> Step 3: Init Context & Tools")
        tools = ToolRegistry()
        context = SimpleContextBuilder()
        context.set_provider(
            provider=provider_router.get_active_provider(),
            memory_store=memory,
            session_id=session_manager.session_id
        )

        # 4. Optimization Components
        print(">>> Step 4: Init Optimization Components")
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
        print(">>> Step 5: Init Scheduler")
        scheduler = AgencyScheduler(tools)
        
        # 6. Trust Anchor
        print(">>> Step 6: Init Trust Anchor")
        trust_anchor = TrustAnchorManager()

        # 7. Register Standard Tools
        print(">>> Step 7: Register Standard Tools")
        GenesisFactory._register_standard_tools(tools, memory, scheduler, provider_router, context)

        # 8. Meta-Cognition Protocols
        print(">>> Step 8: Load Protocols")
        meta_protocol, intent_prompt = GenesisFactory._load_protocols()

        # 9. Cognition
        # Note: CognitiveProcessor depends on `chat_func`.
        # Since we are constructing NanoGenesis, and NanoGenesis usually holds the `chat_with_failover`.
        # However, with providing `provider_router`, we can pass `provider_router.chat_with_failover` directly!
        print(">>> Step 9: Init Cognition")
        cognition = CognitiveProcessor(
            chat_func=provider_router.chat_with_failover,
            memory=memory,
            intent_prompt=intent_prompt,
            meta_protocol=meta_protocol,
            tools_registry=tools
        )

        # 10. Assemble Agent
        print(">>> Step 10: Assemble Agent")
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
        
        print(">>> Step 11: Post-Construction Initialization")
        # Restore session
        if session_manager.restore_last_session_sync():
            logger.info(f"🔄 [Factory] Restored session: {session_manager.session_id}")
        else:
            logger.info(f"✨ [Factory] New session: {session_manager.session_id}")
            
        # Initialize System Prompt
        GenesisFactory._initialize_system_prompt(agent, context)

        return agent

    @staticmethod
    def create_v2(
        user_id: str = "default_user",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "deepseek/deepseek-chat",
    ) -> NanoGenesis:
        """
        V2 精简模式 — 只初始化 Manager + Workshop + OpExecutor 需要的组件。
        跳过 V1 的 Cognition / Optimization / Mission / Memory 系统。
        """
        logger.info(">>> V2 Factory: Init ProviderRouter")
        provider_router = ProviderRouter(
            config=config, api_key=api_key, base_url=base_url, model=model
        )

        logger.info(">>> V2 Factory: Init Tools & Context")
        tools = ToolRegistry()
        context = SimpleContextBuilder()

        # 注册标准工具（V1/V2 共用）
        GenesisFactory._register_standard_tools(tools, None, None, provider_router, context)

        logger.info(">>> V2 Factory: Assemble Agent (V2-only)")
        agent = NanoGenesis(
            user_id=user_id,
            config=config,
            tools=tools,
            context=context,
            provider_router=provider_router,
            enable_optimization=False,
        )
        logger.info(f"✓ V2 Agent ready ({len(tools)} tools)")
        return agent

    @staticmethod
    def create_v3(
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "deepseek/deepseek-chat",
    ):
        """
        Genesis V3 — 自组织智能体。
        极简架构：ReAct Loop + 自管理车间。
        没有 Manager/OpExecutor，没有维度语言，没有预设学习步骤。
        """
        from genesis.v3.agent import GenesisV3

        logger.info(">>> V3 Factory: Init Provider")
        provider_router = ProviderRouter(
            config=config, api_key=api_key, base_url=base_url, model=model
        )

        logger.info(">>> V3 Factory: Register Tools")
        tools = ToolRegistry()

        # 只注册 Genesis 真正需要的工具，干净利落
        try:
            from genesis.tools.file_tools import ReadFileTool, WriteFileTool, AppendFileTool, ListDirectoryTool
            from genesis.tools.shell_tool import ShellTool
            from genesis.tools.web_tool import WebSearchTool
            from genesis.tools.visual_tool import VisualTool
            from genesis.tools.workshop_tool import WorkshopTool
            from genesis.tools.skill_creator_tool import SkillCreatorTool

            tools.register(ReadFileTool())
            tools.register(WriteFileTool())
            tools.register(AppendFileTool())
            tools.register(ListDirectoryTool())
            tools.register(ShellTool(use_sandbox=False))
            tools.register(WebSearchTool())
            tools.register(VisualTool())
            tools.register(WorkshopTool())
            tools.register(SkillCreatorTool(tools))
        except Exception as e:
            logger.error(f"V3 tool registration failed: {e}")

        provider = provider_router.get_active_provider()
        agent = GenesisV3(
            tools=tools,
            provider=provider,
        )
        logger.info(f"✓ Genesis V3 ready ({len(tools)} tools)")
        return agent
        
    @staticmethod
    def create_v4(
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "deepseek/deepseek-chat",
    ):
        """
        Genesis V4 — 认知装配师 (The Glassbox Amplifier)
        极简架构：单 Agent + Node Vault，强调思维过程的白盒暴露。
        """
        from genesis.v4.agent import GenesisV4

        logger.info(">>> V4 Factory: Init Provider")
        provider_router = ProviderRouter(
            config=config, api_key=api_key, base_url=base_url, model=model
        )

        logger.info(">>> V4 Factory: Register Tools")
        tools = ToolRegistry()

        try:
            from genesis.tools.file_tools import ReadFileTool, WriteFileTool, AppendFileTool, ListDirectoryTool
            from genesis.tools.shell_tool import ShellTool
            from genesis.tools.web_tool import WebSearchTool
            from genesis.tools.visual_tool import VisualTool
            from genesis.tools.workshop_tool import WorkshopTool
            from genesis.tools.skill_creator_tool import SkillCreatorTool

            tools.register(ReadFileTool())
            tools.register(WriteFileTool())
            tools.register(AppendFileTool())
            tools.register(ListDirectoryTool())
            tools.register(ShellTool(use_sandbox=False))
            tools.register(WebSearchTool())
            tools.register(VisualTool())
            tools.register(WorkshopTool())
            tools.register(SkillCreatorTool(tools))
        except Exception as e:
            logger.error(f"V4 tool registration failed: {e}")

        provider = provider_router.get_active_provider()
        agent = GenesisV4(
            tools=tools,
            provider=provider,
        )
        logger.info(f"✓ Genesis V4 ready ({len(tools)} tools)")
        return agent

    @staticmethod
    def _register_standard_tools(tools: ToolRegistry, memory: SQLiteMemoryStore, scheduler: AgencyScheduler, provider_router: ProviderRouter, context: SimpleContextBuilder):
        try:
            # First, register some highly coupled core tools that need specific dependencies
            # We keep these few as explicit internal injections until a DI framework is robust enough
            from genesis.tools.memory_tool import SaveMemoryTool, SearchMemoryTool
            from genesis.tools.skill_creator_tool import SkillCreatorTool
            from genesis.tools.scheduler_tool import SchedulerTool
            from genesis.tools.system_health_tool import SystemHealthTool
            
            tools.register(SkillCreatorTool(tools))
            # V1-only tools (need memory/scheduler)
            if memory is not None:
                tools.register(SaveMemoryTool(memory))
                tools.register(SearchMemoryTool(memory))
            if scheduler is not None:
                tools.register(SchedulerTool(scheduler))
            if memory is not None and scheduler is not None:
                tools.register(SystemHealthTool(provider_router, memory, tools, context, scheduler))
            
            # Now, explicitly register all standard decoupled tools from the tools directory
            from genesis.tools.file_tools import ReadFileTool, WriteFileTool, AppendFileTool, ListDirectoryTool
            from genesis.tools.shell_tool import ShellTool
            from genesis.tools.web_tool import WebSearchTool
            from genesis.tools.browser_tool import BrowserTool
            from genesis.tools.douyin_tool import DouyinAnalysisTool
            
            # Sub-Agent Tool Registration
            from genesis.tools.spawn_sub_agent_tool import SpawnSubAgentTool
            from genesis.tools.check_sub_agent_tool import CheckSubAgentTool
            # from genesis.skills.system_task_complete import SystemTaskComplete  <-- REMOVED: Legacy/Missing
            from genesis.tools.evomap_skill_search_tool import EvoMapSkillSearchTool
            from genesis.tools.github_commits_tool import GithubCommitsTool
            tools.register(SpawnSubAgentTool())
            tools.register(CheckSubAgentTool())
            # tools.register(SystemTaskComplete())  <-- REMOVED
            tools.register(EvoMapSkillSearchTool())
            tools.register(GithubCommitsTool())
            
            tools.register(ReadFileTool())
            tools.register(WriteFileTool())
            tools.register(AppendFileTool())
            tools.register(ListDirectoryTool())
            tools.register(ShellTool(use_sandbox=False))
            tools.register(WebSearchTool())
            tools.register(BrowserTool())
            tools.register(DouyinAnalysisTool())
            
            # Vision (Visual Cortex)
            from genesis.tools.visual_tool import VisualTool
            tools.register(VisualTool())
            
            logger.info(f"✓ [Factory] Explicitly Registered {len(tools)} standard tools")
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
