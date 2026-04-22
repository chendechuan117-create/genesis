"""
配置管理中枢 - NanoGenesis Nervous System
实现零配置启动 (Zero-Conf)，自动嗅探宿主环境 (OpenClaw) 和系统变量。
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class GlobalConfig:
    """全局配置对象"""
    # API Keys
    xcode_api_key: Optional[str] = None
    xcode_api_keys: List[str] = None
    xcode_base_url: Optional[str] = None
    xcode_backup_base_url: Optional[str] = None
    xcode_host_header: Optional[str] = None
    xcode_backup_host_header: Optional[str] = None
    xcode_ssl_verify: bool = True
    xcode_backup_ssl_verify: bool = True
    xcode_model: str = "gpt-5.4"
    deepseek_api_key: Optional[str] = None
    
    # NewShrimp provider
    newshrimp_api_key: Optional[str] = None
    newshrimp_base_url: Optional[str] = None
    newshrimp_backup_base_url: Optional[str] = None
    newshrimp_model: Optional[str] = None
    newshrimp_ssl_verify: bool = True
    newshrimp_backup_ssl_verify: bool = True
    
    tavily_api_key: Optional[str] = None
    
    # Observability (optional)
    langfuse_public_key: Optional[str] = None
    langfuse_secret_key: Optional[str] = None
    langfuse_host: Optional[str] = "https://cloud.langfuse.com"
    
    # Network & Limits
    http_proxy: Optional[str] = None
    https_proxy: Optional[str] = None
    no_proxy: Optional[str] = None
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
        "XCODE_API_KEY": "xcode_api_key",
        "XCODE_API_KEYS": "xcode_api_keys",
        "XCODE_BASE_URL": "xcode_base_url",
        "XCODE_BACKUP_BASE_URL": "xcode_backup_base_url",
        "XCODE_HOST_HEADER": "xcode_host_header",
        "XCODE_BACKUP_HOST_HEADER": "xcode_backup_host_header",
        "XCODE_SSL_VERIFY": "xcode_ssl_verify",
        "XCODE_BACKUP_SSL_VERIFY": "xcode_backup_ssl_verify",
        "XCODE_MODEL": "xcode_model",
        "AIXJ_API_KEY": "xcode_api_key",
        "AIXJ_API_KEYS": "xcode_api_keys",
        "AIXJ_BASE_URL": "xcode_base_url",
        "AIXJ_BACKUP_BASE_URL": "xcode_backup_base_url",
        "AIXJ_MODEL": "xcode_model",
        "DEEPSEEK_API_KEY": "deepseek_api_key",
        "NEWSHRIMP_API_KEY": "newshrimp_api_key",
        "NEWSHRIMP_BASE_URL": "newshrimp_base_url",
        "NEWSHRIMP_BACKUP_BASE_URL": "newshrimp_backup_base_url",
        "NEWSHRIMP_MODEL": "newshrimp_model",
        "NEWSHRIMP_SSL_VERIFY": "newshrimp_ssl_verify",
        "NEWSHRIMP_BACKUP_SSL_VERIFY": "newshrimp_backup_ssl_verify",
        "TAVILY_API_KEY": "tavily_api_key",
        "LANGFUSE_PUBLIC_KEY": "langfuse_public_key",
        "LANGFUSE_SECRET_KEY": "langfuse_secret_key",
        "LANGFUSE_HOST": "langfuse_host",
        "HTTP_PROXY": "http_proxy",
        "HTTPS_PROXY": "https_proxy",
        "NO_PROXY": "no_proxy",
    }

    # 需要从环境变量加载的所有 key（含大小写变体）
    _ENV_KEYS_TO_CHECK = list(_KEY_MAP.keys()) + [
        "NANOGENESIS_DEBUG", "http_proxy", "https_proxy", "no_proxy"
    ]

    def _load_env_vars(self):
        """加载系统环境变量（仅检查已知 key，避免遍历全量 environ）"""
        proxy_preferred_values = {}
        for key in self._ENV_KEYS_TO_CHECK:
            val = os.environ.get(key)
            if val is None:
                continue
            upper_key = key.upper()
            if upper_key in {"HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"}:
                proxy_preferred_values.setdefault(upper_key, val)
                continue
            self._set_config_by_key(key, val)

        for upper_key, val in proxy_preferred_values.items():
            self._set_config_by_key(upper_key, val)

    def _set_config_by_key(self, key: str, val: str):
        """根据键名映射到配置对象"""
        upper_key = key.upper()

        # 通用映射
        attr = self._KEY_MAP.get(upper_key)
        if attr:
            if upper_key in ("XCODE_API_KEYS", "AIXJ_API_KEYS"):
                keys = [k.strip() for k in val.split(",") if k.strip()]
                setattr(self._config, "xcode_api_keys", keys)
                if keys and not self._config.xcode_api_key:
                    self._config.xcode_api_key = keys[0]
            elif upper_key in ("XCODE_SSL_VERIFY", "XCODE_BACKUP_SSL_VERIFY", "NEWSHRIMP_SSL_VERIFY", "NEWSHRIMP_BACKUP_SSL_VERIFY"):
                setattr(self._config, attr, val.strip().lower() not in ("0", "false", "no", "off", ""))
            else:
                setattr(self._config, attr, val)
            return

        # 代理的小写变体也需要处理（_load_env_vars 原样传入 key）
        elif key in ("http_proxy",):
            self._config.http_proxy = val
        elif key in ("https_proxy",):
            self._config.https_proxy = val
        elif key in ("no_proxy",):
            self._config.no_proxy = val
        elif upper_key == "NANOGENESIS_DEBUG":
            self._config.debug = (val.lower() == "true")

    def _apply_proxies(self):
        """将代理配置应用到当前进程环境
        2026-03-26: v2rayA tproxy 在内核层做 GeoIP 智能分流，不再需要应用层代理。
        保留此方法以防万一需要临时回滚，但 .env 中已无 HTTPS_PROXY。
        """
        if self._config.http_proxy:
            os.environ['http_proxy'] = self._config.http_proxy
            os.environ['HTTP_PROXY'] = self._config.http_proxy
            logger.info(f"🌐 自动注入 HTTP Proxy: {self._config.http_proxy}")
            
        if self._config.https_proxy:
            os.environ['https_proxy'] = self._config.https_proxy
            os.environ['HTTPS_PROXY'] = self._config.https_proxy
            logger.info(f"🌐 自动注入 HTTPS Proxy: {self._config.https_proxy}")

        if self._config.no_proxy:
            os.environ['no_proxy'] = self._config.no_proxy
            os.environ['NO_PROXY'] = self._config.no_proxy
            logger.info(f"🌐 自动注入 NO_PROXY: {self._config.no_proxy}")

    def _validate(self):
        """验证必要配置"""
        if not self._config.xcode_api_key and not self._config.deepseek_api_key and not self._config.newshrimp_api_key:
            logger.warning("⚠️ 未检测到 xcode / deepseek / newshrimp API Key")
        
        if not self._config.http_proxy and not self._config.https_proxy:
            # 检查是否有 curl
            pass

# 全局单例
config = ConfigManager().config
