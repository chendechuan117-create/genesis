"""
工具注册表 - 统一管理所有工具
"""

from typing import Dict, List, Any, Optional, Set
import ast
import logging
import importlib.util
import inspect
import sys
import subprocess
from pathlib import Path

from .base import Tool, MetaTool

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
            
        # 拦截底层的 JSON 解析错误
        if "__json_decode_error__" in arguments:
            raw_bad = str(arguments["__json_decode_error__"])[:200]
            logger.warning(f"Intercepted JSON decode error for tool {tool_name}: {raw_bad[:80]}")
            return f"Error: JSON参数解析失败。错误片段: {raw_bad}\n请换一种方式：将多行内容拆分为多步小命令，或改用 write_file 工具写入文件。"
        
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
            
            # Auto-Dependency Installation Logic (白名单制，防供应链攻击)
            _PIP_WHITELIST = frozenset([
                "requests", "httpx", "beautifulsoup4", "bs4", "lxml",
                "pyyaml", "toml", "pillow", "numpy", "pandas",
                "aiohttp", "aiofiles", "chardet", "python-dateutil",
                "jinja2", "markdownify", "feedparser",
            ])
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    spec.loader.exec_module(module)
                    break # Success
                except ModuleNotFoundError as e:
                    if attempt == max_retries - 1:
                        raise # Give up after retries
                    
                    missing_package = e.name.split('.')[0]
                    if missing_package not in _PIP_WHITELIST:
                        logger.error(f"⛔ 自动安装被拒绝: '{missing_package}' 不在白名单中。手动安装后重试。")
                        raise
                    logger.warning(f"缺少依赖 '{missing_package}'（白名单内），正在自动安装...")
                    try:
                        subprocess.check_call(
                            [sys.executable, "-m", "pip", "install", missing_package],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE
                        )
                        logger.info(f"✓ 依赖 '{missing_package}' 安装成功")
                    except subprocess.CalledProcessError as e2:
                        logger.error(f"无法安装依赖 '{missing_package}': {e2}")
                        raise e
            
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

    # AST 安全审计：禁止动态工具源码中出现的危险模块和调用
    _BLOCKED_IMPORTS: Set[str] = frozenset({
        "os", "subprocess", "shutil", "ctypes", "socket", "pickle",
        "shelve", "tempfile", "signal", "multiprocessing", "threading",
        "importlib", "code", "codeop", "compileall", "py_compile",
    })
    _BLOCKED_BUILTINS: Set[str] = frozenset({
        "exec", "eval", "compile", "__import__", "globals", "locals",
        "breakpoint", "exit", "quit",
    })
    _BLOCKED_ATTRS: Set[str] = frozenset({
        "__subclasses__", "__globals__", "__builtins__", "__code__",
        "__bases__", "__mro__",
    })

    def _audit_source_safety(self, source_code: str, name: str) -> Optional[str]:
        """AST 安全审计：在 exec 前扫描源码中的危险模式。
        
        Returns:
            None 表示通过审计，否则返回拒绝原因字符串。
        """
        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            return f"语法错误: {e}"

        for node in ast.walk(tree):
            # 检查 import 语句
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_module = alias.name.split('.')[0]
                    if top_module in self._BLOCKED_IMPORTS:
                        return f"禁止导入模块 '{alias.name}'（安全策略）"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top_module = node.module.split('.')[0]
                    if top_module in self._BLOCKED_IMPORTS:
                        return f"禁止导入模块 '{node.module}'（安全策略）"
            # 检查危险函数调用
            elif isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id in self._BLOCKED_BUILTINS:
                    return f"禁止调用内置函数 '{func.id}'（安全策略）"
                if isinstance(func, ast.Attribute) and func.attr in self._BLOCKED_BUILTINS:
                    return f"禁止调用 '{func.attr}'（安全策略）"
            # 检查危险属性访问
            elif isinstance(node, ast.Attribute):
                if node.attr in self._BLOCKED_ATTRS:
                    return f"禁止访问属性 '{node.attr}'（安全策略）"
        return None

    def register_from_source(self, name: str, source_code: str, node_id: str = "", trust_tier: str = "REFLECTION") -> bool:
        """从源码字符串动态注册工具
        
        Args:
            name: 工具名称
            source_code: Python 源码字符串，必须包含一个继承自 Tool/MetaTool 的类定义
            node_id: 来源 TOOL 节点 ID（元工具协议）
            trust_tier: 信任等级（元工具协议）
            
        Returns:
            bool: 是否成功注册
        """
        try:
            # AST 安全审计：在编译/执行前拦截危险代码
            reject_reason = self._audit_source_safety(source_code, name)
            if reject_reason:
                logger.warning(f"🛡️ 动态工具 {name} (node={node_id}) 被安全审计拦截: {reject_reason}")
                return False

            # 创建一个唯一的模块名
            module_name = f"dynamic_tool_{name}"
            
            # 编译源码
            compiled = compile(source_code, f"<dynamic_tool_{name}>", 'exec')
            
            # 创建新的模块
            module = type(sys)(module_name, doc="Dynamically created tool module")

            # 注入必要的属性和导入（包括 MetaTool）
            module.__file__ = f"<dynamic_tool_{name}>"
            module.__name__ = module_name
            
            exec("from genesis.core.base import Tool, MetaTool", module.__dict__)
            
            # 执行编译后的代码
            exec(compiled, module.__dict__)
            
            # 查找 Tool 子类
            loaded = False
            for obj_name, obj in inspect.getmembers(module):
                if (inspect.isclass(obj) and 
                    issubclass(obj, Tool) and 
                    obj is not Tool and
                    obj is not MetaTool):
                    
                    try:
                        tool_instance = obj()
                        # 检查工具名称是否匹配
                        if tool_instance.name != name:
                            logger.warning(f"工具类中的名称 '{tool_instance.name}' 与请求的名称 '{name}' 不匹配，使用类中的名称")
                        
                        # 元工具协议：盖上信任水印
                        if isinstance(tool_instance, MetaTool):
                            tool_instance._node_id = node_id
                            tool_instance._trust_tier = trust_tier
                            tool_instance._source = "nodevault"
                        elif node_id:
                            # 非 MetaTool 子类也尽力附加元数据
                            tool_instance._node_id = node_id
                            tool_instance._trust_tier = trust_tier
                        
                        self.register(tool_instance)
                        logger.info(f"✓ 从源码动态注册工具: {tool_instance.name} (node={node_id}, tier={trust_tier})")
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
