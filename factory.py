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

    # 逐组注册，单组失败不影响其余工具
    try:
        from genesis.tools.file_tools import ReadFileTool, WriteFileTool, AppendFileTool, ListDirectoryTool
        for t in [ReadFileTool(), WriteFileTool(), AppendFileTool(), ListDirectoryTool()]:
            tools.register(t)
    except Exception as e:
        logger.error(f"V4 tool group [file_tools] failed: {e}")

    try:
        from genesis.tools.shell_tool import ShellTool
        tools.register(ShellTool(use_sandbox=False))
    except Exception as e:
        logger.error(f"V4 tool group [shell_tool] failed: {e}")

    try:
        from genesis.tools.web_tool import WebSearchTool
        from genesis.tools.url_tool import ReadUrlTool
        tools.register(WebSearchTool())
        tools.register(ReadUrlTool())
    except Exception as e:
        logger.error(f"V4 tool group [web_tools] failed: {e}")

    try:
        from genesis.tools.skill_creator_tool import SkillCreatorTool
        tools.register(SkillCreatorTool(tools))
    except Exception as e:
        logger.error(f"V4 tool group [skill_creator] failed: {e}")

    try:
        from genesis.tools.node_tools import (
            SearchKnowledgeNodesTool, RecordContextNodeTool, RecordLessonNodeTool,
            CreateMetaNodeTool, DeleteNodeTool, CreateGraphNodeTool, CreateNodeEdgeTool,
            RecordToolNodeTool
        )
        for t in [SearchKnowledgeNodesTool(), RecordContextNodeTool(), RecordLessonNodeTool(),
                   CreateMetaNodeTool(), DeleteNodeTool(), CreateGraphNodeTool(), CreateNodeEdgeTool(),
                   RecordToolNodeTool()]:
            tools.register(t)
    except Exception as e:
        logger.error(f"V4 tool group [node_tools] failed: {e}")

    try:
        from genesis.tools.dispatch_tool import DispatchTool
        tools.register(DispatchTool())
    except Exception as e:
        logger.error(f"V4 tool group [dispatch_tool] failed: {e}")

    # 核心改动：把带有 Failover 能力的 Router 直接传给 Agent
    agent = GenesisV4(tools=tools, provider=provider_router)
    logger.info(f"✓ Genesis V4 ready ({len(tools)} tools, Failover Enabled)")
    return agent
