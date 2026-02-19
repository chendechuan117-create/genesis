"""
工具注册表 - 统一管理所有工具
"""

from typing import Dict, List, Any, Optional
import logging

from .base import Tool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册表 - 核心组件"""
    
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
    
    def register(self, tool: Tool) -> None:
        """注册工具"""
        if tool.name in self._tools:
            logger.warning(f"工具 {tool.name} 已存在，将被覆盖")
        
        self._tools[tool.name] = tool
        logger.debug(f"✓ 注册工具: {tool.name}")
    
    def unregister(self, tool_name: str) -> None:
        """注销工具"""
        if tool_name in self._tools:
            del self._tools[tool_name]
            logger.debug(f"✓ 注销工具: {tool_name}")
    
    def get(self, tool_name: str) -> Optional[Tool]:
        """获取工具"""
        return self._tools.get(tool_name)
    
    def list_tools(self) -> List[str]:
        """列出所有工具名称"""
        return list(self._tools.keys())
    
    def get_definitions(self) -> List[Dict[str, Any]]:
        """获取所有工具的 Schema 定义"""
        return [tool.to_schema() for tool in self._tools.values()]
    
    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """执行工具"""
        tool = self.get(tool_name)
        
        if not tool:
            error_msg = f"工具 {tool_name} 不存在"
            logger.error(error_msg)
            return f"Error: {error_msg}"
        
        try:
            logger.debug(f"执行工具: {tool_name} with {arguments}")
            result = await tool.execute(**arguments)
            logger.debug(f"✓ 工具执行成功: {tool_name}")
            return result
        
        except Exception as e:
            error_msg = f"工具 {tool_name} 执行失败: {str(e)}"
            logger.error(error_msg)
            return f"Error: {error_msg}"
    
    def __len__(self) -> int:
        """工具数量"""
        return len(self._tools)
    
    def __contains__(self, tool_name: str) -> bool:
        """检查工具是否存在"""
        return tool_name in self._tools

    def load_from_file(self, file_path: str) -> bool:
        """从文件动态加载工具"""
        import importlib.util
        import inspect
        from pathlib import Path
        from .base import Tool
        
        path = Path(file_path)
        if not path.exists():
            logger.error(f"工具文件不存在: {path}")
            return False
            
        try:
            # 动态导入模块
            spec = importlib.util.spec_from_file_location(path.stem, path)
            module = importlib.util.module_from_spec(spec)
            
            # Auto-Dependency Installation Logic
            import sys
            import subprocess
            
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    spec.loader.exec_module(module)
                    break # Success
                except ModuleNotFoundError as e:
                    if attempt == max_retries - 1:
                        raise # Give up after retries
                    
                    # Extract package name (simple heuristic)
                    missing_package = e.name.split('.')[0]
                    logger.warning(f"缺少依赖 '{missing_package}'，正在尝试自动安装...")
                    
                    try:
                        # Use sys.executable to ensure we install in the current environment (venv)
                        subprocess.check_call(
                            [sys.executable, "-m", "pip", "install", missing_package],
                            stdout=subprocess.DEVNULL, # Keep it clean
                            stderr=subprocess.PIPE
                        )
                        logger.info(f"✓ 依赖 '{missing_package}' 安装成功")
                    except subprocess.CalledProcessError:
                        logger.warning(f"标准安装失败，尝试使用 --break-system-packages 强制安装 '{missing_package}'...")
                        try:
                            subprocess.check_call(
                                [sys.executable, "-m", "pip", "install", missing_package, "--break-system-packages"],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE
                            )
                            logger.info(f"✓ 依赖 '{missing_package}' (强制) 安装成功")
                        except subprocess.CalledProcessError as e2:
                             logger.error(f"无法安装依赖 '{missing_package}': {e2}")
                             raise e # Re-raise original error if install fails
            
            # 查找 Tool 子类
            loaded = False
            for name, obj in inspect.getmembers(module):
                if (inspect.isclass(obj) and 
                    issubclass(obj, Tool) and 
                    obj is not Tool and
                    obj.__module__ == module.__name__):
                    
                    try:
                        tool_instance = obj()
                        self.register(tool_instance)
                        loaded = True
                    except Exception as e:
                        logger.warning(f"无法实例化工具 {name}: {e}")
            
            return loaded
            
        except Exception as e:
            logger.error(f"加载工具文件失败 {path}: {e}")
            return False
