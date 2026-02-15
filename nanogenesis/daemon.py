
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nanogenesis.agent import NanoGenesis

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path.home() / ".nanogenesis" / "daemon.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("genesis-daemon")

async def main():
    logger.info("🚀 Genesis Daemon starting...")
    
    try:
        # Initialize Agent
        agent = NanoGenesis(
            enable_optimization=True
        )
        
        # Start the Background Scheduler (7x24h Heartbeat)
        if agent.scheduler:
            await agent.scheduler.start()
            logger.info("✅ Background Scheduler is now active.")
        
        # Start Web Server (optional, but keep process alive)
        # For a pure daemon, we just wait forever
        logger.info("Genesis is now resident. Monitoring background jobs...")
        
        while True:
            await asyncio.sleep(3600)  # Wake up every hour to log heartbeat
            logger.info("💓 Heartbeat: Genesis is still watching.")
            
    except Exception as e:
        logger.error(f"❌ Daemon encountered an error: {e}")
        import traceback
        logger.error(traceback.format_exc())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Daemon stopping...")
