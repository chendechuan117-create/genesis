import os
import sys
import asyncio
import logging
from pathlib import Path
import discord
from dotenv import load_dotenv

from factory import create_agent
from genesis.core.models import CallbackEvent

# 1. Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("DiscordBot")

# 0. 单实例保护：防止多个 bot 进程同时运行
PIDFILE = Path("runtime/discord_bot.pid")
PIDFILE.parent.mkdir(parents=True, exist_ok=True)
if PIDFILE.exists():
    old_pid = PIDFILE.read_text().strip()
    # 检查旧进程是否还活着
    try:
        os.kill(int(old_pid), 0)
        logger.error(f"Another discord_bot instance is already running (PID {old_pid}). Exiting.")
        sys.exit(1)
    except (ProcessLookupError, ValueError):
        pass  # 旧进程已死，继续启动
PIDFILE.write_text(str(os.getpid()))

import atexit
atexit.register(lambda: PIDFILE.unlink(missing_ok=True))

# 2. Env
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    logger.error("No DISCORD_BOT_TOKEN found.")
    exit(1)

# 3. Agent
logger.info("Initializing Genesis V4...")
agent = create_agent()

# 4. Discord
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
running_tasks = set()
auto_state = {}  # channel_id -> {"active": bool, "task": asyncio.Task}

GENESIS_VERSION = "V4.2 (Glassbox)"


class DiscordCallback:
    """V4 运行时回调 → Discord 实时状态"""
    def __init__(self, message: discord.Message):
        self.message = message

    async def __call__(self, event_type: str, data):
        try:
            evt = CallbackEvent.from_raw(event_type, data)

            if evt.event_type == "blueprint":
                text = str(data) if not isinstance(data, str) else data
                if len(text) > 2000:
                    for i in range(0, len(text), 1990):
                        await self.message.channel.send(text[i:i+1990])
                else:
                    await self.message.channel.send(text)
            elif evt.event_type == "tool_start":
                await self.message.channel.send(f"🟢 `{evt.name or '?'}` 运行中...")
            elif evt.event_type == "search_result":
                formatted = self._format_search_result(evt.result or "")
                if len(formatted) > 2000:
                    for i in range(0, len(formatted), 1990):
                        await self.message.channel.send(formatted[i:i+1990])
                else:
                    await self.message.channel.send(formatted)
            elif evt.event_type == "tool_result":
                result_peek = (evt.result or "")[:200]
                await self.message.channel.send(f"✅ **[{evt.name or '?'}]**:\n```\n{result_peek}\n```")
            elif evt.event_type == "lens_start":
                personas = (data or {}).get("personas", []) if isinstance(data, dict) else []
                probe_hits = (data or {}).get("probe_hits", 0) if isinstance(data, dict) else 0
                g_interp = (data or {}).get("g_interpretation", "") if isinstance(data, dict) else ""
                persona_str = " / ".join(f"`{p}`" for p in personas)
                msg = f"🔭 **Multi-G 透镜启动** | 探针: {probe_hits} 命中 → {len(personas)} 个视角\n{persona_str}"
                if g_interp:
                    msg += f"\n📋 **G 的理解**: {g_interp}"
                await self.message.channel.send(msg)
            elif evt.event_type == "lens_analysis":
                info = data if isinstance(data, dict) else {}
                persona = info.get("persona", "?")
                preview = info.get("content_preview", "")[:120]
                await self.message.channel.send(f"🔭 `Lens-{persona}` 解读: {preview}")
            elif evt.event_type == "lens_adoption":
                info = data if isinstance(data, dict) else {}
                adopted = info.get("adopted_count", 0)
                total = info.get("total_lenses", 0)
                rate = info.get("adoption_rate", 0)
                adopted_list = info.get("adopted", [])
                persona_names = ", ".join(f"`{a['persona']}`" for a in adopted_list) if adopted_list else "无"
                await self.message.channel.send(
                    f"📊 **Multi-G 采纳率**: {adopted}/{total} ({rate:.0%}) | 被采纳: {persona_names}"
                )
            elif evt.event_type == "lens_done":
                info = data if isinstance(data, dict) else {}
                entries = info.get("entries", 0)
                voids = info.get("voids", 0)
                await self.message.channel.send(
                    f"🔭 **透镜阶段完成** | {entries} 条分析 / {voids} 个信息空洞"
                )
        except Exception as e:
            logger.error(f"Callback error: {e}")

    @staticmethod
    def _format_search_result(raw: str) -> str:
        """将搜索结果格式化为类似「已加载认知节点」的直观风格"""
        lines = raw.strip().split("\n")
        output = []
        current_section = None
        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line in ["RECOMMENDED_ACTIVE_NODES:", "SUPPORTING_REFERENCE_NODES:", "MATCH_DETAILS:", "PREREQUISITE_HINTS:", "SIGNATURE_CLOSURE_HINTS:", "ACTIVE_NODE_SELECTION_HINT:"]:
                current_section = line
                title_map = {
                    "RECOMMENDED_ACTIVE_NODES:": "🧩 **建议挂载节点**",
                    "SUPPORTING_REFERENCE_NODES:": "📚 **背景参考节点**",
                    "MATCH_DETAILS:": "🔎 **详细匹配**",
                    "PREREQUISITE_HINTS:": "🔗 **前置依赖提示**",
                    "SIGNATURE_CLOSURE_HINTS:": "🧭 **签名闭包提示**",
                    "ACTIVE_NODE_SELECTION_HINT:": "📝 **挂载建议**",
                }
                output.append(title_map.get(line, line))
                continue

            if line.startswith("[语义]") or line.startswith("[字面]"):
                source = "🔮" if line.startswith("[语义]") else "🔤"
                rest = line.split(">", 1)[-1].strip() if ">" in line else line
                if "|" in rest:
                    rest = rest.split("|")[0].strip()
                output.append(f"{source} {rest}")
            elif line.startswith("-"):
                prefix = "-"
                if current_section == "RECOMMENDED_ACTIVE_NODES:":
                    prefix = "🧩"
                elif current_section == "SUPPORTING_REFERENCE_NODES:":
                    prefix = "📚"
                elif current_section == "PREREQUISITE_HINTS:":
                    prefix = "🔗"
                elif current_section == "SIGNATURE_CLOSURE_HINTS:":
                    prefix = "🧭"
                elif current_section == "ACTIVE_NODE_SELECTION_HINT:":
                    prefix = "📝"
                elif current_section == "MATCH_DETAILS:":
                    prefix = "🔎"
                output.append(f"{prefix} {line[1:].strip()}")
            elif line.startswith("<--") or line.startswith("-->"):
                output.append(f"  {line}")
            elif line.startswith("SIGNATURE_FILTER:"):
                output.append(f"🧭 {line}")
            elif "未找到" in line or "未命中" in line or "知识库为空" in line:
                output.append(f"⚠️ {line}")
            elif line.startswith("🔍"):
                output.append(line)
        
        if not output:
            return f"🔍 **[知识库检索]**\n⚠️ 无匹配结果"
        return "🔍 **[知识库检索]**\n" + "\n".join(output)


@client.event
async def on_ready():
    logger.info(f"✅ {client.user} | Genesis {GENESIS_VERSION} ready.")


# ── /auto 自主模式 ──────────────────────────────────────

AUTO_MAX_ROUNDS = 50
AUTO_DRY_LIMIT = 5  # 连续全局无产出轮数上限
AUTO_CAT_FATIGUE = 2  # 单类别连续无产出 N 次后跳过

# ── 任务类别定义 ──
# 每个类别：(id, 名称, emoji, prompt 模板)
# prompt 模板中的 {target} 和 {history} 会被动态替换
AUTO_CATEGORIES = [
    {
        "id": "void_verify",
        "name": "VOID 验证",
        "emoji": "🔬",
        "prompt": (
            "任务类型：VOID 验证\n\n"
            "执行步骤：\n"
            "1. 用 search_knowledge_nodes(ntype=\"CONTEXT\", keywords=[\"VOID\"]) 找到待验证的 VOID 节点\n"
            "2. 选择一个你尚未验证过的 VOID（优先选 confidence 最低的）\n"
            "3. 设计最小实验来验证或推翻它（shell 命令、读代码、跑测试）\n"
            "4. 根据实验结果：如果验证了→写 LESSON 并删除 VOID；如果推翻了→直接删除 VOID\n\n"
            "{history}\n"
            "限制：不要修改 genesis/ 下的 .py 文件。每轮只处理 1 个 VOID，做深不做广。"
        ),
    },
    {
        "id": "knowledge_audit",
        "name": "知识审计",
        "emoji": "🔍",
        "prompt": (
            "任务类型：知识审计\n\n"
            "执行步骤：\n"
            "1. 用 search_knowledge_nodes 搜索低质量节点（关键词搜索不同领域）\n"
            "2. 找出以下问题节点：\n"
            "   - 内容空洞或过于笼统的 LESSON\n"
            "   - 相互矛盾的节点\n"
            "   - 内容重复但表述不同的节点\n"
            "   - validation_status=unverified 且 confidence < 0.5 的节点\n"
            "3. 对问题节点：用实验验证→修正或删除\n\n"
            "{history}\n"
            "限制：不要修改 genesis/ 下的 .py 文件。每轮最多处理 3 个节点，做精不做多。"
        ),
    },
    {
        "id": "code_review",
        "name": "代码审查",
        "emoji": "📋",
        "prompt": (
            "任务类型：代码审查\n\n"
            "目标模块：{target}\n\n"
            "执行步骤：\n"
            "1. 阅读目标模块的代码\n"
            "2. 识别以下问题（按优先级排序）：\n"
            "   - 安全漏洞（路径穿越、注入、未授权访问）\n"
            "   - 错误处理缺陷（未捕获异常、静默失败）\n"
            "   - 逻辑 bug（边界条件、状态不一致）\n"
            "   - 性能问题（不必要的重复计算、内存泄漏）\n"
            "3. 对每个发现：记录为 LESSON（包含文件名、行号、具体问题和建议修复方案）\n\n"
            "{history}\n"
            "限制：不要修改代码文件，只记录发现。每个发现必须包含具体代码引用。"
        ),
    },
    {
        "id": "health_check",
        "name": "系统健康",
        "emoji": "🏥",
        "prompt": (
            "任务类型：系统健康检查\n\n"
            "执行步骤：\n"
            "1. 检查系统状态：\n"
            "   - 磁盘空间（df -h）\n"
            "   - Genesis 进程状态（ps aux | grep genesis）\n"
            "   - 最近的错误日志（tail runtime/genesis.log | grep -i error）\n"
            "   - Docker 容器状态（docker ps）\n"
            "   - 知识库大小和增长趋势\n"
            "2. 对发现的异常：诊断根因并记录为 LESSON\n"
            "3. 对系统正常运行的关键指标：记录为 ASSET（便于未来对比）\n\n"
            "{history}\n"
            "限制：不要修改配置文件或重启服务。只诊断和记录。"
        ),
    },
    {
        "id": "consolidate",
        "name": "知识整合",
        "emoji": "🧩",
        "prompt": (
            "任务类型：知识整合\n\n"
            "执行步骤：\n"
            "1. 用 search_knowledge_nodes 搜索某个主题领域的所有节点\n"
            "2. 找出：\n"
            "   - 可以合并的重复节点（内容相似但 ID 不同）\n"
            "   - 可以从多个 CONTEXT 提炼出的更高层 LESSON\n"
            "   - 缺少 prerequisites 或 resolves 的 LESSON（补全关系）\n"
            "3. 执行整合：合并重复→提炼上位→补全关系\n\n"
            "{history}\n"
            "限制：每轮聚焦 1 个主题领域。删除节点前先确认内容已被保留在合并后的节点中。"
        ),
    },
]

# 代码审查的目标模块列表（轮转使用）
_CODE_REVIEW_TARGETS = [
    "genesis/v4/loop.py（核心循环：G/Op/C 阶段流转）",
    "genesis/v4/manager.py（管理器：知识检索、Multi-G、prompt 构建）",
    "genesis/core/provider.py（LLM 调用：httpx、流式解析、重试）",
    "genesis/core/provider_manager.py（Provider 路由：failover、探活）",
    "genesis/tools/node_tools.py（知识节点工具：CRUD、搜索、去重）",
    "genesis/v4/agent.py（Agent 主体：初始化、process 入口）",
    "genesis/v4/background_daemon.py（后台守护：拾荒者/发酵池/验证器/GC）",
    "discord_bot.py（Discord 前端：消息处理、auto 模式）",
    "genesis/v4/blackboard.py（黑板：Multi-G 透镜共享状态）",
    "genesis/core/registry.py（注册表：工具和 Provider 的全局注册）",
]

def _get_node_count() -> int:
    """获取当前知识库节点数量"""
    try:
        import sqlite3
        db = Path.home() / ".nanogenesis" / "workshop_v4.sqlite"
        if not db.exists():
            return 0
        conn = sqlite3.connect(str(db))
        count = conn.execute("SELECT COUNT(*) FROM knowledge_nodes").fetchone()[0]
        conn.close()
        return count
    except Exception:
        return -1

def _reset_provider():
    """每轮行动前强制重置 provider 回首选（防 C-Phase 400 导致的残留 failover）"""
    try:
        router = agent.provider
        preferred = getattr(router, '_preferred_provider_name', 'aixj')
        if router.active_provider_name != preferred and preferred in router.providers:
            router._switch_provider(preferred)
            router._failover_time = 0
    except Exception:
        pass

async def _run_auto(channel: discord.TextChannel):
    """自主模式主循环：结构化任务队列 + 强制轮转"""
    import time as _time
    
    state = auto_state.get(channel.id)
    if not state:
        return
    
    round_num = 0
    total_nodes_created = 0
    consecutive_dry = 0  # 全局连续零产出
    stop_reason = "manual"
    
    # 每个类别的追踪状态
    cat_stats = {}
    for cat in AUTO_CATEGORIES:
        cat_stats[cat["id"]] = {
            "rounds": 0,           # 该类别已执行轮数
            "nodes": 0,            # 该类别产出节点数
            "consecutive_dry": 0,  # 该类别连续无产出
            "fatigued": False,     # 是否疲劳（跳过）
            "history": [],         # 该类别的执行历史
        }
    
    # 代码审查模块索引
    code_review_idx = 0
    
    # 构建轮转队列
    cat_queue = [cat["id"] for cat in AUTO_CATEGORIES]
    cat_pos = 0  # 当前队列位置
    
    # 启动消息
    cat_names = " → ".join(f'{c["emoji"]}{c["name"]}' for c in AUTO_CATEGORIES)
    await channel.send(
        f"🧠 **自主模式启动** (上限 {AUTO_MAX_ROUNDS} 轮, 连续 {AUTO_DRY_LIMIT} 轮无产出停止)\n"
        f"📋 **任务轮转**: {cat_names}\n"
        f"发送 `/auto stop` 停止。"
    )
    
    while state.get("active", False):
        round_num += 1
        
        if round_num > AUTO_MAX_ROUNDS:
            stop_reason = f"reached {AUTO_MAX_ROUNDS} round cap"
            break
        
        # ── 选择下一个非疲劳类别 ──
        attempts = 0
        while attempts < len(cat_queue):
            cat_id = cat_queue[cat_pos % len(cat_queue)]
            cat_pos += 1
            if not cat_stats[cat_id]["fatigued"]:
                break
            attempts += 1
        else:
            # 所有类别都疲劳了
            stop_reason = "all categories fatigued"
            await channel.send("⏸️ 所有任务类别均已疲劳（连续无产出），自动停止。")
            break
        
        # 找到当前类别定义
        current_cat = next(c for c in AUTO_CATEGORIES if c["id"] == cat_id)
        
        _reset_provider()
        nodes_before = _get_node_count()
        
        # ── 构建 prompt ──
        # 该类别的历史
        cat_history = cat_stats[cat_id]["history"]
        if cat_history:
            history_text = "[本类别历史]\n" + "\n".join(cat_history[-5:]) + "\n以上内容你已经做过了，不要重复。\n"
        else:
            history_text = ""
        
        # 代码审查需要具体目标
        target = ""
        if cat_id == "code_review":
            target = _CODE_REVIEW_TARGETS[code_review_idx % len(_CODE_REVIEW_TARGETS)]
            code_review_idx += 1
        
        prompt = current_cat["prompt"].format(target=target, history=history_text)
        
        await channel.send(
            f"{'─'*40}\n"
            f"{current_cat['emoji']} **第 {round_num} 轮 | {current_cat['name']}**"
            + (f"\n📁 目标: `{target}`" if target else "")
        )
        
        try:
            t0 = _time.time()
            
            class AutoCallback:
                def __init__(self, ch):
                    self.channel = ch
                async def __call__(self, event_type, data):
                    try:
                        evt = CallbackEvent.from_raw(event_type, data)
                        if evt.event_type == "tool_start":
                            await self.channel.send(f"🟢 `{evt.name or '?'}` ...")
                    except Exception:
                        pass
            
            result = await agent.process(
                f"[GENESIS_USER_REQUEST_START]\n{prompt}",
                step_callback=AutoCallback(channel)
            )
            
            duration = _time.time() - t0
            response = result.response if hasattr(result, 'response') else result.get("response", "") if isinstance(result, dict) else ""
            total_tokens = result.total_tokens if hasattr(result, 'total_tokens') else 0
            
            # 价值追踪
            nodes_after = _get_node_count()
            nodes_delta = max(0, nodes_after - nodes_before) if nodes_before >= 0 and nodes_after >= 0 else 0
            total_nodes_created += nodes_delta
            
            # 全局生产力
            if nodes_delta > 0:
                consecutive_dry = 0
            else:
                consecutive_dry += 1
            
            # 类别级追踪
            cs = cat_stats[cat_id]
            cs["rounds"] += 1
            cs["nodes"] += nodes_delta
            if nodes_delta > 0:
                cs["consecutive_dry"] = 0
            else:
                cs["consecutive_dry"] += 1
                if cs["consecutive_dry"] >= AUTO_CAT_FATIGUE:
                    cs["fatigued"] = True
                    logger.info(f"Auto: category {cat_id} fatigued after {cs['consecutive_dry']} dry rounds")
            
            # 记录类别历史（摘要更丰富：前 200 字）
            summary = response[:200].replace("\n", " ") if response else "(无输出)"
            cs["history"].append(
                f"R{round_num}: {'+'+ str(nodes_delta) + '节点' if nodes_delta else '无产出'} | {summary}"
            )
            
            tag = f"📝+{nodes_delta}" if nodes_delta > 0 else "⚪"
            fatigue_warn = " ⚠️疲劳" if cs["fatigued"] else ""
            await channel.send(
                f"**第{round_num}轮 [{current_cat['name']}]** | {duration:.0f}s | {total_tokens}t | {tag} | dry={consecutive_dry}{fatigue_warn}"
            )
            
            if response:
                preview = response[:1800]
                if len(response) > 1800:
                    preview += f"\n... (共{len(response)}字)"
                for i in range(0, len(preview), 1990):
                    await channel.send(preview[i:i+1990])
                    
        except Exception as e:
            logger.error(f"Auto round {round_num} [{cat_id}] error: {e}", exc_info=True)
            await channel.send(f"⚠️ 第{round_num}轮 [{current_cat['name']}] 异常: {str(e)[:200]}")
            consecutive_dry += 1
            cat_stats[cat_id]["consecutive_dry"] += 1
        
        # ── 全局生产力熔断 ──
        if consecutive_dry >= AUTO_DRY_LIMIT:
            stop_reason = f"{AUTO_DRY_LIMIT} consecutive dry rounds"
            await channel.send(f"⏸️ 连续 {AUTO_DRY_LIMIT} 轮全局无新节点，自动停止。")
            break
        
        # 轮间休息
        if state.get("active", False):
            sleep_time = 5 if consecutive_dry == 0 else 10 + consecutive_dry * 5
            await asyncio.sleep(sleep_time)
    
    # ── 汇总报告 ──
    state["active"] = False
    report_lines = []
    for cat in AUTO_CATEGORIES:
        cs = cat_stats[cat["id"]]
        if cs["rounds"] > 0:
            status = "✅" if cs["nodes"] > 0 else ("💤疲劳" if cs["fatigued"] else "⚪")
            report_lines.append(f"  {cat['emoji']} {cat['name']}: {cs['rounds']}轮 +{cs['nodes']}节点 {status}")
    
    await channel.send(
        f"{'═'*40}\n"
        f"🏁 **自主模式结束** | {round_num} 轮 | 📝 +{total_nodes_created} 新节点 | 停止: {stop_reason}\n"
        + "\n".join(report_lines) + "\n"
        f"{'═'*40}"
    )
    auto_state.pop(channel.id, None)


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    if client.user in message.mentions:
        content = message.content
        content = content.replace(f"<@{client.user.id}>", "")
        content = content.replace(f"<@!{client.user.id}>", "")
        user_intent = content.strip()
        
        # ── /auto 自主模式 ──
        if user_intent.startswith("/auto"):
            parts = user_intent.split()
            subcmd = parts[1] if len(parts) > 1 else "start"
            
            if subcmd == "stop":
                state = auto_state.get(message.channel.id)
                if state and state.get("active"):
                    state["active"] = False
                    await message.reply("🛑 正在停止（等待当前行动完成）...")
                else:
                    await message.reply("ℹ️ 自主模式未在运行")
                return
            
            # start (default)
            if message.channel.id in auto_state and auto_state[message.channel.id].get("active"):
                await message.reply("⚠️ 自主模式已在运行。发送 `/auto stop` 停止。")
                return
            
            auto_state[message.channel.id] = {"active": True}
            task = asyncio.create_task(_run_auto(message.channel))
            auto_state[message.channel.id]["task"] = task
            return

        # 附件处理
        attachment_paths = []
        image_paths = []
        if message.attachments:
            upload_dir = Path("runtime/uploads")
            upload_dir.mkdir(parents=True, exist_ok=True)
            for att in message.attachments:
                fp = (upload_dir / f"{message.id}_{att.filename}").resolve()
                try:
                    await att.save(fp)
                    if att.content_type and att.content_type.startswith('image/'):
                        image_paths.append(str(fp))
                    else:
                        attachment_paths.append(str(fp))
                except Exception as e:
                    logger.error(f"Attachment save failed: {e}")

        if not user_intent and not attachment_paths and not image_paths:
            await message.reply("嗯？找我什么事？")
            return

        if message.channel.id in running_tasks:
            await message.reply("⏳ 正在处理另一个任务...")
            return
        
        # 自主模式占用中
        if message.channel.id in auto_state and auto_state[message.channel.id].get("active"):
            await message.reply("� 自主模式运行中，发送 `/auto stop` 停止后再对话。")
            return

        running_tasks.add(message.channel.id)

        try:
            async with message.channel.typing():
                # 拉取频道近期聊天记录（解决上下文断裂）
                channel_ctx = ""
                try:
                    recent = [m async for m in message.channel.history(limit=11, before=message)]
                    if recent:
                        recent.reverse()
                        lines = ["[频道近期聊天环境]"]
                        for m in recent:
                            author = "Genesis" if m.author == client.user else m.author.display_name
                            text = m.clean_content.replace('\n', ' ')
                            if len(text) > 300:
                                text = text[:300] + "..."
                            lines.append(f"{author}: {text}")
                        lines.append("────────────────────")
                        channel_ctx = "\n".join(lines) + "\n\n"
                except Exception as e:
                    logger.warning(f"Channel history fetch failed: {e}")

                full_input = user_intent
                if attachment_paths:
                    files_str = "\n".join(f"  - {p}" for p in attachment_paths)
                    full_input += f"\n\n[Attached files:\n{files_str}]"

                full_input = f"{channel_ctx}[GENESIS_USER_REQUEST_START]\n{full_input}"

                ui_callback = DiscordCallback(message)
                result = await agent.process(full_input, step_callback=ui_callback, image_paths=image_paths)
                response = result.response if hasattr(result, 'response') else result.get("response", "...") if isinstance(result, dict) else "..."
                
                # Discord 不允许发送空消息，增加保底机制
                if not response or not str(response).strip():
                    response = "任务已完成，但没有生成可回复的文本内容。"

                if len(response) > 2000:
                    for i in range(0, len(response), 2000):
                        await message.reply(response[i:i+2000])
                else:
                    await message.reply(response)

        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            await message.reply(f"⚠️ 系统异常: {str(e)}")
        finally:
            running_tasks.remove(message.channel.id)


if __name__ == "__main__":
    logger.info("Starting Discord client...")
    client.run(TOKEN)
