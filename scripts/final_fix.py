#!/usr/bin/env python3
"""
最终修复 loop.py 文件
"""

import re

# 读取文件
with open('/home/chendechusn/Genesis/Genesis/genesis/v4/loop.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 在 _parse_op_result 方法后添加新方法
# 找到 _parse_op_result 方法的结束位置
pattern = r'(\s+)def _parse_op_result\(self, content: str\) -> Dict\[str, Any\]:.*?\n\1\S'
match = re.search(pattern, content, re.DOTALL)
if match:
    method_end = match.end() - len(match.group(1)) - 1  # 减去缩进和下一个字符
    
    # 新方法内容
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
                    tool_name_match = re.search(r'def name\\(self\\) -> str:\\s*return "([^"]+)"', source_code)
                    if not tool_name_match:
                        tool_name_match = re.search(r"def name\\(self\\) -> str:\\s*return '([^']+)'", source_code)
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
    
    # 插入新方法
    content = content[:method_end] + '\n' + new_method + content[method_end:]

# 修改 _run_op_phase 方法，添加动态加载代码
# 找到 _run_op_phase 方法中 op_prompt = 的位置
pattern2 = r'(\s+)async def _run_op_phase\(self, task_payload: Dict\[str, Any\], step_callback: Any\) -> Dict\[str, Any\]:.*?\n\1\s+op_prompt = self\.factory\.build_op_prompt\(task_payload\)'
match2 = re.search(pattern2, content, re.DOTALL)
if match2:
    # 在 op_prompt 行前插入动态加载代码
    op_prompt_line_start = match2.end() - len('op_prompt = self.factory.build_op_prompt(task_payload)')
    indent = match2.group(1) + '    '
    
    dynamic_load_code = f'''{indent}# === 动态加载 TOOL_NODE ===
{indent}active_nodes = task_payload.get("active_nodes", [])
{indent}tool_nodes_loaded = self._load_tool_nodes_from_active_nodes(active_nodes)
{indent}if tool_nodes_loaded:
{indent}    logger.info(f"动态加载了 {{len(tool_nodes_loaded)}} 个 TOOL 节点")
{indent}
'''
    
    content = content[:op_prompt_line_start] + dynamic_load_code + content[op_prompt_line_start:]

# 写入文件
with open('/home/chendechusn/Genesis/Genesis/genesis/v4/loop.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("修复完成")