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

AUTO_META_PROMPT = """你正在自主运行模式。你可以自由决定做什么——
探索新知识、填补知识空洞、验证旧知识、研究你感兴趣的领域、
整理知识库、发现知识之间的关联、审计系统健康状况……
任何你认为对自己的成长有价值的事。

限制：不要修改自己的代码文件（genesis/ 下的 .py），但可以在回复中提出改进建议。

每完成一个行动，简要说明：你做了什么、为什么、下一步打算做什么。"""

AUTO_MAX_ROUNDS = 50
AUTO_DRY_LIMIT = 5  # 连续无产出轮数上限

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
    """自主模式主循环：Genesis 自由行动，实时输出到 Discord"""
    import time as _time
    
    state = auto_state.get(channel.id)
    if not state:
        return
    
    round_num = 0
    total_nodes_created = 0
    consecutive_dry = 0  # 连续零产出轮数
    round_summaries = []  # 每轮摘要，供后续 prompt 参考
    explored_directions = []  # 结构化已探索方向，防话题打转
    stop_reason = "manual"
    
    await channel.send(
        f"🧠 **自主模式启动** (上限 {AUTO_MAX_ROUNDS} 轮, 连续 {AUTO_DRY_LIMIT} 轮无产出自动停止)\n"
        f"Genesis 将自由决定行动方向。发送 `/auto stop` 停止。"
    )
    
    while state.get("active", False):
        round_num += 1
        
        # ── 硬上限 ──
        if round_num > AUTO_MAX_ROUNDS:
            stop_reason = f"reached {AUTO_MAX_ROUNDS} round cap"
            break
        
        _reset_provider()
        nodes_before = _get_node_count()
        
        # 第一轮用完整 meta-prompt，后续带上下文累积
        if round_num == 1:
            prompt = AUTO_META_PROMPT
        else:
            # 给 G 提供历史摘要，避免重复走同一条路
            history_block = "\n".join(round_summaries[-10:])  # 最近 10 轮
            # 已探索方向列表（去重用）
            if explored_directions:
                dirs_block = "\n".join(f"  - {d}" for d in explored_directions)
                dirs_text = f"\n[已探索方向（禁止重复）]\n{dirs_block}\n"
            else:
                dirs_text = ""
            prompt = (
                f"继续你的自主行动。\n\n"
                f"[进度] 已完成 {round_num-1} 轮, 累计 +{total_nodes_created} 节点, "
                f"连续 {consecutive_dry} 轮无新产出。\n"
                f"[近期行动]\n{history_block}\n"
                f"{dirs_text}\n"
                f"你必须选择一个与上面所有已探索方向完全不同的新切面。"
            )
        
        await channel.send(f"{'─'*40}\n🧠 **第 {round_num} 轮自主行动**")
        
        try:
            t0 = _time.time()
            
            class AutoCallback:
                def __init__(self, ch):
                    self.channel = ch
                async def __call__(self, event_type, data):
                    try:
                        from genesis.core.models import CallbackEvent
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
            iterations = result.iterations if hasattr(result, 'iterations') else 0
            total_tokens = result.total_tokens if hasattr(result, 'total_tokens') else 0
            
            # 价值追踪
            nodes_after = _get_node_count()
            nodes_delta = max(0, nodes_after - nodes_before) if nodes_before >= 0 and nodes_after >= 0 else 0
            total_nodes_created += nodes_delta
            
            # 生产力追踪
            if nodes_delta > 0:
                consecutive_dry = 0
            else:
                consecutive_dry += 1
            
            # 记录本轮摘要
            summary_preview = response[:100].replace("\n", " ") if response else "(无输出)"
            round_summaries.append(f"R{round_num}: {'+' + str(nodes_delta) + '节点' if nodes_delta else '无产出'} | {summary_preview}")
            
            # 提取本轮探索方向关键词（取第一个 ## 标题或前30字）
            if response:
                import re as _re
                _heading = _re.search(r'##\s*(.{5,60})', response)
                direction = _heading.group(1).strip() if _heading else response[:40].replace("\n", " ").strip()
                if direction and direction not in explored_directions:
                    explored_directions.append(direction)
            
            tag = f"📝+{nodes_delta}" if nodes_delta > 0 else "⚪"
            await channel.send(f"**第{round_num}轮** | {duration:.0f}s | {total_tokens}t | {tag} | dry={consecutive_dry}")
            
            if response:
                preview = response[:1800]
                if len(response) > 1800:
                    preview += f"\n... (共{len(response)}字)"
                for i in range(0, len(preview), 1990):
                    await channel.send(preview[i:i+1990])
                    
        except Exception as e:
            logger.error(f"Auto round {round_num} error: {e}", exc_info=True)
            await channel.send(f"⚠️ 第{round_num}轮异常: {str(e)[:200]}")
            consecutive_dry += 1
        
        # ── 生产力熔断 ──
        if consecutive_dry >= AUTO_DRY_LIMIT:
            stop_reason = f"{AUTO_DRY_LIMIT} consecutive dry rounds"
            await channel.send(f"⏸️ 连续 {AUTO_DRY_LIMIT} 轮无新节点产出，自动停止。")
            break
        
        # 轮间休息：有产出 5s，无产出递增（10s, 15s, 20s...）
        if state.get("active", False):
            sleep_time = 5 if consecutive_dry == 0 else 10 + consecutive_dry * 5
            await asyncio.sleep(sleep_time)
    
    # 汇总
    state["active"] = False
    await channel.send(
        f"{'═'*40}\n"
        f"🏁 **自主模式结束** | {round_num} 轮 | 📝 +{total_nodes_created} 新节点 | 停止原因: {stop_reason}\n"
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
