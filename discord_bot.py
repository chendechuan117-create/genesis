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
                await self.message.channel.send(f"✅ **透镜采纳**: {adopted}/{total} ({rate:.0%})")
            elif evt.event_type == "thought":
                content = str(data) if not isinstance(data, str) else data
                if content.strip():
                    await self.message.channel.send(f"💭 {content[:1800]}")
        except Exception as e:
            logger.error(f"Callback handling error: {e}", exc_info=True)

    def _format_search_result(self, result: str) -> str:
        result = result.strip()
        if not result:
            return "🔎 （无结果）"
        return f"🔎 **检索结果**\n{result[:1900]}"


AUTO_MAX_ROUNDS = 0  # 0 = 无上限
AUTO_DRY_LIMIT = 4  # 连续低活动轮数上限（不依赖节点计数）

def _get_auto_signals() -> str:
    """从 DB 和日志中收集真实信号，作为 /auto 每轮的外部锚点。"""
    import sqlite3
    sections = []
    db = Path.home() / ".nanogenesis" / "workshop_v4.sqlite"

    if db.exists():
        try:
            conn = sqlite3.connect(str(db))
            # Arena 失败记录
            rows = conn.execute(
                "SELECT node_id, title, usage_fail_count, usage_success_count, confidence_score "
                "FROM knowledge_nodes WHERE usage_fail_count > 0 "
                "ORDER BY usage_fail_count DESC LIMIT 5"
            ).fetchall()
            if rows:
                lines = ["[Arena 失败记录 — 实践中翻车的知识]"]
                for nid, title, fail, succ, conf in rows:
                    lines.append(f"  {nid}: {title} (失败{fail}/成功{succ}, conf={conf:.2f})")
                sections.append("\n".join(lines))

            # 低 confidence 节点
            rows = conn.execute(
                "SELECT node_id, title, confidence_score, ntype "
                "FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV_%' "
                "AND confidence_score < 0.35 ORDER BY confidence_score LIMIT 5"
            ).fetchall()
            if rows:
                lines = ["[低置信度节点 — 可能有误或过时]"]
                for nid, title, conf, ntype in rows:
                    lines.append(f"  {nid}: [{ntype}] {title} (conf={conf:.2f})")
                sections.append("\n".join(lines))

            # VOID 任务
            void_count = conn.execute("SELECT COUNT(*) FROM void_tasks").fetchone()[0]
            if void_count > 0:
                void_samples = conn.execute(
                    "SELECT task_id, description FROM void_tasks ORDER BY created_at DESC LIMIT 3"
                ).fetchall()
                lines = [f"[知识空洞 (VOID) — 共 {void_count} 个待验证]"]
                for vid, desc in void_samples:
                    lines.append(f"  {vid}: {desc[:80]}")
                sections.append("\n".join(lines))

            conn.close()
        except Exception as e:
            sections.append(f"[DB 查询异常: {e}]")

    # 最近错误日志
    log_file = Path("runtime/genesis.log")
    if log_file.exists():
        try:
            lines = log_file.read_text(errors="replace").splitlines()
            errors = [l for l in lines[-200:] if "ERROR" in l or "Traceback" in l]
            if errors:
                recent = errors[-5:]
                err_lines = ["[最近运行错误 — 真实故障]"]
                for el in recent:
                    err_lines.append(f"  {el[:150]}")
                sections.append("\n".join(err_lines))
        except Exception:
            pass

    if not sections:
        return "[无明显信号 — 系统状态良好]"
    return "\n\n".join(sections)


AUTO_PROMPT_FIRST = """你正在自主改进模式中。目标：发现自身的真实缺陷，并在 Doctor 沙箱中动手修复。

以下是从你的运行数据中提取的真实信号：
{signals}

## 工作流程
1. 从上述信号中选择一个最值得修复的问题（优先选 Arena 失败或运行错误）
2. 诊断根因：读相关代码、日志、知识节点
3. 在 Doctor 沙箱中修复：
   - `./scripts/doctor.sh start` 启动沙箱
   - `./scripts/doctor.sh exec <cmd>` 在沙箱内执行命令
   - `./scripts/doctor.sh cat <file>` 查看沙箱内文件
   - 用 shell 工具运行 `./scripts/doctor.sh exec sed -i '...' /workspace/path/to/file.py` 修改代码
   - `./scripts/doctor.sh test` 在沙箱内跑测试
   - `./scripts/doctor.sh diff` 查看你的修改
4. 报告你做了什么、改了什么、测试结果如何

## 规则
- 不要直接修改本体代码（genesis/ 下的 .py 文件），所有代码修改必须在 Doctor 沙箱中进行
- 知识库操作（搜索/记录/删除节点）可以直接进行
- 每轮只解决一个问题，做到位
- 如果信号中没有值得修的问题，可以从知识库中找到过时或矛盾的知识进行清理"""

AUTO_PROMPT_CONTINUE = """继续自主改进。不要重复上一轮已完成的工作。

上一轮行动：
{last_findings}

{history}

当前信号：
{signals}

## 工作流程
选择一个新问题 → 诊断 → Doctor 沙箱修复 → 测试 → diff → 报告

沙箱命令：
- `./scripts/doctor.sh start` / `exec <cmd>` / `cat <file>` / `test` / `diff`
- 修改文件: `./scripts/doctor.sh exec sed -i '...' /workspace/path/to/file.py`

规则：不要直接修改本体代码，所有代码修改在 Doctor 沙箱中进行。知识库操作可以直接进行。"""


def _get_node_count_status() -> dict:
    """获取知识节点计数观测状态。仅作遥测，不用于业务判定。"""
    try:
        import sqlite3
        db = Path.home() / ".nanogenesis" / "workshop_v4.sqlite"
        if not db.exists():
            return {
                "status": "unavailable",
                "count": None,
                "detail": f"数据库不存在: {db}",
            }
        conn = sqlite3.connect(str(db))
        try:
            count = conn.execute("SELECT COUNT(*) FROM knowledge_nodes").fetchone()[0]
        finally:
            conn.close()
        return {
            "status": "ok",
            "count": int(count),
            "detail": None,
        }
    except Exception as e:
        return {
            "status": "error",
            "count": None,
            "detail": str(e),
        }


def _format_node_telemetry(before: dict, after: dict) -> str:
    """格式化节点计数遥测文案。"""
    if before.get("status") == "ok" and after.get("status") == "ok":
        before_count = before.get("count")
        after_count = after.get("count")
        delta = after_count - before_count
        delta_str = f"+{delta}" if delta > 0 else str(delta) if delta < 0 else "±0"
        return f"节点计数观测: {before_count} → {after_count} ({delta_str})"

    after_status = after.get("status")
    if after_status == "unavailable":
        return "节点计数观测: 统计不可用"
    if after_status == "error":
        detail = after.get("detail") or "未知错误"
        return f"节点计数观测: 统计失败（{detail[:120]}）"
    return "节点计数观测: 无法判断"


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
    """自主改进模式：信号驱动 → Doctor 沙箱动手 → diff 报告 → 用户决定升级"""
    import time as _time

    state = auto_state.get(channel.id)
    if not state:
        return

    round_num = 0
    consecutive_dry = 0
    stop_reason = "manual"
    round_log = []       # 每轮的行动摘要
    last_findings = ""   # 上轮行动结果，传递给下轮
    final_node_telemetry = "节点计数观测: 无法判断"

    await channel.send(
        f"🚀 **自主改进模式启动** ({'无上限' if AUTO_MAX_ROUNDS == 0 else f'上限 {AUTO_MAX_ROUNDS} 轮'})\n"
        f"Genesis 将基于真实信号，在 Doctor 沙箱中动手改进自身。\n"
        f"发送 `/auto stop` 停止。"
    )

    while state.get("active", False):
        round_num += 1

        if AUTO_MAX_ROUNDS > 0 and round_num > AUTO_MAX_ROUNDS:
            stop_reason = f"reached {AUTO_MAX_ROUNDS} round cap"
            break

        _reset_provider()
        node_status_before = _get_node_count_status()

        # ── 收集真实信号 ──
        signals = _get_auto_signals()

        # ── 构建 prompt ──
        if round_num == 1:
            prompt = AUTO_PROMPT_FIRST.format(signals=signals)
        else:
            history = ""
            if round_log:
                history = "[已完成的行动]\n" + "\n".join(round_log[-5:]) + "\n不要重复以上内容。"
            findings = last_findings if last_findings and last_findings.strip() != "(无输出)" else "(上轮无明确产出，换个方向)"
            prompt = AUTO_PROMPT_CONTINUE.format(
                last_findings=findings,
                history=history,
                signals=signals,
            )

        phase = f"R{round_num}"
        await channel.send(f"{'─'*40}\n🔧 **第 {round_num} 轮**")

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

            # 节点变化仅做遥测，不参与轮次判断或停止条件
            node_status_after = _get_node_count_status()
            node_telemetry = _format_node_telemetry(node_status_before, node_status_after)
            final_node_telemetry = node_telemetry

            # 保守停止条件：仅基于轮次输出是否为空，不依赖节点计数
            has_observation = bool(response and str(response).strip())
            if has_observation:
                consecutive_dry = 0
            else:
                consecutive_dry += 1

            # 保存本轮输出作为下轮的"上轮观察"
            last_findings = response[:2000] if response else "(无输出)"

            # 记录摘要
            summary = response[:300].replace("\n", " ") if response else "(无输出)"
            round_log.append(f"R{round_num}[{phase}]: {node_telemetry} | {summary}")

            await channel.send(
                f"**第{round_num}轮 [{phase}]** | {duration:.0f}s | {total_tokens}t | {node_telemetry} | 空输出计数={consecutive_dry}"
            )

            if response:
                preview = response[:3600]
                if len(response) > 3600:
                    preview += f"\n... (共{len(response)}字)"
                for i in range(0, len(preview), 1990):
                    await channel.send(preview[i:i+1990])

        except Exception as e:
            logger.error(f"Auto round {round_num} [{phase}] error: {e}", exc_info=True)
            await channel.send(f"⚠️ 第{round_num}轮 [{phase}] 异常: {str(e)[:200]}")
            consecutive_dry += 1
            last_findings = ""
            final_node_telemetry = "节点计数观测: 统计失败（本轮执行异常后未完成观测）"

        # ── 熔断 ──
        if consecutive_dry >= AUTO_DRY_LIMIT:
            stop_reason = f"{AUTO_DRY_LIMIT} consecutive empty-output/error rounds"
            await channel.send(f"⏸️ 连续 {AUTO_DRY_LIMIT} 轮空输出或异常，自动停止。")
            break

        # 轮间休息
        if state.get("active", False):
            sleep_time = 8 if consecutive_dry == 0 else 15 + consecutive_dry * 5
            await asyncio.sleep(sleep_time)

    # ── 汇总 ──
    state["active"] = False
    await channel.send(
        f"{'═'*40}\n"
        f"🏁 **自主改进结束** | {round_num} 轮 | 停止: {stop_reason}\n"
        f"{final_node_telemetry}\n"
        f"{'═'*40}"
    )
    auto_state.pop(channel.id, None)


@client.event
async def on_ready():
    logger.info(f"Logged in as {client.user} (id={client.user.id})")
    logger.info("Discord bot ready.")


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    content = (message.content or "").strip()
    # Strip bot mention so "@Genesis /auto" works
    if client.user and client.user.mentioned_in(message):
        content = content.replace(f"<@{client.user.id}>", "").replace(f"<@!{client.user.id}>", "").strip()
    user_intent = content

    if content.startswith("/auto"):
        parts = content.split(maxsplit=1)
        cmd = parts[1].strip().lower() if len(parts) > 1 else "start"

        if cmd == "stop":
            st = auto_state.get(message.channel.id)
            if st and st.get("active"):
                st["active"] = False
                await message.reply("🛑 正在停止（等待当前行动完成）...")
            else:
                await message.reply("ℹ️ 当前没有运行中的自主模式。")
            return

        if cmd == "status":
            st = auto_state.get(message.channel.id)
            if st and st.get("active"):
                await message.reply("🟢 自主模式运行中。发送 `/auto stop` 停止。")
            else:
                await message.reply("⚪ 自主模式未运行。")
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
        await message.reply("⚠️ 自主模式运行中，发送 `/auto stop` 停止后再对话。")
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
