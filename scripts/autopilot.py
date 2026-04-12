#!/usr/bin/env python3
"""
Genesis Autopilot — 自动驾驶模式
持续向 Genesis 投喂任务，最大化 API 利用率 + 全模块压力测试

用法:
  python scripts/autopilot.py                    # 前台运行（Ctrl+C 停止）
  python scripts/autopilot.py --daemon           # 后台运行
  python scripts/autopilot.py --interval 60      # 任务间隔（秒，默认 30）
  python scripts/autopilot.py --max-tasks 50     # 最多跑 N 个任务后停止
  python scripts/autopilot.py --category doctor  # 只跑某一类任务
"""

import os
import sys
import json
import time
import signal
import asyncio
import logging
import random
import argparse
from datetime import datetime
from pathlib import Path

# 确保 Genesis 在路径中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

# ── 日志 ──
RUNTIME_DIR = PROJECT_ROOT / "runtime"
RUNTIME_DIR.mkdir(exist_ok=True)
LOG_FILE = RUNTIME_DIR / "autopilot.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
    ]
)
logger = logging.getLogger("Autopilot")

# ── PID 文件 ──
PIDFILE = RUNTIME_DIR / "autopilot.pid"

# ── 任务库 ──────────────────────────────────────────────

TASKS = {
    # ─── 知识探索 (Multi-G + GP + C 全管线) ───
    "explore": [
        {
            "label": "explore_ai_agents",
            "input": "搜索最新的 AI Agent 架构趋势（2025-2026），特别是多智能体协作和记忆系统的进展。总结关键论文和开源项目。",
            "covers": ["multi_g", "g_search", "op_web", "op_url", "c_record"],
        },
        {
            "label": "explore_vector_db",
            "input": "调研当前主流的向量数据库方案（Milvus, Qdrant, ChromaDB, Weaviate），比较它们的性能、易用性和适用场景。我们目前用的是 SQLite + 本地 bge-small-zh 嵌入。",
            "covers": ["multi_g", "g_search", "op_web", "c_record"],
        },
        {
            "label": "explore_prompt_engineering",
            "input": "搜索 2025-2026 年 prompt engineering 的最新实践，特别是 prefix caching 优化、few-shot 策略、以及思维链（CoT）和工具调用（tool use）的最佳实践。",
            "covers": ["multi_g", "g_search", "op_web", "op_url", "c_record"],
        },
        {
            "label": "explore_knowledge_graph",
            "input": "调研知识图谱在 AI Agent 中的应用，特别是动态知识图谱、知识蒸馏、以及如何将非结构化信息转化为结构化知识。",
            "covers": ["multi_g", "g_search", "op_web", "c_record"],
        },
        {
            "label": "explore_python_async",
            "input": "搜索 Python 3.13+ asyncio 的新特性和最佳实践，特别是 TaskGroup、ExceptionGroup、以及异步上下文管理器的高级用法。",
            "covers": ["multi_g", "g_search", "op_web", "c_record"],
        },
        {
            "label": "explore_llm_safety",
            "input": "搜索 LLM 安全性相关的最新研究：prompt injection 防御、输出过滤、沙箱执行策略、以及代码执行的安全隔离方案。",
            "covers": ["multi_g", "g_search", "op_web", "c_record"],
        },
        {
            "label": "explore_docker_security",
            "input": "调研 Docker 容器安全最佳实践：最小权限原则、seccomp 配置、capabilities 管理、以及容器逃逸防护。",
            "covers": ["multi_g", "g_search", "op_web", "c_record"],
        },
    ],

    # ─── 自我诊断 (shell + file + Doctor 容器) ───
    "doctor": [
        {
            "label": "doctor_selftest",
            "input": "运行 Doctor 沙箱自检：./scripts/doctor.sh exec /opt/venv/bin/python3 /src/genesis/doctor/selftest.py。分析结果，如果有失败的测试，诊断原因。",
            "covers": ["op_shell", "analysis"],
        },
        {
            "label": "doctor_loop_audit",
            "input": "在 Doctor 沙箱中审计 genesis/v4/loop.py 的核心状态机。用 shell 工具运行：./scripts/doctor.sh exec grep -n 'def _run' /workspace/genesis/v4/loop.py 列出所有关键方法，然后逐一检查是否有死锁路径、无限循环、或未保护的异常。",
            "covers": ["op_shell", "op_file", "analysis"],
        },
        {
            "label": "doctor_provider_audit",
            "input": "用 Doctor 沙箱检查 provider 健康状态。检查 provider.py 的重试逻辑是否有 token 浪费风险。",
            "covers": ["op_shell", "analysis"],
        },
        {
            "label": "doctor_signature_audit",
            "input": "用 Doctor 沙箱审计签名系统。运行：./scripts/doctor.sh exec sqlite3 /workspace/runtime/genesis_v4.db \"SELECT dim_key, COUNT(*) FROM learned_signature_markers GROUP BY dim_key\"。然后检查维度注册表是否有垃圾维度。",
            "covers": ["op_shell", "analysis"],
        },
        {
            "label": "doctor_daemon_health",
            "input": "检查后台守护进程的健康状态。运行：cat runtime/daemon.log | tail -50。分析最近的 cycle 产出，是否有异常或零产出。",
            "covers": ["op_shell", "op_file", "analysis"],
        },
    ],

    # ─── 知识维护 (search + node tools + C-Phase) ───
    "maintain": [
        {
            "label": "maintain_void_fill",
            "input": "搜索知识库中标记为 VOID（信息空洞）的节点，选一个与 Genesis 自身运行最相关的。分析这个 VOID 描述的知识缺口，设计一个最小本地实验来验证它（用 shell 命令、读代码、跑测试、或在 Doctor 沙箱中操作）。根据实验结果，将结论沉淀为 LESSON 节点。",
            "covers": ["g_search", "op_shell", "op_file", "c_record", "void_system"],
        },
        {
            "label": "maintain_stale_review",
            "input": "搜索知识库中 confidence 最低的 5 个节点。评估它们是否仍然有价值：如果过时了就建议删除，如果只是缺少验证就去搜索最新信息验证。",
            "covers": ["g_search", "op_web", "c_record", "verifier"],
        },
        {
            "label": "maintain_duplicate_check",
            "input": "搜索知识库中关于 'Docker' 和 '容器' 相关的所有节点。检查是否有语义重复的节点（说的是同一件事但措辞不同）。如果有重复，建议合并策略。",
            "covers": ["g_search", "signature_system", "analysis"],
        },
        {
            "label": "maintain_edge_discovery",
            "input": "搜索知识库中关于 Python 异步编程的节点，然后搜索关于 LLM API 调用的节点。分析这两个领域之间是否有未被记录的关联（比如异步 HTTP 客户端管理、并发 API 调用优化等）。",
            "covers": ["g_search", "c_record", "edge_discovery"],
        },
    ],

    # ─── 编程挑战 (G分治 + Op多工具 + 高工具调用密度) ───
    "challenge": [
        {
            "label": "challenge_async_debug",
            "input": "帮我写一个 Python asyncio 的并发限流器（semaphore + rate limiter 组合），要求：1) 最大并发数可配置 2) 每秒最大请求数可配置 3) 支持 async with 语法 4) 有完整的单元测试。写完后在 Doctor 沙箱中运行测试。",
            "covers": ["gp_execute", "gp_file", "gp_shell"],
        },
        {
            "label": "challenge_sqlite_tool",
            "input": "帮我写一个 SQLite 数据库健康检查脚本，功能：1) 检查 WAL 文件大小 2) 统计各表行数和大小 3) 检测碎片率 4) 输出 JSON 格式报告。对 runtime/genesis_v4.db 运行测试。",
            "covers": ["gp_execute", "gp_file", "gp_shell"],
        },
        {
            "label": "challenge_log_analyzer",
            "input": "分析 runtime/daemon.log 的内容，写一个 Python 脚本统计：1) 每个 cycle 的耗时 2) 各任务（拾荒/发酵/验证/GC）的成功率 3) 免费池各 provider 的使用频率 4) 输出可视化报告（文本格式即可）。",
            "covers": ["gp_execute", "gp_file", "gp_shell", "analysis"],
        },
    ],

    # ─── 深度思考 (/deep 强制 7 透镜，极限压测 Multi-G) ───
    "deep": [
        {
            "label": "deep_architecture_review",
            "input": "/deep 从第一性原理审视 Genesis 的知识管理系统：当前的 NodeVault（SQLite + 向量搜索 + 签名系统）在知识量增长到 10000+ 节点时会遇到什么瓶颈？有哪些前瞻性的架构改进方向？",
            "covers": ["multi_g_7lens", "g_search", "c_record"],
        },
        {
            "label": "deep_consciousness_reflection",
            "input": "/deep 反思你自己的认知模式：作为一个 AI Agent，你的「知道」和「不知道」的边界在哪里？你的知识库中哪些是真正经过验证的知识，哪些只是 LLM 的幻觉被记录下来了？你有能力区分这两者吗？",
            "covers": ["multi_g_7lens", "g_search", "philosophical"],
        },
        {
            "label": "deep_learning_meta",
            "input": "/deep 分析你过去的学习模式：搜索知识库中所有 LESSON 类型的节点，找出哪些主题你学得最多、哪些领域有明显的知识盲区。你的学习是否存在系统性偏差？",
            "covers": ["multi_g_7lens", "g_search", "c_record", "meta_cognition"],
        },
    ],

    # ─── 快速任务 (/quick 跳过 Multi-G，测试纯 GP 路径) ───
    "quick": [
        {
            "label": "quick_system_check",
            "input": "/quick 检查一下 Docker 容器和系统服务的状态：运行 docker ps 看容器列表，systemctl --user status genesis-v4 看服务状态。",
            "covers": ["op_shell", "quick_path"],
        },
        {
            "label": "quick_disk_usage",
            "input": "/quick 检查磁盘使用情况：du -sh runtime/ 和 ls -lh runtime/*.db 看数据库大小。",
            "covers": ["op_shell", "quick_path"],
        },
        {
            "label": "quick_recent_knowledge",
            "input": "/quick 搜索知识库中最近 24 小时内新增的节点，列出它们的标题和类型。",
            "covers": ["g_search", "quick_path"],
        },
    ],
}

# 所有类别的扁平列表
ALL_CATEGORIES = list(TASKS.keys())


def build_task_queue(category: str = None, shuffle: bool = True) -> list:
    """构建任务队列"""
    if category:
        tasks = TASKS.get(category, [])
    else:
        tasks = []
        for cat_tasks in TASKS.values():
            tasks.extend(cat_tasks)
    
    if shuffle:
        tasks = list(tasks)
        random.shuffle(tasks)
    return tasks


class AutopilotMetrics:
    """运行指标追踪"""
    def __init__(self):
        self.started_at = datetime.now()
        self.tasks_completed = 0
        self.tasks_failed = 0
        self.total_iterations = 0
        self.total_duration_secs = 0
        self.task_log = []

    def record(self, label: str, success: bool, iterations: int, duration: float, response_preview: str):
        self.tasks_completed += 1
        if not success:
            self.tasks_failed += 1
        self.total_iterations += iterations
        self.total_duration_secs += duration
        self.task_log.append({
            "time": datetime.now().isoformat(),
            "label": label,
            "success": success,
            "iterations": iterations,
            "duration_secs": round(duration, 1),
            "response_preview": response_preview[:200],
        })

    def summary(self) -> str:
        elapsed = (datetime.now() - self.started_at).total_seconds()
        return (
            f"⏱️ 运行 {elapsed/60:.0f} 分钟 | "
            f"✅ {self.tasks_completed - self.tasks_failed} 成功 | "
            f"❌ {self.tasks_failed} 失败 | "
            f"🔄 {self.total_iterations} 总迭代 | "
            f"⏳ {self.total_duration_secs:.0f}s 总处理时间"
        )

    def save(self):
        """保存详细日志到 JSON"""
        log_path = RUNTIME_DIR / "autopilot_results.json"
        data = {
            "started_at": self.started_at.isoformat(),
            "summary": self.summary(),
            "tasks": self.task_log,
        }
        log_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


class Autopilot:
    """Genesis 自动驾驶"""

    def __init__(self, interval: int = 30, max_tasks: int = 0, category: str = None):
        self.interval = interval
        self.max_tasks = max_tasks
        self.category = category
        self.metrics = AutopilotMetrics()
        self.agent = None
        self._stop = False

    def _init_agent(self):
        """初始化 Genesis Agent（复用单实例）"""
        from factory import create_agent
        logger.info("🚀 初始化 Genesis Agent...")
        self.agent = create_agent()
        # Autopilot 模式：C-Phase 阻塞等待完成（保证知识写入）
        self.agent.c_phase_blocking = True
        self._preferred_provider = getattr(self.agent.provider, '_preferred_provider_name', 'xcode')
        logger.info(f"✅ Agent 就绪 | 首选 provider: {self._preferred_provider}")

    def _check_provider_guard(self) -> tuple:
        """检查 provider 是否仍是首选（日付费），防止 failover 烧钱
        Returns: (is_safe, current_provider_name)"""
        try:
            current = self.agent.provider.active_provider_name
            return (current == self._preferred_provider, current)
        except Exception:
            return (True, "unknown")

    def _get_node_count(self) -> dict:
        """获取 knowledge_nodes 节点计数观测状态（中性 telemetry）。"""
        db = Path.home() / ".genesis" / "workshop_v4.sqlite"
        if not db.exists():
            db = Path.home() / ".nanogenesis" / "workshop_v4.sqlite"
        try:
            import sqlite3
            if not db.exists():
                return {
                    "status": "unavailable",
                    "db_path": str(db),
                    "count": None,
                    "error": "database file not found",
                }
            conn = sqlite3.connect(str(db))
            try:
                count = conn.execute("SELECT COUNT(*) FROM knowledge_nodes").fetchone()[0]
            finally:
                conn.close()
            return {
                "status": "ok",
                "db_path": str(db),
                "count": count,
                "error": None,
            }
        except Exception as e:
            return {
                "status": "error",
                "db_path": str(db),
                "count": None,
                "error": str(e),
            }

    async def run_task(self, task: dict) -> bool:
        """执行单个任务"""
        label = task["label"]
        user_input = task["input"]
        covers = task.get("covers", [])

        # ── Provider 守卫：任务前检查 ──
        is_safe, current = self._check_provider_guard()
        if not is_safe:
            logger.warning(f"⛔ Provider 切换到 {current}（非 {self._preferred_provider}），停止 autopilot 防止烧钱")
            self._stop = True
            return False

        node_count_before = self._get_node_count()

        logger.info(f"{'='*60}")
        logger.info(f"📋 Task: {label}")
        logger.info(f"   Covers: {', '.join(covers)}")
        logger.info(f"   Input: {user_input[:100]}...")
        logger.info(f"{'='*60}")

        start = time.time()
        try:
            result = await asyncio.wait_for(
                self.agent.process(user_input),
                timeout=600
            )
            duration = time.time() - start
            response = result.get("response", "")
            metrics = result.get("metrics")
            success = metrics.success if metrics else False
            iterations = metrics.iterations if metrics else 0

            # ── 中性 telemetry：节点计数观测，不进入价值语义 ──
            node_count_after = self._get_node_count()
            value_tags = []
            if response and len(response) > 200: value_tags.append(f"{len(response)}字")
            if iterations > 3: value_tags.append(f"{iterations}轮")
            value_str = " | ".join(value_tags) if value_tags else "已完成"

            if node_count_before["status"] == "ok" and node_count_after["status"] == "ok":
                count_before = node_count_before["count"]
                count_after = node_count_after["count"]
                nodes_delta = count_after - count_before
                node_telemetry = f"节点计数观测: {count_before} -> {count_after} (Δ {nodes_delta:+d})"
            elif node_count_after["status"] == "unavailable":
                node_telemetry = (
                    f"节点计数观测: 不可用 | db={node_count_after['db_path']} | "
                    f"reason={node_count_after['error']}"
                )
            elif node_count_after["status"] == "error":
                node_telemetry = (
                    f"节点计数观测: 异常 | db={node_count_after['db_path']} | "
                    f"error={node_count_after['error']}"
                )
            else:
                node_telemetry = (
                    f"节点计数观测: 前置状态={node_count_before['status']} | "
                    f"后置状态={node_count_after['status']}"
                )

            preview = response[:200] if response else "(empty)"
            logger.info(f"✅ {label} 完成 | {iterations} iters | {duration:.1f}s | 摘要: {value_str}")
            logger.info(f"   {node_telemetry}")
            logger.info(f"   Response: {preview}")

            self.metrics.record(label, success, iterations, duration, preview)

            # ── Provider 守卫：任务后检查 ──
            is_safe, current = self._check_provider_guard()
            if not is_safe:
                logger.warning(f"⛔ 任务中 provider 切换到 {current}，停止 autopilot")
                self._stop = True
            return True

        except asyncio.TimeoutError:
            duration = time.time() - start
            logger.error(f"⏰ {label} 超时 (>{600}s)")
            self.metrics.record(label, False, 0, duration, "TIMEOUT")
            return False
        except Exception as e:
            duration = time.time() - start
            logger.error(f"❌ {label} 异常: {e}", exc_info=True)
            self.metrics.record(label, False, 0, duration, f"ERROR: {e}")
            return False

    async def run(self):
        """主循环"""
        self._init_agent()

        # 构建任务队列（无限循环 - 用完了重新 shuffle）
        task_count = 0

        while not self._stop:
            queue = build_task_queue(self.category, shuffle=True)
            
            for task in queue:
                if self._stop:
                    break
                if self.max_tasks > 0 and task_count >= self.max_tasks:
                    logger.info(f"🏁 已达到最大任务数 {self.max_tasks}")
                    self._stop = True
                    break

                await self.run_task(task)
                task_count += 1

                # 每 5 个任务输出一次汇总
                if task_count % 5 == 0:
                    logger.info(f"📊 {self.metrics.summary()}")
                    self.metrics.save()

                if not self._stop:
                    logger.info(f"⏳ 休息 {self.interval}s...")
                    await asyncio.sleep(self.interval)

            if not self._stop and self.max_tasks == 0:
                logger.info("🔄 任务队列已完成一轮，重新 shuffle...")

        # 最终汇总
        logger.info(f"{'='*60}")
        logger.info(f"🏁 Autopilot 停止")
        logger.info(f"📊 最终统计: {self.metrics.summary()}")
        logger.info(f"{'='*60}")
        self.metrics.save()

    def stop(self):
        logger.info("🛑 收到停止信号...")
        self._stop = True


def main():
    parser = argparse.ArgumentParser(description='Genesis Autopilot')
    parser.add_argument('--interval', type=int, default=30, help='任务间隔秒数 (默认 30)')
    parser.add_argument('--max-tasks', type=int, default=0, help='最多跑 N 个任务后停止 (0=无限)')
    parser.add_argument('--category', choices=ALL_CATEGORIES, help='只跑某一类任务')
    parser.add_argument('--daemon', action='store_true', help='后台运行')
    parser.add_argument('--list', action='store_true', help='列出所有任务')
    args = parser.parse_args()

    if args.list:
        for cat, tasks in TASKS.items():
            print(f"\n[{cat}] ({len(tasks)} tasks)")
            for t in tasks:
                print(f"  {t['label']}: {t['input'][:80]}...")
        return

    # 后台模式
    if args.daemon:
        pid = os.fork()
        if pid > 0:
            print(f"Autopilot started in background (PID {pid})")
            PIDFILE.write_text(str(pid))
            return
        # 子进程
        os.setsid()

    # 写 PID 文件
    PIDFILE.write_text(str(os.getpid()))

    pilot = Autopilot(
        interval=args.interval,
        max_tasks=args.max_tasks,
        category=args.category,
    )

    # 信号处理
    def handle_signal(sig, frame):
        pilot.stop()
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        asyncio.run(pilot.run())
    finally:
        PIDFILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
