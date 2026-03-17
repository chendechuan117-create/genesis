#!/usr/bin/env python3
"""
修改 loop.py 文件，添加 TOOL_NODE 动态加载功能
"""

import re

# 读取原始文件
with open('/home/chendechusn/Genesis/Genesis/genesis/v4/loop.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 在 _get_op_tools 方法前添加新方法
new_method = '''    def _load_tool_nodes_from_active_nodes(self, active_nodes: List[str]) -> List[str]:
        """从 active_nodes 中加载 TOOL 节点并动态注册工具"""
        loaded_tools = []
        for node_id in active_nodes:
            if node_id.startswith("TOOL_"):
                # 获取节点内容
                source_code = self.vault.get_node_content(node_id)
                if source_code:
                    # 从源码中提取工具名称
                    import re
                    # 尝试从源码中提取工具名称
                    tool_name_match = re.search(r"def name\\(self\\) -> str:\\s*return \\"([^\\"]+)\\"", source_code)
                    if not tool_name_match:
                        tool_name_match = re.search(r"def name\\(self\\) -> str:\\s*return \\'([^\\']+)\\'", source_code)
                    if tool_name_match:
                        tool_name = tool_name_match.group(1)
                        # 动态注册工具
                        if self.tools.register_from_source(tool_name, source_code):
                            loaded_tools.append(tool_name)
                            logger.info(f"动态注册工具: {tool_name} from {node_id}")
                        else:
                            logger.warning(f"动态注册工具失败: {node_id}")
                    else:
                        logger.warning(f"无法从 TOOL 节点提取工具名称: {node_id}")
        return loaded_tools
'''

# 找到 _get_op_tools 方法的位置
pattern = r'(\s+)def _get_op_tools\(self\) -> List\[Any\]:'
match = re.search(pattern, content)
if match:
    indent = match.group(1)
    # 在 _get_op_tools 方法前插入新方法
    insert_pos = match.start()
    content = content[:insert_pos] + new_method + '\n' + indent + content[insert_pos:]

# 修改 _run_op_phase 方法，在开头添加动态加载逻辑
run_op_phase_pattern = r'(\s+)async def _run_op_phase\(self, task_payload: Dict\[str, Any\], step_callback: Any\) -> Dict\[str, Any\]:'
match = re.search(run_op_phase_pattern, content)
if match:
    indent = match.group(1)
    # 找到方法体的开始
    method_start = match.end()
    # 找到第一个缩进减少的位置（方法体的开始）
    lines = content[method_start:].split('\n')
    body_start = 0
    for i, line in enumerate(lines):
        if line.strip() and not line.startswith(indent + '    '):
            body_start = method_start + sum(len(line) + 1 for line in lines[:i])
            break
    
    # 在方法体开始处插入动态加载代码
    dynamic_load_code = f'''{indent}        # === 动态加载 TOOL_NODE ===
{indent}        active_nodes = task_payload.get("active_nodes", [])
{indent}        tool_nodes_loaded = self._load_tool_nodes_from_active_nodes(active_nodes)
{indent}        if tool_nodes_loaded:
{indent}            logger.info(f"动态加载了 {{len(tool_nodes_loaded)}} 个 TOOL 节点")
{indent}        
'''
    content = content[:body_start] + dynamic_load_code + content[body_start:]

# 写入修改后的文件
with open('/home/chendechusn/Genesis/Genesis/genesis/v4/loop.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("loop.py 修改完成")