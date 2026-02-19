
import asyncio
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "nanogenesis"))

from genesis.tools.shell_tool import ShellTool
from genesis.core.jobs import JobManager

async def test_job_system():
    print("🚀 Initializing ShellTool with Job System...")
    
    # Manually wire them up for testing
    job_mgr = JobManager()
    tool = ShellTool(job_manager=job_mgr)
    
    # 1. Spawn a Job (20s sleep)
    print("\n1. Spawning Long Job...")
    spawn_res = await tool.execute(command="echo 'Starting...'; sleep 10; echo 'Done!'", action="spawn")
    print(spawn_res)
    
    # Extract ID
    job_id = spawn_res.split("ID: ")[1].strip().split()[0]
    print(f"   Target Job ID: {job_id}")
    
    # 2. Poll immediately (Running)
    print("\n2. Polling Immediate Status...")
    poll_res = await tool.execute(job_id=job_id, action="poll")
    print(poll_res)
    assert "RUNNING" in poll_res
    
    # 3. List Jobs
    print("\n3. Listing Active Jobs...")
    list_res = await tool.execute(action="list_jobs")
    print(list_res)
    assert job_id in list_res
    
    # 4. Wait for completion
    print("\n4. Waiting for completion (12s)...")
    await asyncio.sleep(12)
    
    # 5. Poll Final Status
    print("\n5. Polling Final Status...")
    final_res = await tool.execute(job_id=job_id, action="poll")
    print(final_res)
    assert "COMPLETED" in final_res
    assert "Done!" in final_res
    
    print("\n✅ Job System Test PASSED!")

if __name__ == "__main__":
    asyncio.run(test_job_system())
