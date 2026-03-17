"""
工具注册表 - 统一管理所有工具
"""

from typing import Dict, List, Any, Optional
import logging
import importlib.util
import inspect
import sys
import subprocess
from pathlib import Path

from .base import Tool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册表 - 核心组件"""
    
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._cached_definitions: Optional[List[Dict[str, Any]]] = None
    
    def register(self, tool: Tool) -> None:
        """注册工具"""
        if tool.name in self._tools:
            logger.warning(f"工具 {tool.name} 已存在，将被覆盖")
        
        self._tools[tool.name] = tool
        self._cached_definitions = None  # Invalidate cache
        logger.debug(f"✓ 注册工具: {tool.name}")
    
    def unregister(self, tool_name: str) -> None:
        """注销工具"""
        if tool_name in self._tools:
            del self._tools[tool_name]
            self._cached_definitions = None  # Invalidate cache
            logger.debug(f"✓ 注销工具: {tool_name}")
    
    def get(self, tool_name: str) -> Optional[Tool]:
        """获取工具"""
        return self._tools.get(tool_name)
    
    def list_tools(self) -> List[str]:
        """列出所有工具名称"""
        return list(self._tools.keys())
    
    def get_definitions(self) -> List[Dict[str, Any]]:
        """获取所有工具的 Schema 定义 (按字母排序以确保缓存命中)"""
        if self._cached_definitions is not None:
            return self._cached_definitions
            
        definitions = [tool.to_schema() for tool in self._tools.values()]
        self._cached_definitions = sorted(definitions, key=lambda x: x["function"]["name"])
        return self._cached_definitions
    
    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """执行工具"""
        tool = self.get(tool_name)
        
        if not tool:
            error_msg = f"工具 {tool_name} 不存在"
            logger.error(error_msg)
            return f"Error: {error_msg}"
            
        # 拦截底层的 JSON 解析错误，直接用自然语言反馈给大模型，避免引发底层的 TypeError
        if "__json_decode_error__" in arguments:
            raw_bad_json = arguments["__json_decode_error__"]
            error_msg = f"你生成的工具参数 JSON 格式有误（通常是未转义的换行符或引号导致）。请检查并修复你的 JSON 格式后再试。你刚才输出的错误内容片段：\n{raw_bad_json[:200]}..."
            logger.warning(f"Intercepted JSON decode error for tool {tool_name}")
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
        path = Path(file_path)
        if not path.exists():
            logger.error(f"工具文件不存在: {path}")
            return False
            
        try:
            # 动态导入模块
            spec = importlib.util.spec_from_file_location(path.stem, path)
            module = importlib.util.module_from_spec(spec)
            
            # Auto-Dependency Installation Logic
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

    def register_from_source(self, name: str, source_code: str) -> bool:
        """从源码字符串动态注册工具
        
        Args:
            name: 工具名称
            source_code: Python 源码字符串，必须包含一个继承自 Tool 的类定义
            
        Returns:
            bool: 是否成功注册
        """
        try:
            # 创建一个唯一的模块名
            module_name = f"dynamic_tool_{name}"
            
            # 编译源码
            compiled = compile(source_code, f"<dynamic_tool_{name}>", 'exec')
            
            # 创建新的模块

            
            module = type(sys)(

            
                module_name,

            
                doc="Dynamically created tool module"

            
            )

            
            

            
            # 注入必要的属性和导入

            
            module.__file__ = f"<dynamic_tool_{name}>"

            
            module.__name__ = module_name

            
            exec("from genesis.core.base import Tool", module.__dict__)
            
            # 注入必要的导入
            exec("from genesis.core.base import Tool", module.__dict__)
            
            # 执行编译后的代码
            exec(compiled, module.__dict__)
            
            # 查找 Tool 子类
            loaded = False
            for obj_name, obj in inspect.getmembers(module):
                if (inspect.isclass(obj) and 
                    issubclass(obj, Tool) and 
                    obj is not Tool):
                    
                    try:
                        tool_instance = obj()
                        # 检查工具名称是否匹配
                        if tool_instance.name != name:
                            logger.warning(f"工具类中的名称 '{tool_instance.name}' 与请求的名称 '{name}' 不匹配，使用类中的名称")
                        
                        self.register(tool_instance)
                        logger.info(f"✓ 从源码动态注册工具: {tool_instance.name}")
                        loaded = True
                        break
                    except Exception as e:
                        logger.warning(f"无法实例化动态工具 {obj_name}: {e}")
            
            if not loaded:
                logger.error(f"在源码中未找到有效的 Tool 子类: {name}")
                return False
                
            return True
            
        except SyntaxError as e:
            logger.error(f"源码语法错误 {name}: {e}")
            return False
        except Exception as e:
            logger.error(f"从源码注册工具失败 {name}: {e}")
            return False

class ProviderRegistry:
    """提供商注册表 - 动态加载和管理不同的大模型提供商工厂"""
    
    def __init__(self):
        # 存储返回 LLMProvider 实例的 Callable 工厂函数
        self._provider_builders: Dict[str, Any] = {}
        
    def register(self, name: str, builder: Any) -> None:
        """注册一个 Provider 工厂函数"""
        if name in self._provider_builders:
            logger.warning(f"提供商工厂 {name} 已存在，将被覆盖")
            
        self._provider_builders[name] = builder
        logger.debug(f"✓ 注册提供商插件: {name}")
        
    def unregister(self, name: str) -> None:
        if name in self._provider_builders:
            del self._provider_builders[name]
            
    def get_builder(self, name: str) -> Optional[Any]:
        return self._provider_builders.get(name)
        
    def list_providers(self) -> List[str]:
        return list(self._provider_builders.keys())

# 全局单例
tool_registry = ToolRegistry()
provider_registry = ProviderRegistry()


# zhipu 和 sambanova 已在 genesis/providers/cloud_providers.py 中统一注册
