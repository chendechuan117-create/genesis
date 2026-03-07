import os
import asyncio
import logging
from pathlib import Path
import discord
from dotenv import load_dotenv

from genesis.core.factory import GenesisFactory

# 1. Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("DiscordBot")

# 2. Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if not TOKEN:
    logger.error("No DISCORD_BOT_TOKEN found in environment variables.")
    exit(1)

# 3. Setup Genesis V4 Agent (The Glassbox Amplifier)
logger.info("Initializing Genesis V4 Agent...")
agent = GenesisFactory.create_v4()

# 4. Setup Discord Client
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Keep track of running tasks to avoid overlapping execution in the same channel
running_tasks = set()

GENESIS_VERSION = "V4.2 (Glassbox)"

class DiscordCallback:
    """处理 V4 运行时回调，向 Discord 发送实时状态更新"""
    def __init__(self, message: discord.Message):
        self.message = message

    async def __call__(self, event_type: str, data: dict | str):
        try:
            if event_type == "blueprint":
                # 发送厂长装配单
                if len(data) > 2000:
                    chunks = [data[i:i+1990] for i in range(0, len(data), 1990)]
                    for c in chunks:
                        await self.message.channel.send(c)
                else:
                    await self.message.channel.send(data)

            elif event_type == "tool_start":
                # 简单提示节点亮起
                tool_name = data.get("name", "Unknown Node")
                await self.message.channel.send(f"🟢 **[节点激活]**: `{tool_name}` 运行中...")
                
            elif event_type == "tool_result":
                tool_name = data.get("name", "Unknown Node")
                result_peek = data.get("result", "")[:200]
                # 缩短日志以防刷屏
                await self.message.channel.send(f"✅ **[{tool_name} 节点反馈]**: \n```\n{result_peek}...\n```")
                
        except Exception as e:
            logger.error(f"Callback error: {e}")

@client.event
async def on_ready():
    logger.info(f"✅ Logged in as {client.user} (ID: {client.user.id})")
    logger.info(f"Genesis {GENESIS_VERSION} daemon is ready and listening for mentions.")

@client.event
async def on_message(message: discord.Message):
    # Ignore our own messages
    if message.author == client.user:
        return

    # Check if the bot is mentioned
    if client.user in message.mentions:
        # Extract the actual prompt by removing the bot mention (handle both <@ID> and <@!ID>)
        content = message.content
        content = content.replace(f"<@{client.user.id}>", "")
        content = content.replace(f"<@!{client.user.id}>", "")
        user_intent = content.strip()
        
        # Handle Attachments
        attachment_paths = []
        if message.attachments:
            upload_dir = Path("runtime/uploads")
            upload_dir.mkdir(parents=True, exist_ok=True)
            
            for attachment in message.attachments:
                # Use a safe filename
                safe_filename = f"{message.id}_{attachment.filename}"
                file_path = (upload_dir / safe_filename).resolve()
                try:
                    await attachment.save(file_path)
                    attachment_paths.append(str(file_path))
                    logger.info(f"📥 Saved attachment: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to save attachment {attachment.filename}: {e}")
        
        if not user_intent and not attachment_paths:
            await message.reply("嗯？找我什么事？")
            return

        # Prevent overlapping tasks in the same channel
        if message.channel.id in running_tasks:
            await message.reply("⏳ 我正在处理这个频道的另一个任务，请稍等...")
            return

        running_tasks.add(message.channel.id)

        try:
            async with message.channel.typing():
                # 1. 主动拉取频道近期的聊天记录（解决“没 @ 它的消息它看不见”的瞎子问题）
                channel_history_text = ""
                try:
                    # 获取该频道的最近 10 条消息（包含用户当前这条，所以取 11 条排除当前）
                    recent_messages = [msg async for msg in message.channel.history(limit=11, before=message)]
                    if recent_messages:
                        recent_messages.reverse() # 按时间正序
                        lines = ["[频道近期聊天环境（供你参考，了解当前语境）：]"]
                        for msg in recent_messages:
                            # 如果是 bot 自己的消息，标明是 Genesis
                            author_name = "Genesis" if msg.author == client.user else msg.author.display_name
                            
                            # 提取内容，如果有附件也简单提及
                            msg_content = msg.clean_content.replace('\n', ' ')
                            if msg.attachments:
                                msg_content += " [含附件]"
                            
                            # 限制单条消息长度，防刷屏
                            if len(msg_content) > 300:
                                msg_content = msg_content[:300] + "..."
                                
                            lines.append(f"{author_name}: {msg_content}")
                        lines.append("────────────────────")
                        channel_history_text = "\n".join(lines) + "\n\n"
                except Exception as e:
                    logger.warning(f"Failed to fetch channel history: {e}")

                # 2. 组装最终输入
                full_input = user_intent
                if attachment_paths:
                    files_str = "\n".join(f"  - {p}" for p in attachment_paths)
                    full_input += f"\n\n[Attached files saved locally:\n{files_str}]"
                    
                full_input = f"{channel_history_text}[当前请求]\n{full_input}"

                # V4 接入 UI 拦截器（记忆由 Sedimenter 在 loop 内部持久化处理）
                ui_callback = DiscordCallback(message)
                
                result = await agent.process(full_input, step_callback=ui_callback)
                response = result.get("response", "...")

                # Chunk response if too long
                if len(response) > 2000:
                    response_chunks = [response[i:i+2000] for i in range(0, len(response), 2000)]
                    for chunk in response_chunks:
                        await message.reply(chunk)
                else:
                    await message.reply(response)
                
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            await message.reply(f"⚠️ 系统异常: {str(e)}")
        finally:
            # Always remove from running tasks when done
            running_tasks.remove(message.channel.id)

if __name__ == "__main__":
    logger.info("Starting Discord client...")
    client.run(TOKEN)
