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
    deepseek_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    openrouter_model: Optional[str] = "trinity-large-preview"
    
    # Consumables Pool (Phase 3)
    siliconflow_api_key: Optional[str] = None
    dashscope_api_key: Optional[str] = None
    qianfan_api_key: Optional[str] = None
    zhipu_api_key: Optional[str] = None
    
    tavily_api_key: Optional[str] = None
    
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
        # 1. 尝试加载 OpenClaw 宿主配置 (最底层)
        self._load_openclaw_config()
        
        # 2. 加载 .env (中间层)
        self._load_dotenv()
        
        # 3. 加载环境变量 (最高优)
        self._load_env_vars()
        
        # 4. 验证核心凭证
        self._validate()

    def _load_openclaw_config(self):
        """寄生模式：读取 OpenClaw 配置文件"""
        try:
            # 标准路径
            openclaw_path = Path.home() / ".local/share/openclaw/openclaw.json"
            if not openclaw_path.exists():
                return
                
            logger.info(f"🧬 检测到 OpenClaw 宿主配置: {openclaw_path}")
            with open(openclaw_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # 提取 Proxy
            if 'env' in data and 'vars' in data['env']:
                env_vars = data['env']['vars']
                self._config.http_proxy = env_vars.get('HTTP_PROXY') or env_vars.get('http_proxy')
                self._config.https_proxy = env_vars.get('HTTPS_PROXY') or env_vars.get('https_proxy')
                
            # 提取 API Key (DeepSeek)
            if 'models' in data and 'providers' in data['models']:
                providers = data['models']['providers']
                if 'deepseek' in providers:
                    self._config.deepseek_api_key = providers['deepseek'].get('apiKey')
            
            logger.info("✓ 已从 OpenClaw 继承配置 (API Key, Proxy)")
            
        except Exception as e:
            logger.warning(f"读取 OpenClaw 配置失败: {e}")

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
        "DEEPSEEK_API_KEY": "deepseek_api_key",
        "OPENAI_API_KEY": "openai_api_key",
        "OPENROUTER_API_KEY": "openrouter_api_key",
        "OPENROUTER_MODEL": "openrouter_model",
        "SILICONFLOW_API_KEY": "siliconflow_api_key",
        "DASHSCOPE_API_KEY": "dashscope_api_key",
        "QIANFAN_API_KEY": "qianfan_api_key",
        "ZHIPU_API_KEY": "zhipu_api_key",
        "TAVILY_API_KEY": "tavily_api_key",
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
        """将代理配置应用到当前进程环境"""
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
