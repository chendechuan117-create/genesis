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
                # --- V2 Architecture: Use SensoryCortex ---
                cortex = SensoryCortex()
                packet = await cortex.perceive(
                    text_input=user_intent,
                    attachments=attachment_paths,
                    source="discord",
                    context_id=str(message.channel.id)
                )

                # Process with Genesis V2 (Agent accepts packet now)
                result = await agent.process(packet, use_v2=True)
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
