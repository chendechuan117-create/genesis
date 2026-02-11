"""
工具生成器 - 动态创建工具（类似 OpenClaw）

当 Agent 需要一个不存在的工具时，自动生成并注册。
"""

from typing import Dict, Optional
import subprocess
import json
from pathlib import Path
import logging


logger = logging.getLogger(__name__)


class ToolGenerator:
    """工具生成器"""
    
    def __init__(self, api_key: str, storage_path: str = "./generated_tools"):
        """
        初始化
        
        Args:
            api_key: DeepSeek API key
            storage_path: 生成的工具存储路径
        """
        self.api_key = api_key
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
    
    def generate_tool(self, tool_description: str, tool_name: str) -> Optional[str]:
        """
        生成工具代码
        
        Args:
            tool_description: 工具描述（需求）
            tool_name: 工具名称
        
        Returns:
            生成的工具代码路径，失败返回 None
        """
        
        # 构建提示词
        prompt = f"""你是一个 Python 工具生成器。

需求：{tool_description}

请生成一个符合以下接口的 Python 工具类：

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.base import Tool
from typing import Dict, Any

class {self._to_class_name(tool_name)}(Tool):
    '''工具描述'''
    
    @property
    def name(self) -> str:
        return "{tool_name}"
    
    @property
    def description(self) -> str:
        return "工具功能描述"
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {{
            "type": "object",
            "properties": {{
                # 参数定义
            }},
            "required": []
        }}
    
    async def execute(self, **kwargs) -> str:
        '''执行工具'''
        # 实现逻辑
        pass
```

要求：
1. 只输出完整的 Python 代码
2. 不要解释，不要 markdown 标记
3. 代码必须可以直接运行
4. 包含必要的 import
5. 实现完整的功能逻辑

生成的代码："""
        
        # 调用 API 生成代码
        try:
            code = self._call_api(prompt)
            
            # 清理代码（移除可能的 markdown 标记）
            code = self._clean_code(code)
            
            # 保存代码
            tool_file = self.storage_path / f"{tool_name}.py"
            with open(tool_file, 'w', encoding='utf-8') as f:
                f.write(code)
            
            logger.debug(f"✓ 工具代码已生成: {tool_file}")
            return str(tool_file)
        
        except Exception as e:
            logger.error(f"✗ 工具生成失败: {e}")
            return None
    
    def load_tool(self, tool_file: str):
        """
        动态加载工具
        
        Args:
            tool_file: 工具文件路径
        
        Returns:
            工具实例
        """
        import importlib.util
        
        # 动态导入模块
        spec = importlib.util.spec_from_file_location("generated_tool", tool_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # 查找工具类
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and hasattr(obj, 'name') and hasattr(obj, 'execute'):
                return obj()
        
        raise Exception("未找到有效的工具类")
    
    def _call_api(self, prompt: str) -> str:
        """调用 DeepSeek API"""
        
        data = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "你是一个 Python 代码生成专家。只输出代码，不要解释。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 2000
        }
        
        cmd = [
            'curl', '-s', '-X', 'POST',
            'https://api.deepseek.com/v1/chat/completions',
            '-H', f'Authorization: Bearer {self.api_key}',
            '-H', 'Content-Type: application/json',
            '-d', json.dumps(data)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            response = json.loads(result.stdout)
            return response['choices'][0]['message']['content']
        else:
            raise Exception(f"API 调用失败: {result.stderr}")
    
    def _clean_code(self, code: str) -> str:
        """清理代码（移除 markdown 标记）"""
        
        # 移除 ```python 和 ```
        code = code.replace('```python', '').replace('```', '')
        
        # 移除开头的空行
        lines = code.split('\n')
        while lines and not lines[0].strip():
            lines.pop(0)
        
        return '\n'.join(lines)
    
    def _to_class_name(self, tool_name: str) -> str:
        """工具名转类名"""
        # 例如：get_weather → GetWeatherTool
        parts = tool_name.split('_')
        return ''.join(p.capitalize() for p in parts) + 'Tool'


# 示例用法
if __name__ == '__main__':
    import asyncio
    import os
    
    async def test():
        # 创建生成器
        api_key = os.getenv('DEEPSEEK_API_KEY')
        if not api_key:
            raise RuntimeError("请先设置环境变量 DEEPSEEK_API_KEY")

        generator = ToolGenerator(api_key=api_key)
        
        # 生成工具
        print("="*60)
        print("测试工具生成")
        print("="*60)
        
        tool_description = """
        创建一个获取天气信息的工具。
        
        功能：
        - 输入：城市名称（city）
        - 输出：该城市的天气信息（模拟数据即可）
        """
        
        tool_file = generator.generate_tool(tool_description, "get_weather")
        
        if tool_file:
            print(f"\n生成的代码:")
            with open(tool_file, 'r', encoding='utf-8') as f:
                print(f.read())
            
            # 尝试加载
            try:
                tool = generator.load_tool(tool_file)
                print(f"\n✓ 工具加载成功: {tool.name}")
                print(f"  描述: {tool.description}")
                
                # 测试执行
                result = await tool.execute(city="北京")
                print(f"\n执行结果: {result}")
            
            except Exception as e:
                print(f"\n✗ 工具加载失败: {e}")
    
    asyncio.run(test())
