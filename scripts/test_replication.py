
import sys
from pathlib import Path
import shutil

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "nanogenesis"))

from genesis.tools.replication_tool import ReplicationTool

def test_replication():
    print("🧬 Testing Genesis Self-Replication...")
    
    repl_tool = ReplicationTool()
    
    # Target Path
    target_dir = Path.home() / "Genesis_Replication_Test"
    
    # Clean up previous test
    if target_dir.exists():
        print(f"🧹 Cleaning up existing test dir: {target_dir}")
        shutil.rmtree(target_dir)
        
    print(f"🚀 Cloning to: {target_dir}")
    
    try:
        result = repl_tool.execute(str(target_dir), worker_id="test_worker_01")
        
        if result.get("status") == "success":
            print(f"✅ Success: {result['message']}")
            print(f"   Method Used: {result['method']}")
            
            # Verify Contents
            if (target_dir / "genesis_daemon.py").exists():
                print("   [Check] Daemon script exists.")
            else:
                 print("   [Fail] Daemon script missing!")
                 
            if (target_dir / "config.json").exists():
                 print("   [Fail] config.json should have been deleted!")
            else:
                 print("   [Check] config.json correctly removed (Resource Negotiation Prep).")
                 
            if (target_dir / "GENESIS_WORKER_ID").exists():
                 with open(target_dir / "GENESIS_WORKER_ID") as f:
                     wid = f.read().strip()
                 print(f"   [Check] Worker ID set to: {wid}")
            else:
                 print("   [Fail] Worker ID marker missing!")

        else:
            print(f"❌ Failed: {result.get('error')}")
            
    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    test_replication()
