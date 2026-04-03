
import logging
import asyncio
import time
from typing import Dict, Any, List, Optional
from genesis.core.provider import NativeHTTPProvider, MockLLMProvider
from genesis.core.registry import provider_registry
from genesis.core.base import LLMProvider
from genesis.core.provider import WallClockTimeoutError, LLMResponse
from genesis.core.tracer import Tracer
# Ensure providers are loaded
import genesis.providers
logger = logging.getLogger(__name__)

# provider_name -> config attribute that must be truthy for it to be valid
PROVIDER_KEY_MAP = {
    "aixj": "aixj_api_key",
    "aixj_responses": "aixj_api_key",
    "codex": "codex_api_key",
    "deepseek": "deepseek_api_key",
    "gemini": "gemini_api_key",
    "openai": "openai_api_key",
    "openrouter": "openrouter_api_key",
    "sambanova": "sambanova_api_key",
    "siliconflow": "siliconflow_api_key",
    "dashscope": "dashscope_api_key",
    "qianfan": "qianfan_api_key",
    "zhipu": "zhipu_api_key",
    "groq": "groq_api_key",
    "cloudflare": "cloudflare_api_key",
    "zen": "zen_api_key"
}

class ProviderRouter(LLMProvider):
    """
    Provider Router - Manages multiple LLM providers and handles failover.
    Decouples the 'brain' logic from the Agent body.
    Implements LLMProvider interface so it can be passed directly to Genesis.
    """
    
    # 回退探活：failover 后每隔此秒数尝试恢复首选 provider
    RECOVERY_COOLDOWN_SECS = 60
    # 每小时刷新 provider 连接，防止长连接腐化
    REFRESH_INTERVAL_SECS = 3600

    def __init__(self, config: Any, api_key: str = None, base_url: str = None, model: str = None):
        self.config = config
        self.providers: Dict[str, Any] = {}
        self.active_provider_name = 'aixj'
        self._preferred_provider_name: Optional[str] = None  # 首选 provider
        self._failover_time: float = 0  # 上次 failover 时间戳
        self._last_recovery_attempt: float = 0  # 上次探活时间戳
        self._last_refresh_time: float = time.time()  # 上次刷新时间
        
        self._initialize_providers(api_key, base_url, model)
        self.active_provider = self.providers.get(self.active_provider_name)
        self._preferred_provider_name = self.active_provider_name
        
        # Fallback if preferred provider not available
        if not self.active_provider:
            if 'gemini' in self.providers:
                self._switch_provider('gemini')
            else:
                 # Last resort mock
                 self.providers['mock'] = MockLLMProvider()
                 self._switch_provider('mock')

    def _initialize_providers(self, api_key: str, base_url: str, model: str):
        """Initialize all available providers based on the dynamically registered factories"""
        
        for name in provider_registry.list_providers():
            builder = provider_registry.get_builder(name)
            if not builder:
                continue
            try:
                provider_instance = builder(self.config)
                if not provider_instance:
                    continue
                    
                # Legacy override: explicit runtime key for deepseek
                if name == "deepseek" and api_key:
                    provider_instance.api_key = api_key
                
                # Validate: each provider needs its OWN config key
                required_attr = PROVIDER_KEY_MAP.get(name)
                is_valid = (
                    (name == "deepseek" and api_key)
                    or (required_attr and getattr(self.config, required_attr, None))
                )
                
                if is_valid:
                    self.providers[name] = provider_instance
                    logger.info(f"Initialized Provider from Registry: {name}")
                             
            except Exception as e:
                logger.warning(f"Failed to build provider plugin '{name}': {e}")
        
        # Determine Activation & Failover Order
        # deepseek 默认不参与自动 failover（烧付费额度）
        # 设置 GENESIS_DEEPSEEK_FAILOVER=1 可手动启用
        import os
        if os.environ.get('GENESIS_DEEPSEEK_FAILOVER') == '1':
            self.failover_order = ['aixj', 'codex', 'deepseek', 'gemini']
        else:
            self.failover_order = ['aixj', 'codex', 'gemini']
        
        self.active_provider_name = 'aixj'
        for name in self.failover_order:
            if name in self.providers:
                self.active_provider_name = name
                break
                
    def _switch_provider(self, target: str):
        """Switch active provider"""
        if target not in self.providers:
            # logger.error(f"Cannot switch to unknown provider: {target}")
            return False
            
        if target == self.active_provider_name:
            return True
            
        logger.warning(f"⚠️ Switching Provider: {self.active_provider_name} -> {target}")
        self.active_provider_name = target
        self.active_provider = self.providers[target]
        return True

    async def chat(self, messages: List[Dict], **kwargs) -> Any:
        """Wrapper for chat with dynamic failover and tracing"""
        if not self.active_provider:
             raise RuntimeError("No active provider available")

        tracer = Tracer.get_instance()
        trace_id = kwargs.pop("_trace_id", None) or ""
        trace_phase = kwargs.pop("_trace_phase", "") or ""
        trace_parent = kwargs.pop("_trace_parent", None)
        model = kwargs.get("model") or self.get_default_model()

        t0 = time.time()

        # 每小时刷新连接：关闭旧 httpx client，下次请求自动重建
        if (time.time() - self._last_refresh_time) > self.REFRESH_INTERVAL_SECS:
            self._last_refresh_time = time.time()
            for name, prov in self.providers.items():
                if hasattr(prov, '_http_client') and prov._http_client:
                    try:
                        await prov._http_client.aclose()
                    except Exception:
                        pass
                    prov._http_client = None
            logger.info("🔄 Provider connections refreshed (hourly)")

        # 回退探活：如果当前不是首选 provider，定期用轻量 ping 尝试恢复
        if (
            self._preferred_provider_name
            and self.active_provider_name != self._preferred_provider_name
            and self._preferred_provider_name in self.providers
            and (time.time() - self._last_recovery_attempt) > self.RECOVERY_COOLDOWN_SECS
        ):
            self._last_recovery_attempt = time.time()
            try:
                probe_provider = self.providers[self._preferred_provider_name]
                _probe_msgs = [{"role": "user", "content": "ping"}]
                _probe_kwargs = {k: v for k, v in kwargs.items() if k not in ("tools", "stream", "stream_callback")}
                _probe_kwargs["max_tokens"] = 1
                await probe_provider.chat(messages=_probe_msgs, **_probe_kwargs)
                # 探活成功，恢复首选（不返回 probe 结果，继续走正常路径用真实消息）
                self._switch_provider(self._preferred_provider_name)
                self._failover_time = 0
                logger.info(f"✅ Provider recovered: back to {self._preferred_provider_name}")
            except Exception as probe_e:
                logger.debug(f"Recovery probe to {self._preferred_provider_name} failed: {probe_e}")

        # Try active first
        try:
            result = await self.active_provider.chat(messages=messages, **kwargs)
            dur = (time.time() - t0) * 1000
            if trace_id:
                tracer.log_llm_call(
                    trace_id, parent=trace_parent, phase=trace_phase,
                    model=model,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    total_tokens=result.total_tokens,
                    cache_hit_tokens=getattr(result, 'prompt_cache_hit_tokens', 0),
                    duration_ms=dur,
                    has_tool_calls=result.has_tool_calls
                )
            return result
        except WallClockTimeoutError:
            raise  # 总超时不是 provider 故障，直接上抛，不触发 failover
        except Exception as e:
            err_str = str(e)
            logger.error(f"Provider {self.active_provider_name} Failed: {e}")
            
            # 400 = 客户端格式错误，换 provider 也修不了，直接上抛
            if "400" in err_str or "invalid_request_error" in err_str:
                raise
            
            self._failover_time = time.time()
            
            # Dynamic Failover (仅对 5xx / 网络 / 超时等服务端故障)
            current_index = -1
            try:
                current_index = self.failover_order.index(self.active_provider_name)
            except ValueError:
                pass
                
            # Try next providers in the list
            start_index = current_index + 1
            for next_provider_name in self.failover_order[start_index:]:
                if next_provider_name in self.providers:
                     if self._switch_provider(next_provider_name):
                         logger.info(f"🔄 Failover Attempt: {next_provider_name}")
                         try:
                             result = await self.active_provider.chat(messages=messages, **kwargs)
                             dur = (time.time() - t0) * 1000
                             if trace_id:
                                 tracer.log_llm_call(
                                     trace_id, parent=trace_parent, phase=trace_phase,
                                     model=model + f"(failover:{next_provider_name})",
                                     input_tokens=result.input_tokens,
                                     output_tokens=result.output_tokens,
                                     total_tokens=result.total_tokens,
                                     cache_hit_tokens=getattr(result, 'prompt_cache_hit_tokens', 0),
                                     duration_ms=dur,
                                     has_tool_calls=result.has_tool_calls
                                 )
                             return result
                         except Exception as e2:
                             logger.error(f"Backup Provider {next_provider_name} also failed: {e2}")
                             continue # Try next
            
            dur = (time.time() - t0) * 1000
            if trace_id:
                tracer.log_llm_call(
                    trace_id, parent=trace_parent, phase=trace_phase,
                    model=model, duration_ms=dur,
                    error=str(e)
                )
            # If all failed
            raise e
    
    # Delegate standard provider methods to active provider
    
    def get_default_model(self) -> str:
        if self.active_provider:
            return self.active_provider.get_default_model()
        return "unknown"
        
    def get_active_provider(self):
        return self.active_provider

    def get_consumable_provider(self):
        """Returns the first available cheap/free provider from the consumables pool.
        Deprecated: 新代码请用 FreePoolManager。保留此方法供旧调用方兼容。"""
        pool = FreePoolManager.get_instance(self)
        name, provider = pool.get_best_provider()
        return provider


# ════════════════════════════════════════════════════════════
#  FreePoolManager — 傻瓜式免费池自管理
#  单一注册表 + 健康追踪 + 周期性重探 + deepseek 限频兜底
# ════════════════════════════════════════════════════════════

class FreePoolManager:
    """
    免费 LLM 池的统一管理器（单例）。
    
    设计目标：
    1. 单一注册表 — 免费 provider 列表只在这里定义一次
    2. 健康追踪 — 每个 provider 记录 success/fail 计数，自动计算健康分
    3. 周期性重探 — 死掉的 provider 每 REPROBE_INTERVAL 秒重试一次
    4. 自动排序 — 按健康分降序，优先用最稳定的
    5. deepseek 兜底 — 所有免费池失败时，用 deepseek 但限频
    
    用法：
        pool = FreePoolManager.get_instance(router)
        name, provider = pool.get_best_provider()
        try:
            result = await provider.chat(...)
            pool.report_success(name)
        except:
            pool.report_failure(name)
    """
    
    _instance = None
    
    # ── 免费池注册表（唯一定义处）──
    FREE_POOL_NAMES = ["groq", "cloudflare", "siliconflow", "dashscope", "zhipu", "qianfan", "zen"]
    
    # ── 配置 ──
    REPROBE_INTERVAL = 600       # 死亡 provider 重探间隔（秒）
    DEAD_THRESHOLD = 3           # 连续失败 N 次标记为 dead
    DEEPSEEK_HOURLY_LIMIT = 20   # deepseek 兜底每小时最多 N 次调用
    
    @classmethod
    def get_instance(cls, router: 'ProviderRouter') -> 'FreePoolManager':
        if cls._instance is None:
            cls._instance = cls(router)
        return cls._instance
    
    def __init__(self, router: 'ProviderRouter'):
        self.router = router
        self._health: Dict[str, Dict[str, Any]] = {}
        self._deepseek_calls_this_hour: int = 0
        self._deepseek_hour_start: float = time.time()
        self._probed = False
        
        # 初始化健康记录
        for name in self.FREE_POOL_NAMES:
            if name in router.providers:
                self._health[name] = {
                    "success": 0,
                    "fail": 0,
                    "consecutive_fail": 0,
                    "dead": False,
                    "last_fail_at": 0.0,
                    "last_success_at": 0.0,
                }
        
        available = list(self._health.keys())
        if available:
            logger.info(f"FreePool: {len(available)} providers registered: {', '.join(available)}")
        else:
            logger.warning("FreePool: no free providers available!")
    
    async def probe_all(self):
        """并行探活所有 provider，更新健康状态。"""
        logger.info("FreePool: probing all providers (parallel)...")
        
        async def _probe_one(name: str):
            provider = self.router.providers.get(name)
            if not provider:
                return
            try:
                await asyncio.wait_for(
                    provider.chat(messages=[{"role": "user", "content": "ping"}], stream=False),
                    timeout=15
                )
                self._health[name]["dead"] = False
                self._health[name]["consecutive_fail"] = 0
                self._health[name]["last_success_at"] = time.time()
                self._health[name]["success"] += 1
                logger.info(f"  ✅ {name}: alive")
            except Exception as e:
                self._health[name]["dead"] = True
                self._health[name]["consecutive_fail"] += 1
                self._health[name]["last_fail_at"] = time.time()
                self._health[name]["fail"] += 1
                logger.warning(f"  ❌ {name}: {type(e).__name__}: {str(e)[:60]}")
        
        await asyncio.gather(*[_probe_one(n) for n in list(self._health.keys())])
        
        self._probed = True
        alive = [n for n, h in self._health.items() if not h["dead"]]
        logger.info(f"FreePool: {len(alive)}/{len(self._health)} alive: {', '.join(alive) or 'NONE'}")
    
    def report_success(self, name: str):
        """调用成功反馈"""
        h = self._health.get(name)
        if h:
            h["success"] += 1
            h["consecutive_fail"] = 0
            h["dead"] = False
            h["last_success_at"] = time.time()
    
    def report_failure(self, name: str):
        """调用失败反馈"""
        h = self._health.get(name)
        if h:
            h["fail"] += 1
            h["consecutive_fail"] += 1
            h["last_fail_at"] = time.time()
            if h["consecutive_fail"] >= self.DEAD_THRESHOLD:
                h["dead"] = True
                logger.warning(f"FreePool: {name} marked DEAD ({h['consecutive_fail']} consecutive failures)")
    
    def _health_score(self, name: str) -> float:
        """计算健康分（越高越好）"""
        h = self._health[name]
        if h["dead"]:
            return -1.0
        total = h["success"] + h["fail"]
        if total == 0:
            return 0.5  # 未知 = 中等优先级
        return h["success"] / total
    
    def get_best_provider(self) -> tuple:
        """返回 (name, provider)。按健康分排序，优先返回最健康的。
        所有免费池不可用时返回 deepseek 兜底（受限频）。
        返回 (None, None) 表示完全不可用。"""
        
        # 检查是否需要重探死亡 provider
        now = time.time()
        for name, h in self._health.items():
            if h["dead"] and (now - h["last_fail_at"]) > self.REPROBE_INTERVAL:
                h["dead"] = False  # 解除死亡标记，给一次机会
                h["consecutive_fail"] = 0
                logger.info(f"FreePool: {name} un-dead for re-probe (cooldown elapsed)")
        
        # 按健康分排序
        ranked = sorted(self._health.keys(), key=lambda n: self._health_score(n), reverse=True)
        
        for name in ranked:
            if not self._health[name]["dead"]:
                provider = self.router.providers.get(name)
                if provider:
                    return (name, provider)
        
        # 所有免费 provider 都 dead → 不兜底，不烧付费额度
        logger.warning("FreePool: all free providers dead. No fallback (deepseek disabled).")
        return (None, None)
    
    def _deepseek_fallback(self) -> tuple:
        """deepseek 限频兜底"""
        now = time.time()
        # 每小时重置计数
        if now - self._deepseek_hour_start > 3600:
            self._deepseek_calls_this_hour = 0
            self._deepseek_hour_start = now
        
        if self._deepseek_calls_this_hour >= self.DEEPSEEK_HOURLY_LIMIT:
            logger.warning(f"FreePool: deepseek hourly limit reached ({self.DEEPSEEK_HOURLY_LIMIT}/h). No provider available.")
            return (None, None)
        
        ds = self.router.providers.get("deepseek")
        if ds:
            self._deepseek_calls_this_hour += 1
            logger.info(f"FreePool: all free dead, using deepseek fallback ({self._deepseek_calls_this_hour}/{self.DEEPSEEK_HOURLY_LIMIT} this hour)")
            return ("deepseek", ds)
        
        return (None, None)
    
    def get_status(self) -> Dict[str, Any]:
        """返回池状态摘要（供 heartbeat / 诊断）"""
        alive = []
        dead = []
        for name, h in self._health.items():
            entry = {"name": name, "score": round(self._health_score(name), 2),
                     "success": h["success"], "fail": h["fail"]}
            if h["dead"]:
                dead.append(entry)
            else:
                alive.append(entry)
        return {
            "alive": sorted(alive, key=lambda x: x["score"], reverse=True),
            "dead": dead,
            "deepseek_fallback_used": self._deepseek_calls_this_hour,
            "deepseek_hourly_limit": self.DEEPSEEK_HOURLY_LIMIT,
            "probed": self._probed,
        }
