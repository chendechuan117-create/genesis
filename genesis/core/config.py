"""
配置管理中枢 - NanoGenesis Nervous System
实现零配置启动 (Zero-Conf)，自动嗅探宿主环境 (OpenClaw) 和系统变量。
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class GlobalConfig:
    """全局配置对象"""
    # API Keys
    aixj_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    openrouter_model: Optional[str] = "trinity-large-preview"
    
    # Consumables Pool (Phase 3)
    siliconflow_api_key: Optional[str] = None
    dashscope_api_key: Optional[str] = None
    qianfan_api_key: Optional[str] = None
    zhipu_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    cloudflare_api_key: Optional[str] = None
    zen_api_key: Optional[str] = None
    
    tavily_api_key: Optional[str] = None
    
    # Observability (optional)
    langfuse_public_key: Optional[str] = None
    langfuse_secret_key: Optional[str] = None
    langfuse_host: Optional[str] = "https://cloud.langfuse.com"
    
    # Network & Limits
    http_proxy: Optional[str] = None
    https_proxy: Optional[str] = None
    connect_timeout: int = 15
    request_timeout: int = 120
    
    # Paths
    workspace_root: Path = Path.cwd()
    
    # System
    debug: bool = False

class ConfigManager:
    """
    配置管理器 (Singleton Pattern)
    优先级: Env Vars > .env > OpenClaw Config > Defaults
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._config = GlobalConfig()
        self._load_all()
        self._apply_proxies()
        self._initialized = True
        
    @property
    def config(self) -> GlobalConfig:
        return self._config
        
    def _load_all(self):
        """加载所有配置源"""
        # 1. 加载 .env (中间层)
        self._load_dotenv()
        
        # 2. 加载环境变量 (最高优)
        self._load_env_vars()
        
        # 3. 验证核心凭证
        self._validate()

    def _load_dotenv(self):
        """加载 .env 文件"""
        # 简单实现，避免引入 python-dotenv 依赖
        # Search for .env in current and parent directories
        search_path = Path.cwd()
        env_path = None
        
        # Look up 3 levels
        for _ in range(4):
            candidate = search_path / ".env"
            if candidate.exists():
                env_path = candidate
                break
            if search_path.parent == search_path: # Root
                break
            search_path = search_path.parent
            
        if not env_path:
            return
            
        try:
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        key, val = line.split('=', 1)
                        self._set_config_by_key(key.strip(), val.strip().strip('"').strip("'"))
        except Exception as e:
            logger.warning(f"读取 .env 失败: {e}")

    # ENV_KEY (upper) -> GlobalConfig attribute name
    _KEY_MAP = {
        "AIXJ_API_KEY": "aixj_api_key",
        "DEEPSEEK_API_KEY": "deepseek_api_key",
        "GEMINI_API_KEY": "gemini_api_key",
        "OPENAI_API_KEY": "openai_api_key",
        "OPENROUTER_API_KEY": "openrouter_api_key",
        "OPENROUTER_MODEL": "openrouter_model",
        "SILICONFLOW_API_KEY": "siliconflow_api_key",
        "DASHSCOPE_API_KEY": "dashscope_api_key",
        "QIANFAN_API_KEY": "qianfan_api_key",
        "ZHIPU_API_KEY": "zhipu_api_key",
        "GROQ_API_KEY": "groq_api_key",
        "CLOUDFLARE_API_KEY": "cloudflare_api_key",
        "ZEN_API_KEY": "zen_api_key",
        "TAVILY_API_KEY": "tavily_api_key",
        "LANGFUSE_PUBLIC_KEY": "langfuse_public_key",
        "LANGFUSE_SECRET_KEY": "langfuse_secret_key",
        "LANGFUSE_HOST": "langfuse_host",
        "HTTP_PROXY": "http_proxy",
        "HTTPS_PROXY": "https_proxy",
    }

    # 需要从环境变量加载的所有 key（含大小写变体）
    _ENV_KEYS_TO_CHECK = list(_KEY_MAP.keys()) + [
        "API_KEY", "NANOGENESIS_DEBUG", "http_proxy", "https_proxy"
    ]

    def _load_env_vars(self):
        """加载系统环境变量（仅检查已知 key，避免遍历全量 environ）"""
        for key in self._ENV_KEYS_TO_CHECK:
            val = os.environ.get(key)
            if val is not None:
                self._set_config_by_key(key, val)

    def _set_config_by_key(self, key: str, val: str):
        """根据键名映射到配置对象"""
        upper_key = key.upper()

        # 通用映射
        attr = self._KEY_MAP.get(upper_key)
        if attr:
            setattr(self._config, attr, val)
            return

        # 特殊情况：API_KEY 作为 deepseek 的 fallback
        if upper_key == "API_KEY":
            if not self._config.deepseek_api_key:
                self._config.deepseek_api_key = val
        # 代理的小写变体也需要处理（_load_env_vars 原样传入 key）
        elif key in ("http_proxy",):
            self._config.http_proxy = val
        elif key in ("https_proxy",):
            self._config.https_proxy = val
        elif upper_key == "NANOGENESIS_DEBUG":
            self._config.debug = (val.lower() == "true")

    def _apply_proxies(self):
        """将代理配置应用到当前进程环境
        ⚠️ 注意：provider.py 的 httpx 客户端使用 trust_env=False 绕过此处注入的代理，
        以避免国内 API（DeepSeek）绕道代理 +11s 延迟。墙外免费池（groq/cloudflare）
        因此无法通过代理访问。参见 provider.py:_get_http_client()。
        """
        if self._config.http_proxy:
            os.environ['http_proxy'] = self._config.http_proxy
            os.environ['HTTP_PROXY'] = self._config.http_proxy
            logger.info(f"🌐 自动注入 HTTP Proxy: {self._config.http_proxy}")
            
        if self._config.https_proxy:
            os.environ['https_proxy'] = self._config.https_proxy
            os.environ['HTTPS_PROXY'] = self._config.https_proxy
            logger.info(f"🌐 自动注入 HTTPS Proxy: {self._config.https_proxy}")

    def _validate(self):
        """验证必要配置"""
        if not self._config.deepseek_api_key:
            logger.warning("⚠️ 未检测到 DeepSeek API Key (将仅使用本地大脑)")
        
        if not self._config.http_proxy and not self._config.https_proxy:
            # 检查是否有 curl
            pass

# 全局单例
config = ConfigManager().config
