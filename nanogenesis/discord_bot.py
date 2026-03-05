import os
import asyncio
import logging
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

# 3. Setup Genesis V2 Agent
logger.info("Initializing Genesis V2 Agent...")
agent = GenesisFactory.create_v2()

# 4. Setup Discord Client
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Keep track of running tasks to avoid overlapping execution in the same channel
running_tasks = set()

@client.event
async def on_ready():
    logger.info(f"✅ Logged in as {client.user} (ID: {client.user.id})")
    logger.info("Genesis 7*24h daemon is ready and listening for mentions.")

@client.event
async def on_message(message: discord.Message):
    # Ignore our own messages
    if message.author == client.user:
        return

    # Check if the bot is mentioned
    if client.user in message.mentions:
        # Extract the actual prompt by removing the bot mention
        user_intent = message.content.replace(f"<@{client.user.id}>", "").strip()
        
        if not user_intent:
            await message.reply("嗯？找我什么事？")
            return

        # Prevent overlapping tasks in the same channel
        if message.channel.id in running_tasks:
            await message.reply("⏳ 我正在处理这个频道的另一个任务，请稍等...")
            return

        running_tasks.add(message.channel.id)
        
        try:
            # Send initial reaction/message to show we are working on it
            status_msg = await message.reply("🔄 厂长正在思考和处理...")
            
            logger.info(f"Received task from {message.author}: {user_intent}")
            
            # Execute through Genesis V2
            result = await agent.process(user_intent)
            
            # Formatting the output
            if result.get("success"):
                response_text = result.get("response", "任务完成，但没有返回具体文本。")
                # Discord max message length is 2000 chars
                if len(response_text) > 1900:
                    response_text = response_text[:1900] + "\n...[内容过长已截断]"
                
                await status_msg.edit(content=f"✅ **完成**:\n{response_text}")
            else:
                error_msg = result.get("response", "未知错误")
                await status_msg.edit(content=f"❌ **执行失败**:\n{error_msg}")
                
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            await message.reply(f"⚠️ 系统异常: {str(e)}")
        finally:
            # Always remove from running tasks when done
            running_tasks.remove(message.channel.id)

if __name__ == "__main__":
    logger.info("Starting Discord client...")
    client.run(TOKEN)
