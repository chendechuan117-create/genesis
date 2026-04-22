
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
    "xcode": "xcode_api_key",
    "xcode_backup": "xcode_api_key",
    "deepseek": "deepseek_api_key",
    "xcode_responses": "xcode_api_key",
    "newshrimp": "newshrimp_api_key",
    "newshrimp_backup": "newshrimp_api_key",
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
        self.active_provider_name = 'xcode'
        self._preferred_provider_name: Optional[str] = None  # 首选 provider
        self._failover_time: float = 0  # 上次 failover 时间戳
        self._last_recovery_attempt: float = 0  # 上次探活时间戳
        self._last_refresh_time: float = time.time()  # 上次刷新时间
        self._last_schedule_check: float = 0  # 上次时段调度检查
        
        self._initialize_providers(api_key, base_url, model)
        self.active_provider = self.providers.get(self.active_provider_name)
        self._preferred_provider_name = self.active_provider_name
        
        # Fallback if no configured provider is available
        if not self.active_provider:
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
                
                required_attr = PROVIDER_KEY_MAP.get(name)
                if required_attr and getattr(self.config, required_attr, None):
                    self.providers[name] = provider_instance
                    logger.info(f"Initialized Provider from Registry: {name}")
                             
            except Exception as e:
                logger.warning(f"Failed to build provider plugin '{name}': {e}")
        
        self.failover_order = [
            name for name in ['newshrimp', 'newshrimp_backup', 'xcode', 'xcode_backup', 'deepseek'] if name in self.providers
        ]
        self.active_provider_name = self._get_scheduled_provider()
                
    # ── 时段调度：7-24 newshrimp, 0-7 xcode ──
    _DAYTIME_PROVIDER = "newshrimp"    # 7:00-24:00 首选
    _NIGHTTIME_PROVIDER = "xcode"      # 0:00-7:00 首选
    _SCHEDULE_CHECK_INTERVAL = 300     # 每5分钟检查一次时段切换

    def _get_scheduled_provider(self) -> str:
        """根据当前小时返回首选 provider (北京时间 UTC+8)
        7:00-24:00 北京时间 = newshrimp → UTC 23:00-16:00 (跨日)
        0:00-7:00  北京时间 = xcode     → UTC 16:00-23:00
        """
        from datetime import datetime, timezone, timedelta
        bj_hour = (datetime.now(timezone(timedelta(hours=8)))).hour
        if 7 <= bj_hour < 24:
            preferred = self._DAYTIME_PROVIDER
        else:
            preferred = self._NIGHTTIME_PROVIDER
        # 如果首选不可用，回退到 failover_order 第一个
        if preferred in self.providers:
            return preferred
        return self.failover_order[0] if self.failover_order else 'xcode'

    def _check_schedule_switch(self):
        """时段切换检查：如果当前首选与调度不符，切换"""
        scheduled = self._get_scheduled_provider()
        if scheduled != self._preferred_provider_name:
            logger.info(f"🕐 时段切换: {self._preferred_provider_name} -> {scheduled}")
            self._preferred_provider_name = scheduled
            if scheduled in self.providers:
                self._switch_provider(scheduled)
                self._failover_time = 0

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

        # 时段调度检查：每5分钟检查是否需要切换首选 provider
        if (time.time() - self._last_schedule_check) > self._SCHEDULE_CHECK_INTERVAL:
            self._last_schedule_check = time.time()
            self._check_schedule_switch()

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
        """Returns the active provider (xcode only)."""
        return self.active_provider

