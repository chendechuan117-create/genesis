#!/usr/bin/env python3
"""
修复 registry.py 中的 register_from_source 方法
"""

import re

# 读取文件
with open('/home/chendechusn/Genesis/Genesis/genesis/core/registry.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 找到 register_from_source 方法中创建模块的部分
pattern = r'(\s+)# 创建新的模块\n\s+module = type\(sys\)\(\n\s+module_name,\n\s+doc="Dynamically created tool module"\n\s+\)'
match = re.search(pattern, content)
if match:
    indent = match.group(1)
    
    # 替换为修复后的代码
    fixed_code = f'''{indent}# 创建新的模块
{indent}module = type(sys)(
{indent}    module_name,
{indent}    doc="Dynamically created tool module"
{indent})
{indent}
{indent}# 注入必要的属性和导入
{indent}module.__file__ = f"<dynamic_tool_{{name}}>"
{indent}module.__name__ = module_name
{indent}exec("from genesis.core.base import Tool", module.__dict__)'''
    
    # 替换内容
    content = content[:match.start()] + fixed_code + content[match.end():]

# 写入文件
with open('/home/chendechusn/Genesis/Genesis/genesis/core/registry.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("registry.py 修复完成")