"""
Asyncio 并发和速率限制器
支持最大并发数和每秒最大请求数限制
"""

import asyncio
import time
from typing import Optional
from contextlib import asynccontextmanager


class AsyncLimiter:
    """
    Asyncio 并发和速率限制器
    
    支持两种限制：
    1. 最大并发数限制
    2. 每秒最大请求数（速率）限制
    
    使用示例：
    ```python
    limiter = AsyncLimiter(max_concurrent=5, max_rate=10)  # 最大5并发，每秒10个请求
    
    async def make_request():
        async with limiter:
            # 执行受限制的操作
            await do_something()
    ```
    """
    
    def __init__(self, max_concurrent: int, max_rate: float):
        """
        初始化限制器
        
        Args:
            max_concurrent: 最大并发数
            max_rate: 每秒最大请求数
        """
        if max_concurrent <= 0:
            raise ValueError("max_concurrent must be positive")
        if max_rate <= 0:
            raise ValueError("max_rate must be positive")
        
        self.max_concurrent = max_concurrent
        self.max_rate = max_rate
        
        # 并发控制信号量
        self._semaphore = asyncio.Semaphore(max_concurrent)
        
        # 速率控制相关
        self._rate_per_token = 1.0 / max_rate  # 每个令牌的时间间隔（秒）
        self._tokens = 0.0  # 当前可用令牌数
        self._last_update = self._get_monotonic_time()  # 上次更新时间
        
        # 用于保护速率控制变量的锁
        self._rate_lock = asyncio.Lock()
        
        # 跟踪活跃任务，用于调试和监控
        self._active_count = 0
        self._active_lock = asyncio.Lock()
    
    def _get_monotonic_time(self) -> float:
        """获取单调时钟时间，避免系统时间变化影响"""
        return time.monotonic()
    
    async def _add_tokens(self) -> None:
        """根据时间流逝添加令牌"""
        now = self._get_monotonic_time()
        elapsed = now - self._last_update
        
        # 计算应添加的令牌数
        new_tokens = elapsed / self._rate_per_token
        if new_tokens > 0:
            self._tokens = min(self.max_rate, self._tokens + new_tokens)
            self._last_update = now
    
    async def _acquire_rate_permit(self) -> None:
        """获取速率许可"""
        async with self._rate_lock:
            await self._add_tokens()
            
            # 如果没有可用令牌，需要等待
            if self._tokens < 1.0:
                # 计算需要等待的时间
                deficit = 1.0 - self._tokens
                wait_time = deficit * self._rate_per_token
                
                # 消耗令牌并更新时间
                self._tokens = 0.0
                self._last_update += wait_time
                
                # 等待所需时间
                await asyncio.sleep(wait_time)
            else:
                # 消耗一个令牌
                self._tokens -= 1.0
    
    async def acquire(self) -> None:
        """
        获取许可（先获取速率许可，再获取并发许可）
        
        注意：建议使用 async with 语法而不是直接调用此方法
        """
        # 先获取速率许可
        await self._acquire_rate_permit()
        
        # 再获取并发许可
        await self._semaphore.acquire()
        
        # 更新活跃计数
        async with self._active_lock:
            self._active_count += 1
    
    async def release(self) -> None:
        """释放并发许可（速率许可自动过期）"""
        # 更新活跃计数
        async with self._active_lock:
            self._active_count -= 1
        
        # 释放并发许可
        self._semaphore.release()
    
    async def __aenter__(self):
        """进入上下文管理器"""
        await self.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出上下文管理器"""
        await self.release()
    
    @asynccontextmanager
    async def context(self):
        """提供上下文管理器接口（兼容旧代码）"""
        await self.acquire()
        try:
            yield
        finally:
            await self.release()
    
    @property
    def active_count(self) -> int:
        """当前活跃任务数"""
        return self._active_count
    
    @property
    def available_concurrent(self) -> int:
        """可用并发槽位数"""
        return self._semaphore._value
    
    @property
    def waiting_count(self) -> int:
        """等待并发许可的任务数"""
        # 信号量的等待队列长度
        return len(self._semaphore._waiters) if hasattr(self._semaphore, '_waiters') else 0


class RateLimiterOnly:
    """
    仅速率限制器（无并发限制）
    
    使用示例：
    ```python
    limiter = RateLimiterOnly(max_rate=10)  # 每秒10个请求
    
    async def make_request():
        async with limiter:
            await do_something()
    ```
    """
    
    def __init__(self, max_rate: float):
        """
        初始化速率限制器
        
        Args:
            max_rate: 每秒最大请求数
        """
        if max_rate <= 0:
            raise ValueError("max_rate must be positive")
        
        self.max_rate = max_rate
        self._rate_per_token = 1.0 / max_rate
        self._tokens = 0.0
        self._last_update = time.monotonic()
        self._lock = asyncio.Lock()
    
    def _get_monotonic_time(self) -> float:
        return time.monotonic()
    
    async def _add_tokens(self) -> None:
        now = self._get_monotonic_time()
        elapsed = now - self._last_update
        
        new_tokens = elapsed / self._rate_per_token
        if new_tokens > 0:
            self._tokens = min(self.max_rate, self._tokens + new_tokens)
            self._last_update = now
    
    async def acquire(self) -> None:
        """获取速率许可"""
        async with self._lock:
            await self._add_tokens()
            
            if self._tokens < 1.0:
                deficit = 1.0 - self._tokens
                wait_time = deficit * self._rate_per_token
                
                self._tokens = 0.0
                self._last_update += wait_time
                
                await asyncio.sleep(wait_time)
            else:
                self._tokens -= 1.0
    
    async def release(self) -> None:
        """速率许可自动过期，无需释放"""
        pass
    
    async def __aenter__(self):
        await self.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()