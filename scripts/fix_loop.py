#!/usr/bin/env python3
"""
修复 loop.py 文件，正确添加 TOOL_NODE 动态加载功能
"""

# 读取原始文件
with open('/home/chendechusn/Genesis/Genesis/genesis/v4/loop.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到 _parse_op_result 方法的结束位置
new_lines = []
in_method = False
method_indent = ""
for i, line in enumerate(lines):
    new_lines.append(line)
    
    # 检查是否是 _parse_op_result 方法的最后一行
    if line.strip().startswith('def _parse_op_result'):
        in_method = True
        # 获取方法的缩进
        method_indent = line[:len(line) - len(line.lstrip())]
    elif in_method and line.strip() and not line.startswith(method_indent + '    '):
        in_method = False
        # 这是 _parse_op_result 方法结束后的第一行
        # 在这里插入新方法
        
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
        new_lines.append(new_method)

# 现在修改 _run_op_phase 方法
final_lines = []
in_run_op_phase = False
for line in new_lines:
    final_lines.append(line)
    
    if line.strip().startswith('async def _run_op_phase'):
        in_run_op_phase = True
    elif in_run_op_phase and line.strip() and line.strip().startswith('op_prompt ='):
        # 在 op_prompt = 之前插入动态加载代码
        indent = line[:len(line) - len(line.lstrip())]
        dynamic_load_code = f'''{indent}        # === 动态加载 TOOL_NODE ===
{indent}        active_nodes = task_payload.get("active_nodes", [])
{indent}        tool_nodes_loaded = self._load_tool_nodes_from_active_nodes(active_nodes)
{indent}        if tool_nodes_loaded:
{indent}            logger.info(f"动态加载了 {{len(tool_nodes_loaded)}} 个 TOOL 节点")
{indent}        
'''
        # 移除原来的 op_prompt 行，我们会在后面重新添加
        final_lines.pop()  # 移除刚刚添加的 op_prompt 行
        final_lines.append(dynamic_load_code)
        final_lines.append(line)  # 重新添加 op_prompt 行
        in_run_op_phase = False

# 写入修改后的文件
with open('/home/chendechusn/Genesis/Genesis/genesis/v4/loop.py', 'w', encoding='utf-8') as f:
    f.writelines(final_lines)

print("loop.py 修复完成")