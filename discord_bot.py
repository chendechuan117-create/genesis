import os
import sys
import asyncio
import logging
from pathlib import Path
import discord
from dotenv import load_dotenv

from factory import create_agent
from genesis.core.models import CallbackEvent
from genesis.auto_mode import run_auto, describe_auto_state

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
channel_tasks = {}  # channel_id -> asyncio.Task
auto_state = {}  # channel_id -> {"active": bool, "task": asyncio.Task}


def _prune_auto_state(channel_id: int):
    st = auto_state.get(channel_id)
    if not st:
        return None
    task = st.get("task")
    if task is None or not task.done():
        return st
    exc = None
    if not task.cancelled():
        try:
            exc = task.exception()
        except Exception as e:
            exc = e
    logger.warning(
        f"/auto stale state pruned | channel={channel_id} active={st.get('active', False)} "
        f"cancelled={task.cancelled()} exc={exc!r}"
    )
    auto_state.pop(channel_id, None)
    return None


def _on_auto_task_done(channel_id: int, task: asyncio.Task):
    exc = None
    if task.cancelled():
        logger.warning(f"/auto task cancelled | channel={channel_id}")
    else:
        try:
            exc = task.exception()
        except Exception as e:
            exc = e
        if exc:
            exc_info = (type(exc), exc, exc.__traceback__) if isinstance(exc, BaseException) else False
            logger.error(f"/auto task failed | channel={channel_id} error={exc!r}", exc_info=exc_info)
        else:
            logger.info(f"/auto task finished | channel={channel_id}")
    st = auto_state.get(channel_id)
    if st and st.get("task") is task:
        auto_state.pop(channel_id, None)


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


### Auto-mode logic extracted to genesis/auto_mode.py ###

@client.event
async def on_ready():
    logger.info(f"Logged in as {client.user} (id={client.user.id})")
    logger.info("Discord bot ready.")


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return
    # 忽略 webhook 消息（Yogg 的只读输出），防止回声
    if message.webhook_id is not None:
        return

    content = (message.content or "").strip()
    # Strip bot mention so "@Genesis /auto" works
    if client.user and client.user.mentioned_in(message):
        content = content.replace(f"<@{client.user.id}>", "").replace(f"<@!{client.user.id}>", "").strip()
    user_intent = content

    if content.startswith("/auto"):
        rest = content[len("/auto"):].strip()
        cmd = rest.lower().split()[0] if rest else ""
        logger.info(f"/auto command received | channel={message.channel.id} cmd={cmd!r} state={describe_auto_state(auto_state, message.channel.id)}")
        st = _prune_auto_state(message.channel.id)

        if cmd == "stop":
            if st and st.get("active"):
                st["active"] = False
                logger.info(f"/auto stop requested | channel={message.channel.id} state={describe_auto_state(auto_state, message.channel.id)}")
                await message.reply("🛑 正在停止（等待当前行动完成）...")
            else:
                await message.reply("ℹ️ 当前没有运行中的自主模式。")
            return

        if cmd == "status":
            if st and st.get("active"):
                await message.reply(f"🟢 自主模式运行中。发送 `/auto stop` 停止。\n`{describe_auto_state(auto_state, message.channel.id)}`")
            else:
                await message.reply("⚪ 自主模式未运行。")
            return

        # start — rest is the user directive (may be empty)
        directive = rest if cmd not in ("start", "") else rest[len("start"):].strip() if cmd == "start" else ""
        if st and st.get("active"):
            await message.reply("⚠️ 自主模式已在运行。发送 `/auto stop` 停止。")
            return

        auto_state[message.channel.id] = {"active": True, "directive": directive}
        task = asyncio.create_task(run_auto(message.channel, agent, auto_state, directive=directive))
        auto_state[message.channel.id]["task"] = task
        task.add_done_callback(lambda t, cid=message.channel.id: _on_auto_task_done(cid, t))
        dir_preview = f" | directive={directive[:60]}" if directive else ""
        logger.info(f"/auto task scheduled | channel={message.channel.id}{dir_preview} state={describe_auto_state(auto_state, message.channel.id)}")
        return

    if content in ("/pause", "/stop"):
        st = auto_state.get(message.channel.id)
        if st and st.get("active"):
            st["active"] = False
            await message.reply("🛑 自主模式正在停止（等待当前行动完成）...")
            return

        target_task = channel_tasks.get(message.channel.id)
        if target_task and not target_task.done():
            target_task.cancel()
            await message.reply("⏸️ 已请求暂停当前任务。")
        else:
            await message.reply("ℹ️ 当前没有可暂停的运行中任务。")
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

    existing_task = channel_tasks.get(message.channel.id)
    if message.channel.id in running_tasks:
        if existing_task is None or existing_task.done():
            logger.warning(f"Clearing stale running task gate | channel={message.channel.id}")
            running_tasks.discard(message.channel.id)
            channel_tasks.pop(message.channel.id, None)
        else:
            await message.reply("⏳ 正在处理另一个任务... 发送 `/pause` 可中断当前任务。")
            return

    st = _prune_auto_state(message.channel.id)

    if st and st.get("active"):
        await message.reply("⚠️ 自主模式运行中，发送 `/auto stop` 或 `/pause` 停止后再对话。")
        return

    running_tasks.add(message.channel.id)
    channel_tasks[message.channel.id] = asyncio.current_task()

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

    except asyncio.CancelledError:
        logger.info(f"Channel task cancelled: {message.channel.id}")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await message.reply(f"⚠️ 系统异常: {str(e)}")
    finally:
        channel_tasks.pop(message.channel.id, None)
        running_tasks.discard(message.channel.id)


if __name__ == "__main__":
    logger.info("Starting Discord client...")
    client.run(TOKEN)
