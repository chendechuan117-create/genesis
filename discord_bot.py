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
                task_brief = (data or {}).get("task_brief", "") if isinstance(data, dict) else ""
                persona_str = " / ".join(f"`{p}`" for p in personas)
                brief_preview = task_brief[:200] if task_brief else ""
                msg = f"🔭 **Multi-G 透镜启动** | 知识密度探针: {probe_hits} 命中 → {len(personas)} 个视角\n{persona_str}"
                if brief_preview:
                    msg += f"\n📋 **G 布置的搜索作业：**\n```\n{brief_preview}\n```"
                await self.message.channel.send(msg)
            elif evt.event_type == "lens_search":
                info = data if isinstance(data, dict) else {}
                persona = info.get("persona", "?")
                query = info.get("query", [])
                query_str = ", ".join(query) if isinstance(query, list) else str(query)
                await self.message.channel.send(f"🔭 `Lens-{persona}` 搜索: {query_str[:100]}")
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


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    if client.user in message.mentions:
        content = message.content
        content = content.replace(f"<@{client.user.id}>", "")
        content = content.replace(f"<@!{client.user.id}>", "")
        user_intent = content.strip()

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
                response = result.get("response", "...")
                
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
