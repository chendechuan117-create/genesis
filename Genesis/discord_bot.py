import os
import asyncio
import logging
from pathlib import Path
import discord
from dotenv import load_dotenv

from factory import create_agent

# 1. Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("DiscordBot")

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
            if event_type == "blueprint":
                if len(data) > 2000:
                    for i in range(0, len(data), 1990):
                        await self.message.channel.send(data[i:i+1990])
                else:
                    await self.message.channel.send(data)
            elif event_type == "tool_start":
                tool_name = data.get("name", "?")
                await self.message.channel.send(f"🟢 `{tool_name}` 运行中...")
            elif event_type == "search_result":
                # 搜索结果专用格式化：提取节点清单，类似蓝图的「已加载认知节点」风格
                formatted = self._format_search_result(data)
                if len(formatted) > 2000:
                    for i in range(0, len(formatted), 1990):
                        await self.message.channel.send(formatted[i:i+1990])
                else:
                    await self.message.channel.send(formatted)
            elif event_type == "tool_result":
                tool_name = data.get("name", "?")
                result_peek = data.get("result", "")[:200]
                await self.message.channel.send(f"✅ **[{tool_name}]**:\n```\n{result_peek}\n```")
        except Exception as e:
            logger.error(f"Callback error: {e}")

    @staticmethod
    def _format_search_result(raw: str) -> str:
        """将搜索结果格式化为类似「已加载认知节点」的直观风格"""
        lines = raw.strip().split("\n")
        output = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # 提取节点行: [语义]/<字面> <TYPE> [NODE_ID] title | tags:...
            if line.startswith("[语义]") or line.startswith("[字面]"):
                # 去掉来源标签和 tags 后缀，只保留类型+ID+标题
                source = "🔮" if line.startswith("[语义]") else "🔤"
                # 找到 <TYPE> [NODE_ID] title 部分
                rest = line.split(">", 1)[-1].strip() if ">" in line else line
                # 提取 [NODE_ID] 和标题（tags之前的部分）
                if "|" in rest:
                    rest = rest.split("|")[0].strip()
                output.append(f"{source} {rest}")
            elif line.startswith("└─"):
                # 依赖节点
                rest = line.split(">", 1)[-1].strip() if ">" in line else line
                if "|" in rest:
                    rest = rest.split("|")[0].strip()
                output.append(f"  🔗 {rest}")
            elif "未找到" in line or "未命中" in line or "知识库为空" in line:
                output.append(f"⚠️ {line}")
            elif line.startswith("🔍"):
                # 搜索头部，保留查询词
                output.append(line)
            # 跳过其他提示行（系统提示等）
        
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
        if message.attachments:
            upload_dir = Path("runtime/uploads")
            upload_dir.mkdir(parents=True, exist_ok=True)
            for att in message.attachments:
                fp = (upload_dir / f"{message.id}_{att.filename}").resolve()
                try:
                    await att.save(fp)
                    attachment_paths.append(str(fp))
                except Exception as e:
                    logger.error(f"Attachment save failed: {e}")

        if not user_intent and not attachment_paths:
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

                full_input = f"{channel_ctx}[当前请求]\n{full_input}"

                ui_callback = DiscordCallback(message)
                result = await agent.process(full_input, step_callback=ui_callback)
                response = result.get("response", "...")

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
