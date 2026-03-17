#!/usr/bin/env python3
"""
测试 TOOL_NODE 动态加载功能
"""

import sys
import logging
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from genesis.core.registry import ToolRegistry, tool_registry
from genesis.v4.manager import NodeVault

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_register_from_source():
    """测试从源码注册工具"""
    print("=== 测试 register_from_source 方法 ===")
    
    # 创建一个简单的工具源码
    source_code = '''
from genesis.core.base import Tool

class TestTool(Tool):
    @property
    def name(self) -> str:
        return "test_tool"
        
    @property
    def description(self) -> str:
        return "这是一个测试工具"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "测试参数"}
            },
            "required": ["param1"]
        }
        
    async def execute(self, param1: str) -> str:
        return f"测试工具执行成功，参数: {param1}"
'''
    
    # 测试注册
    success = tool_registry.register_from_source("test_tool", source_code)
    print(f"注册结果: {success}")
    
    # 验证工具是否已注册
    tool = tool_registry.get("test_tool")
    print(f"获取工具: {tool is not None}")
    if tool:
        print(f"工具名称: {tool.name}")
        print(f"工具描述: {tool.description}")
    
    return success

def test_tool_node_loading():
    """测试从 NodeVault 加载 TOOL 节点"""
    print("\n=== 测试 TOOL_NODE 加载 ===")
    
    # 初始化 NodeVault
    vault = NodeVault()
    
    # 查询 TOOL 节点
    import sqlite3
    conn = vault._conn
    cursor = conn.execute(
        "SELECT node_id, type, title FROM knowledge_nodes WHERE type = ? LIMIT 5",
        ("TOOL",)
    )
    tool_nodes = cursor.fetchall()
    
    print(f"找到 {len(tool_nodes)} 个 TOOL 节点")
    
    for i, node in enumerate(tool_nodes):
        node_id = node[0]
        title = node[2]
        print(f"{i+1}. {node_id}: {title[:50]}...")
        
        # 获取源码
        source_code = vault.get_node_content(node_id)
        if source_code:
            print(f"   源码长度: {len(source_code)} 字符")
            
            # 尝试提取工具名称
            import re
            tool_name_match = re.search(r'def name\(self\) -> str:\s*return "([^"]+)"', source_code)
            if not tool_name_match:
                tool_name_match = re.search(r"def name\(self\) -> str:\s*return '([^']+)'", source_code)
            
            if tool_name_match:
                tool_name = tool_name_match.group(1)
                print(f"   提取的工具名称: {tool_name}")
                
                # 测试动态注册
                print(f"   测试动态注册...")
                success = tool_registry.register_from_source(tool_name, source_code)
                print(f"   注册结果: {success}")
                
                if success:
                    # 验证工具是否可用
                    tool = tool_registry.get(tool_name)
                    if tool:
                        print(f"   工具描述: {tool.description}")
                        # 清理：注销工具
                        tool_registry.unregister(tool_name)
                        print(f"   已清理工具: {tool_name}")
                break  # 只测试第一个工具

def test_v4_loop_integration():
    """测试 V4Loop 集成"""
    print("\n=== 测试 V4Loop 集成 ===")
    
    # 创建一个模拟的 task_payload
    task_payload = {
        "op_intent": "测试 TOOL_NODE 动态加载",
        "active_nodes": ["TOOL_SYSTEM_MONITOR"],  # 使用我们迁移的工具节点
        "instructions": "测试动态加载的工具"
    }
    
    print(f"模拟 task_payload:")
    print(f"  op_intent: {task_payload['op_intent']}")
    print(f"  active_nodes: {task_payload['active_nodes']}")
    print(f"  instructions: {task_payload['instructions']}")
    
    # 测试 _load_tool_nodes_from_active_nodes 方法
    from genesis.v4.loop import V4Loop
    from genesis.core.registry import ToolRegistry
    from genesis.providers.mock_provider import MockProvider
    
    # 创建模拟的组件
    tools = ToolRegistry()
    provider = MockProvider()
    
    # 创建 V4Loop 实例
    loop = V4Loop(tools, provider, max_iterations=3)
    
    # 调用方法
    loaded_tools = loop._load_tool_nodes_from_active_nodes(task_payload["active_nodes"])
    print(f"动态加载的工具: {loaded_tools}")
    
    return len(loaded_tools) > 0

def main():
    """主测试函数"""
    print("开始测试 TOOL_NODE 动态加载功能")
    print("=" * 60)
    
    # 测试 1: register_from_source 方法
    test1_success = test_register_from_source()
    
    # 测试 2: TOOL_NODE 加载
    test2_success = test_tool_node_loading()
    
    # 测试 3: V4Loop 集成
    try:
        test3_success = test_v4_loop_integration()
    except Exception as e:
        print(f"V4Loop 集成测试失败: {e}")
        test3_success = False
    
    print("\n" + "=" * 60)
    print("测试结果汇总:")
    print(f"1. register_from_source 方法: {'✓ 通过' if test1_success else '✗ 失败'}")
    print(f"2. TOOL_NODE 加载测试: {'✓ 通过' if test2_success else '✗ 失败'}")
    print(f"3. V4Loop 集成测试: {'✓ 通过' if test3_success else '✗ 失败'}")
    
    if test1_success and test2_success and test3_success:
        print("\n✅ 所有测试通过！TOOL_NODE 动态加载功能已就绪。")
        return 0
    else:
        print("\n❌ 部分测试失败，请检查问题。")
        return 1

if __name__ == "__main__":
    sys.exit(main())