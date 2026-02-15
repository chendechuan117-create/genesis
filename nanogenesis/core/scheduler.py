"""
任务调度器 (Scheduler)
实现 7x24 小时后台任务 (Time Agency)
"""

import asyncio
import logging
import time
import json
from pathlib import Path
from typing import List, Dict, Callable, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class Job:
    id: str
    command: str  # Shell 命令或任务描述
    interval: int  # 秒
    last_run: float = 0
    next_run: float = 0
    description: str = ""
    enabled: bool = True

class AgencyScheduler:
    """
    Agency 调度器
    负责在后台运行周期性任务
    """
    
    def __init__(self, tool_registry, db_path: str = None):
        self.tools = tool_registry
        self.jobs: Dict[str, Job] = {}
        self.running = False
        self._task = None
        
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = Path.home() / ".nanogenesis" / "jobs.json"
            
        self._load_jobs()
        
        # 获取 Shell 工具用于执行监测命令
        self.shell_tool = None
        
    def _load_jobs(self):
        """加载任务"""
        if not self.db_path.exists():
            return
            
        try:
            with self.db_path.open('r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    job = Job(**item)
                    # 恢复 next_run，防止积压任务立即爆发
                    # 如果上次运行时间是很久以前，重置 next_run 为现在
                    if time.time() - job.last_run > job.interval * 2:
                        job.next_run = time.time()
                    self.jobs[job.id] = job
            logger.info(f"✓ 已加载 {len(self.jobs)} 个后台任务")
        except Exception as e:
            logger.warning(f"加载任务失败: {e}")

    def _save_jobs(self):
        """保存任务"""
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with self.db_path.open('w', encoding='utf-8') as f:
                json.dump([asdict(j) for j in self.jobs.values()], f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存任务失败: {e}")

    def add_job(self, command: str, interval: int, description: str = "") -> str:
        """添加任务"""
        job_id = f"job_{int(time.time())}_{len(self.jobs)}"
        job = Job(
            id=job_id,
            command=command,
            interval=interval,
            next_run=time.time() + interval,
            description=description
        )
        self.jobs[job_id] = job
        self._save_jobs()
        logger.info(f"➕ 添加后台任务 [{job_id}]: {command} (每 {interval}s)")
        return job_id

    def remove_job(self, job_id: str) -> bool:
        """移除任务"""
        if job_id in self.jobs:
            del self.jobs[job_id]
            self._save_jobs()
            logger.info(f"➖ 移除后台任务: {job_id}")
            return True
        return False

    async def start(self):
        """启动调度器"""
        if self.running:
            return
            
        self.running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("⏰ Agency 调度器已启动 (Heartbeat Active)")

    async def stop(self):
        """停止调度器"""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("💤 Agency 调度器已休眠")

    async def _loop(self):
        """主循环"""
        while self.running:
            now = time.time()
            
            for job in self.jobs.values():
                if job.enabled and now >= job.next_run:
                    # 执行任务
                    await self._execute_job(job)
                    # 更新下次运行时间
                    job.last_run = now
                    job.next_run = now + job.interval
            
            # 休眠 1 秒 (心跳频率)
            await asyncio.sleep(1)

    async def _execute_job(self, job: Job):
        """执行单个任务"""
        logger.debug(f"⚡ 执行后台任务: {job.id}")
        
        # 尝试获取 Shell 工具 (如果是第一次)
        if not self.shell_tool:
            self.shell_tool = self.tools.get("shell")
            
        if not self.shell_tool:
            logger.error("无法执行任务: Shell 工具未找到")
            return

        try:
            # 执行命令
            # 这里的 shell_tool.execute 可能返回 output 字符串
            # 我们需要一种机制来判断是否需要报警
            # 简单的规则: 如果命令返回非空且包含 "ERROR"/"FAIL" 或者 exit code != 0 (ShellTool 需要支持返回 exit code)
            
            # 目前 ShellTool.execute 返回的是 stdout+stderr 文本
            result = await self.shell_tool.execute(command=job.command)
            
            # 简单的异常检测 (Level 1: Python Check)
            # 如果输出包含错误关键词，视为异常
            if "error" in result.lower() or "fail" in result.lower() or "exception" in result.lower():
                await self._trigger_alert(job, result)
                
        except Exception as e:
            logger.error(f"任务 {job.id} 执行异常: {e}")
            await self._trigger_alert(job, f"Execution Error: {e}")

    async def _trigger_alert(self, job: Job, content: str):
        """触发报警"""
        logger.warning(f"🚨 后台任务 {job.id} 触发报警: {content[:100]}...")
        # 这里的报警目前只是打印日志
        # 在深度集成后，应该推送到 Telegram
        # 或者存入 Memory 供 Agent 醒来时查看
        pass
