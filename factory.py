"""
Genesis V4 — 极简工厂
无 V3 遗留，无冗余依赖
"""

import logging
import re
from typing import Optional

from genesis.core.provider import NativeHTTPProvider
from genesis.core.registry import ToolRegistry
from genesis.core.provider_manager import ProviderRouter
from genesis.core.config import config
from genesis.v4.agent import GenesisV4

logger = logging.getLogger(__name__)


def _build_explicit_provider(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
):
    if not api_key:
        return None
    resolved_model = (model or "deepseek/deepseek-chat").strip()
    resolved_base_url = (base_url or "https://api.deepseek.com/v1").strip()
    provider_name = "deepseek" if "api.deepseek.com" in resolved_base_url.lower() else "override"
    return NativeHTTPProvider(
        api_key=api_key,
        base_url=resolved_base_url,
        default_model=resolved_model,
        provider_name=provider_name,
    )


def create_agent(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: str = "deepseek/deepseek-chat",
) -> GenesisV4:
    """创建 V4 Agent 实例"""
    logger.info(">>> V4 Factory: Init Provider")
    provider = _build_explicit_provider(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
    if provider is None:
        provider = ProviderRouter(
            config=config, api_key=api_key, base_url=base_url, model=model
        )

    logger.info(">>> V4 Factory: Register Tools")
    tools = ToolRegistry()

    # 逐组注册，单组失败不影响其余工具
    try:
        from genesis.tools.file_tools import ReadFileTool, WriteFileTool, AppendFileTool, ListDirectoryTool, GrepFilesTool
        for t in [ReadFileTool(), WriteFileTool(), AppendFileTool(), ListDirectoryTool(), GrepFilesTool()]:
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
        from genesis.tools.skill_creator_tool import SkillCreatorTool, SkillInventoryTool
        tools.register(SkillCreatorTool(tools))
        tools.register(SkillInventoryTool(tools))
    except Exception as e:
        logger.error(f"V4 tool group [skill_creator] failed: {e}")

    try:
        from genesis.tools.node_tools import (
            RecordContextNodeTool, RecordPointTool, RecordLineTool, RecordLessonNodeTool,
            CreateMetaNodeTool, DeleteNodeTool, CreateGraphNodeTool, CreateNodeEdgeTool,
            RecordToolNodeTool, RecordDiscoveryTool,
        )
        for t in [RecordContextNodeTool(), RecordPointTool(), RecordLineTool(), RecordLessonNodeTool(),
                   CreateMetaNodeTool(), DeleteNodeTool(), CreateGraphNodeTool(), CreateNodeEdgeTool(),
                   RecordToolNodeTool(), RecordDiscoveryTool()]:
            tools.register(t)
    except Exception as e:
        logger.error(f"V4 tool group [node_tools] failed: {e}")

    try:
        from genesis.tools.search_tool import SearchKnowledgeNodesTool
        tools.register(SearchKnowledgeNodesTool())
    except Exception as e:
        logger.error(f"V4 tool group [search_tool] failed: {e}")

    try:
        from genesis.tools.pls_query_tool import PLSQueryTool
        tools.register(PLSQueryTool())
    except Exception as e:
        logger.error(f"V4 tool group [pls_query] failed: {e}")

    try:
        from genesis.tools.trace_query_tool import TraceQueryTool
        tools.register(TraceQueryTool())
    except Exception as e:
        logger.error(f"V4 tool group [trace_query] failed: {e}")

    # TOOL 节点自动激活：从 vault 加载 C-Phase 创建的动态工具
    activate_vault_tools(tools)
    # 物理存量技能自动激活：仅在启动时加载一次磁盘幽灵技能，避免运行时轮次重复扫描刷屏
    autoload_physical_skills(tools)

    # 核心改动：把带有 Failover 能力的 Router 直接传给 Agent
    agent = GenesisV4(tools=tools, provider=provider)
    logger.info(
        f"✓ Genesis V4 ready ({len(tools)} tools, "
        f"{'Direct Provider Override' if isinstance(provider, NativeHTTPProvider) else 'Failover Enabled'})"
    )
    return agent


def activate_vault_tools(registry: ToolRegistry) -> int:
    """从 vault 加载所有 TOOL 节点并注册到运行时 registry。

    桥接 record_tool_node（存储）→ register_from_source（激活）。
    可在启动时和 auto 轮次间调用，幂等安全。

    Returns:
        成功激活的工具数量
    """
    try:
        from genesis.v4.manager import NodeVault, TOOL_EXEC_MIN_TIER
        vault = NodeVault()
        tool_nodes = vault.get_tool_nodes(min_tier=TOOL_EXEC_MIN_TIER)
    except Exception as e:
        logger.warning(f"activate_vault_tools: cannot read vault — {e}")
        return 0

    activated = 0
    for tn in tool_nodes:
        name = tn["tool_name"]
        # 跳过已注册的同名工具（内置工具优先）
        if name in registry:
            logger.debug(f"activate_vault_tools: skip '{name}' (already registered)")
            continue
        try:
            ok = registry.register_from_source(
                name=name,
                source_code=tn["source_code"],
                node_id=tn["node_id"],
                trust_tier=tn["trust_tier"],
            )
            if ok:
                activated += 1
                logger.info(f"activate_vault_tools: ✓ '{name}' loaded from vault (node={tn['node_id']})")
            else:
                logger.warning(f"activate_vault_tools: ✗ '{name}' failed to register (node={tn['node_id']})")
        except Exception as e:
            logger.warning(f"activate_vault_tools: ✗ '{name}' error — {e}")

    if activated:
        logger.info(f"activate_vault_tools: {activated} vault tools activated")
    return activated


def autoload_physical_skills(registry: ToolRegistry) -> int:
    """自动扫描本地 skills_dir 目录下的物理技能并动态加载一次。
    由于此逻辑扫描本地磁盘，仅应在服务初始化时调用一次，严禁内嵌到轮次主循环中以免造成日志和文件系统扫描的冗余负荷。
    """
    try:
        from pathlib import Path
        skills_dir = Path(__file__).parent / "genesis" / "skills"
        if not skills_dir.exists():
            skills_dir = Path(__file__).parent / "skills"
        if not skills_dir.exists():
            return 0
        
        phys_activated = 0
        for py_file in skills_dir.glob("*.py"):
            if py_file.name == "__init__.py":
                continue
            tool_name = py_file.stem
            if tool_name in registry:
                continue
            try:
                source_code = py_file.read_text(encoding="utf-8")
                if not re.search(r'class\s+\w+\s*\(\s*Tool\s*\)', source_code):
                    logger.debug(f"autoload_physical_skills: skip '{tool_name}' (no Tool subclass)")
                    continue
                ok = registry.register_from_source(
                    name=tool_name,
                    source_code=source_code,
                    node_id=f"PHYS_{tool_name.upper()}",
                    trust_tier="REFLECTION",
                )
                if ok:
                    phys_activated += 1
                    logger.info(f"autoload_physical_skills: ✓ '{tool_name}' loaded from physical skill file")
            except Exception as ex:
                logger.debug(f"failed to load physical skill '{tool_name}': {ex}")
        if phys_activated:
            logger.info(f"autoload_physical_skills: {phys_activated} physical skills autoloaded")
        return phys_activated
    except Exception as e:
        logger.debug(f"physical skill autoloading skipped: {e}")
        return 0
