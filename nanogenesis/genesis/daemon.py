
import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Optional
import time

from genesis.core.factory import GenesisFactory
from genesis.core.diagnostic import DiagnosticManager
from genesis.core.mission import MissionManager

# Configure Daemon Logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(Path.home() / ".nanogenesis" / "guardian.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("guardian")

class GenesisDaemon:
    """
    Genesis Guardian Daemon
    Runs the agent in a 7x24h background loop (Observe -> Decide -> Act).
    """

    def __init__(self):
        self.agent = None
        self.mission_manager = MissionManager()
        self.running = False
        self.tick_interval = 10 # Check frequently (10s)
        self.shutdown_event = asyncio.Event()

    async def initialize(self):
        """Initialize the agent and components"""
        logger.info("🛡️ Initializing Genesis Guardian...")
        try:
            # Create Agent
            self.agent = GenesisFactory.create_common(enable_optimization=True)
            
            # Start Scheduler
            if self.agent.scheduler:
                await self.agent.scheduler.start()
                logger.info("✅ Scheduler started")
            
            logger.info("🚀 Guardian System Ready")
            
        except Exception as e:
            logger.critical(f"❌ Initialization failed: {e}", exc_info=True)
            sys.exit(1)

    async def run_forever(self):
        """Main Daemon Loop"""
        await self.initialize()
        
        self.running = True
        
        # Setup Signal Handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self.shutdown(s)))
            
        logger.info("🕹️ Entering Guardian Loop")
        
        while self.running:
            try:
                # 1. Heartbeat / Observation
                await self._tick()
                
                # 2. Wait for next tick (or shutdown)
                try:
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=self.tick_interval)
                    break # Event set, exit loop
                except asyncio.TimeoutError:
                    continue # Timeout reached, next tick
                    
            except Exception as e:
                logger.error(f"⚠️ Error in daemon loop: {e}", exc_info=True)
                await asyncio.sleep(5) # Backoff
                
        await self._cleanup()

    async def _tick(self):
        """Single Loop Iteration: Observe & Decide"""
        # 1. Self-Diagnostic
        # Periodically check health (every 60 mins or so? For now every tick is too much)
        # Let's just log a heartbeat for now.
        logger.debug("💓 Guardian Heartbeat")
        
        # 2. Mission Control
        active_mission = self.mission_manager.get_active_mission()
        if active_mission:
            logger.info(f"🎯 Resuming Mission: {active_mission.objective} (ID: {active_mission.id})")
            
            # Execute one step of autonomy
            try:
                # Check for circuit breaker (Mission Level)
                if active_mission.error_count >= 5:
                    logger.warning(f"🛑 Mission '{active_mission.objective}' exceeded error threshold (5). PAUSING.")
                    self.mission_manager.update_mission(active_mission.id, status="paused", last_error="Auto-Paused: Excessive Errors")
                    return

                # Execute Step
                if hasattr(self.agent, "autonomous_step"):
                     result = await self.agent.autonomous_step(active_mission)
                     
                     if result.get("status") == "error":
                         raise RuntimeError(result.get("error"))
                         
                     logger.info(f"✅ Mission Step Result: {result.get('tools_executed')} tools, Output: {str(result.get('output'))[:50]}...")
                     
                     # Success - reset error count
                     if active_mission.error_count > 0:
                         self.mission_manager.update_mission(active_mission.id, error_count=0)
                else:
                     logger.warning("⚠️ Agent lacks autonomous_step capability. Skipping mission.")
                     
            except Exception as e:
                logger.error(f"❌ Mission Execution Failed: {e}", exc_info=True)
                
                # Update error state
                new_count = active_mission.error_count + 1
                self.mission_manager.update_mission(
                    active_mission.id,
                    error_count=new_count,
                    last_error=str(e)[:200]
                )
                
        else:
            logger.debug("💤 No active mission. Sleeping.")

    async def shutdown(self, sig):
        """Graceful Shutdown"""
        logger.info(f"🛑 Received signal {sig.name}, shutting down...")
        self.running = False
        self.shutdown_event.set()

    async def _cleanup(self):
        """Cleanup resources"""
        if self.agent and self.agent.scheduler:
            await self.agent.scheduler.stop()
        logger.info("👋 Guardian Shutdown Complete")

if __name__ == "__main__":
    daemon = GenesisDaemon()
    try:
        asyncio.run(daemon.run_forever())
    except KeyboardInterrupt:
        # Handled by signal handler usually, but just in case
        pass
