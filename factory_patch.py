"""
最小补丁：在 factory.py 中注册 BrowserUseTool 和 VisualTool
"""

PATCH = '''
    try:
        from genesis.tools.browser_use_tool import BrowserUseTool
        from genesis.tools.visual_tool import VisualTool
        tools.register(BrowserUseTool())
        tools.register(VisualTool())
    except Exception as e:
        logger.error(f"V4 tool group [browser_visual] failed: {e}")
'''

# 读取原文件
with open('/workspace/factory.py', 'r') as f:
    content = f.read()

# 在 trace_query 组之后、activate_vault_tools 之前插入
marker = '    activate_vault_tools(tools)'
if marker in content and 'browser_use_tool' not in content:
    content = content.replace(
        marker,
        PATCH + '\n' + marker
    )
    with open('/workspace/factory.py', 'w') as f:
        f.write(content)
    print('✓ Patch applied')
else:
    if 'browser_use_tool' in content:
        print('! Patch already present')
    else:
        print('✗ Marker not found')
