#!/usr/bin/env python3
"""
简单测试 TOOL_NODE 功能
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from genesis.core.registry import tool_registry
from genesis.v4.manager import NodeVault

def test_basic():
    """基本测试"""
    print("=== 基本测试 ===")
    
    # 测试 register_from_source
    source_code = '''
from genesis.core.base import Tool

class SimpleTestTool(Tool):
    @property
    def name(self) -> str:
        return "simple_test_tool"
        
    @property
    def description(self) -> str:
        return "简单测试工具"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "测试消息"}
            },
            "required": ["message"]
        }
        
    async def execute(self, message: str) -> str:
        return f"收到消息: {message}"
'''
    
    success = tool_registry.register_from_source("simple_test_tool", source_code)
    print(f"1. register_from_source 测试: {'✓ 通过' if success else '✗ 失败'}")
    
    # 测试工具是否可用
    tool = tool_registry.get("simple_test_tool")
    print(f"2. 获取工具测试: {'✓ 通过' if tool else '✗ 失败'}")
    if tool:
        print(f"   工具名称: {tool.name}")
        print(f"   工具描述: {tool.description}")
    
    # 测试 NodeVault 中的 TOOL 节点
    print("\n=== 测试 NodeVault 中的 TOOL 节点 ===")
    vault = NodeVault()
    
    # 查询 TOOL 节点数量
    conn = vault._conn
    cursor = conn.execute(
        "SELECT COUNT(*) as count FROM knowledge_nodes WHERE type = ?",
        ("TOOL",)
    )
    count = cursor.fetchone()[0]
    print(f"数据库中的 TOOL 节点数量: {count}")
    
    # 获取一个 TOOL 节点的源码
    cursor = conn.execute(
        "SELECT node_id FROM knowledge_nodes WHERE type = ? LIMIT 1",
        ("TOOL",)
    )
    row = cursor.fetchone()
    if row:
        node_id = row[0]
        print(f"获取 TOOL 节点: {node_id}")
        
        source_code = vault.get_node_content(node_id)
        if source_code:
            print(f"源码长度: {len(source_code)} 字符")
            
            # 提取工具名称
            import re
            tool_name_match = re.search(r'def name\(self\) -> str:\s*return "([^"]+)"', source_code)
            if not tool_name_match:
                tool_name_match = re.search(r"def name\(self\) -> str:\s*return '([^']+)'", source_code)
            
            if tool_name_match:
                tool_name = tool_name_match.group(1)
                print(f"提取的工具名称: {tool_name}")
                
                # 测试动态注册
                print(f"测试动态注册 {tool_name}...")
                success = tool_registry.register_from_source(tool_name, source_code)
                print(f"动态注册结果: {'✓ 成功' if success else '✗ 失败'}")
                
                if success:
                    # 验证工具
                    tool = tool_registry.get(tool_name)
                    print(f"工具验证: {'✓ 可用' if tool else '✗ 不可用'}")
                    if tool:
                        print(f"工具描述: {tool.description}")
                        # 清理
                        tool_registry.unregister(tool_name)
                        print(f"已清理工具: {tool_name}")
    
    return success

if __name__ == "__main__":
    success = test_basic()
    sys.exit(0 if success else 1)