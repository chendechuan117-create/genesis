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
    telegram_bot_token: Optional[str] = None
    github_token: Optional[str] = None
    
    # Network & Limits
    http_proxy: Optional[str] = None
    https_proxy: Optional[str] = None
    connect_timeout: int = 15
    request_timeout: int = 120
    max_iterations: int = 10
    
    # Paths
    workspace_root: Path = Path.cwd()
    memory_path: Path = Path.cwd() / "memory"
    
    # System
    debug: bool = False
    language: str = "zh"

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
            
            # 提取 Telegram Token
            if 'channels' in data and 'telegram' in data['channels']:
                tg = data['channels']['telegram']
                if tg.get('enabled'):
                    self._config.telegram_bot_token = tg.get('botToken')
                    # 如果有专用代理配置
                    if tg.get('proxy'):
                         # 优先使用专用代理，或者仅当全局未设置时使用
                         if not self._config.http_proxy:
                             self._config.http_proxy = tg.get('proxy')
                             self._config.https_proxy = tg.get('proxy')

            logger.info("✓ 已从 OpenClaw 继承配置 (API Key, Proxy, Telegram)")
            
        except Exception as e:
            logger.warning(f"读取 OpenClaw 配置失败: {e}")

    def _load_dotenv(self):
        """加载 .env 文件"""
        # 简单实现，避免引入 python-dotenv 依赖
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

    def _load_env_vars(self):
        """加载系统环境变量"""
        for key, val in os.environ.items():
            self._set_config_by_key(key, val)

    def _set_config_by_key(self, key: str, val: str):
        """根据键名映射到配置对象"""
        key = key.upper()
        if key == "DEEPSEEK_API_KEY":
            self._config.deepseek_api_key = val
        elif key == "OPENAI_API_KEY":
            self._config.openai_api_key = val
        elif key == "API_KEY":
            if not self._config.deepseek_api_key:
                self._config.deepseek_api_key = val
        elif key == "OPENROUTER_API_KEY":
            self._config.openrouter_api_key = val
        elif key == "OPENROUTER_MODEL":
            self._config.openrouter_model = val
            
        # Consumable Keys
        elif key == "SILICONFLOW_API_KEY":
            self._config.siliconflow_api_key = val
        elif key == "DASHSCOPE_API_KEY":
            self._config.dashscope_api_key = val
        elif key == "QIANFAN_API_KEY":
            self._config.qianfan_api_key = val
        elif key == "ZHIPU_API_KEY":
            self._config.zhipu_api_key = val
            
        elif key == "TAVILY_API_KEY":
            self._config.tavily_api_key = val
        elif key == "TELEGRAM_BOT_TOKEN":
            self._config.telegram_bot_token = val
        elif key == "GITHUB_TOKEN":
            self._config.github_token = val
        elif key in ["HTTP_PROXY", "http_proxy"]:
            self._config.http_proxy = val
        elif key in ["HTTPS_PROXY", "https_proxy"]:
            self._config.https_proxy = val
        elif key == "NANOGENESIS_DEBUG":
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
