"""
诊断管理器 - System Health Monitor
负责检测网络连通性、Provider 状态、记忆库完整性等核心指标。
"""

import socket
import logging
import asyncio
import os
import time
from typing import Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)

class DiagnosticManager:
    """诊断管理器"""

    def __init__(self, provider_router=None, memory_store=None, tool_registry=None, context=None, scheduler=None):
        self.provider_router = provider_router
        self.memory = memory_store
        self.tool_registry = tool_registry
        self.context = context
        self.scheduler = scheduler

    async def run_all_checks(self) -> Dict[str, Any]:
        """运行所有检查"""
        report = {
            "timestamp": time.time(),
            "status": "healthy", # healthy, degraded, critical
            "checks": {}
        }
        
        # 1. 网络检查
        net_status = await self._check_network()
        report["checks"]["network"] = net_status
        
        # 2. Provider 检查
        if self.provider_router:
            prov_status = await self._check_provider()
            report["checks"]["provider"] = prov_status
            if prov_status["status"] == "error":
                report["status"] = "critical"
        
        # 3. 记忆库检查
        if self.memory:
            mem_status = await self._check_memory()
            report["checks"]["memory"] = mem_status
            if mem_status["status"] == "error":
                 report["status"] = "degraded"
                 
        # 4. 磁盘检查
        disk_status = self._check_disk()
        report["checks"]["disk"] = disk_status
        
        # 5. 工具库检查
        if self.tool_registry:
            tool_status = self._check_tools()
            report["checks"]["tools"] = tool_status
            
        # 6. 上下文检查 (Deep Audit)
        if self.context:
            ctx_status = self._check_context()
            report["checks"]["context"] = ctx_status
            
        # 7. 调度器检查
        if self.scheduler:
            sched_status = self._check_scheduler()
            report["checks"]["scheduler"] = sched_status
        
        return report

    def _check_tools(self) -> Dict[str, Any]:
        """检查核心工具状态"""
        if not self.tool_registry:
            return {"status": "skipped"}
            
        tools = self.tool_registry.list_tools()
        count = len(tools)
        
        # Check for critical tools
        critical = ['read_file', 'write_file', 'shell', 'save_memory']
        missing = [t for t in critical if t not in tools]
        
        status = "ok" if not missing else "warning"
        
        return {
            "status": status,
            "count": count,
            "missing": missing,
            "sample": tools[:5]
        }

    def _check_context(self) -> Dict[str, Any]:
        """检查上下文管道状态"""
        status = "ok"
        issues = []
        
        # 1. Check System Profile
        # logic from EnvironmentPlugin
        profile_found = False
        possible_paths = [
            Path(os.getcwd()) / "system_profile.md",
            Path(__file__).parent.parent.parent / "system_profile.md" # genesis/../../system_profile.md
        ]
        
        for path in possible_paths:
            if path.exists():
                profile_found = True
                break
                
        if not profile_found:
            status = "warning"
            issues.append("system_profile.md not found")
            
        return {
            "status": status,
            "profile_found": profile_found,
            "issues": issues
        }

    def _check_scheduler(self) -> Dict[str, Any]:
        """检查调度器状态"""
        # scheduler is AgencyScheduler instance
        # It has .jobs list
        try:
            job_count = len(self.scheduler.jobs) if hasattr(self.scheduler, "jobs") else 0
            is_running = self.scheduler.running if hasattr(self.scheduler, "running") else False
            
            return {
                "status": "ok",
                "job_count": job_count,
                "is_running": is_running
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _check_network(self) -> Dict[str, Any]:
        """检查基础网络连通性"""
        targets = [
            ("8.8.8.8", 53),     # Google DNS (TCP)
            ("1.1.1.1", 53),     # Cloudflare DNS
            ("www.google.com", 80) # HTTP
        ]
        
        results = []
        success_count = 0
        
        for host, port in targets:
            try:
                start = time.time()
                # Use synchronous socket for simplicity in async loop (it's fast)
                # Ideally execute in executor if blocking
                s = socket.create_connection((host, port), timeout=2)
                s.close()
                latency = (time.time() - start) * 1000
                results.append({"target": host, "status": "ok", "latency_ms": latency})
                success_count += 1
            except Exception as e:
                results.append({"target": host, "status": "error", "error": str(e)})
                
        status = "ok" if success_count > 0 else "error"
        return {"status": status, "details": results}

    async def _check_provider(self) -> Dict[str, Any]:
        """检查 LLM Provider 状态"""
        if not self.provider_router:
            return {"status": "skipped", "reason": "No provider router configured"}
            
        active_name = self.provider_router.active_provider_name
        provider = self.provider_router.active_provider
        
        # 构造一个极简的 Ping包
        messages = [{"role": "user", "content": "ping"}]
        
        try:
            start = time.time()
            # 强制使用非流式以快速检测
            response = await provider.chat(messages=messages, max_tokens=5)
            latency = (time.time() - start) * 1000
            
            content = response.content
            if not content and not response.tool_calls:
                 return {
                     "status": "warning", 
                     "provider": active_name, 
                     "latency_ms": latency,
                     "error": "Empty response from provider"
                 }
                 
            # Test 2: Streaming (Robustness)
            streaming_ok = False
            stream_latency = 0
            try:
                s_start = time.time()
                # Use a callback that just counts
                chunks = 0
                async def noop_callback(kind, content):
                    nonlocal chunks
                    chunks += 1
                    
                await provider.chat(messages=messages, max_tokens=5, stream=True, stream_callback=noop_callback)
                stream_latency = (time.time() - s_start) * 1000
                if chunks > 0:
                    streaming_ok = True
            except Exception:
                pass

            return {
                "status": "ok",
                "provider": active_name,
                "latency_ms": latency,
                "stream_latency_ms": stream_latency,
                "streaming_ok": streaming_ok,
                "model": getattr(provider, "model", "unknown")
            }
            
        except Exception as e:
            return {
                "status": "error",
                "provider": active_name,
                "error": str(e)
            }

    async def _check_memory(self) -> Dict[str, Any]:
        """检查记忆库完整性"""
        if not self.memory:
             return {"status": "skipped", "reason": "No memory store configured"}
             
        try:
            # 假设是 SQLiteMemoryStore
            if hasattr(self.memory, "_get_conn"):
                start = time.time()
                try:
                    conn = self.memory._get_conn()
                    
                    # 1. Check Short-term Memory
                    cursor = conn.execute("SELECT count(*) FROM memories")
                    count = cursor.fetchone()[0]
                    
                    # 2. Check Long-term Memory (Compressed Blocks)
                    # This would have caught the missing table issue!
                    try:
                        cursor = conn.execute("SELECT count(*) FROM compressed_blocks")
                        block_count = cursor.fetchone()[0]
                    except Exception:
                        block_count = -1 # Table missing
                    
                    conn.close()
                    latency = (time.time() - start) * 1000
                    
                    # 3. Check Vector Memory (Deep Memory)
                    try:
                        cursor = conn.execute("SELECT count(*) FROM vectors")
                        vec_count = cursor.fetchone()[0]
                    except Exception:
                        vec_count = -1 # Vector table missing/not enabled
                        
                    conn.close()
                    latency = (time.time() - start) * 1000
                    
                    status = "ok" if block_count >= 0 else "warning"
                    error = None
                    if block_count == -1:
                         error = "Missing 'compressed_blocks' table - Persistence broken"
                         status = "error"
                         
                    # Check if Embedding Model is loaded
                    encoder_status = "not_loaded"
                    if hasattr(self.memory, "encoder") and self.memory.encoder:
                        encoder_status = "ready"
                    elif hasattr(self.memory, "_encoder_failed") and self.memory._encoder_failed:
                        encoder_status = "failed"
                         
                    return {
                        "status": status,
                        "impl": "sqlite",
                        "latency_ms": latency,
                        "item_count": count,
                        "block_count": block_count,
                        "vector_count": vec_count,
                        "encoder_status": encoder_status,
                        "error": error
                    }
                except Exception as db_err:
                    return {"status": "error", "error": str(db_err)}
            else:
                return {"status": "skipped", "reason": "Unknown memory implementation"}
                
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _check_disk(self) -> Dict[str, Any]:
        """检查磁盘空间"""
        try:
            import shutil
            cwd = Path.cwd()
            total, used, free = shutil.disk_usage(cwd)
            
            free_gb = free / (1024**3)
            status = "ok" if free_gb > 1.0 else "warning" # Warn if < 1GB
            
            return {
                "status": status,
                "free_gb": f"{free_gb:.2f}",
                "path": str(cwd)
            }
        except Exception as e:
             return {"status": "error", "error": str(e)}
