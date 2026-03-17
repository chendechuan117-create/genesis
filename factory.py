"""
Genesis V4 — 极简工厂
无 V3 遗留，无冗余依赖
"""

import logging
from typing import Optional

from genesis.core.registry import ToolRegistry
from genesis.core.provider_manager import ProviderRouter
from genesis.core.config import config
from genesis.v4.agent import GenesisV4

logger = logging.getLogger(__name__)


def create_agent(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: str = "deepseek/deepseek-chat",
) -> GenesisV4:
    """创建 V4 Agent 实例"""
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
        from genesis.tools.url_tool import ReadUrlTool
        from genesis.tools.skill_creator_tool import SkillCreatorTool
        from genesis.tools.node_tools import SearchKnowledgeNodesTool, RecordContextNodeTool, RecordLessonNodeTool, CreateMetaNodeTool, DeleteNodeTool, CreateGraphNodeTool, CreateNodeEdgeTool

        tools.register(ReadFileTool())
        tools.register(WriteFileTool())
        tools.register(AppendFileTool())
        tools.register(ListDirectoryTool())
        tools.register(ShellTool(use_sandbox=False))
        tools.register(WebSearchTool())
        tools.register(ReadUrlTool())
        tools.register(SkillCreatorTool(tools))
        tools.register(SearchKnowledgeNodesTool())
        tools.register(RecordContextNodeTool())
        tools.register(RecordLessonNodeTool())
        tools.register(CreateMetaNodeTool())
        tools.register(DeleteNodeTool())
        tools.register(CreateGraphNodeTool())
        tools.register(CreateNodeEdgeTool())
    except Exception as e:
        logger.error(f"V4 tool registration failed: {e}")

    # 核心改动：把带有 Failover 能力的 Router 直接传给 Agent
    agent = GenesisV4(tools=tools, provider=provider_router)
    logger.info(f"✓ Genesis V4 ready ({len(tools)} tools, Failover Enabled)")
    return agent
