
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "nanogenesis"))

from genesis.core.mission import MissionManager

def test_mission_tree():
    print("🚀 Initializing Mission Manager...")
    # Use a temporary DB for testing
    db_path = Path("/tmp/genesis_test_mission.sqlite")
    if db_path.exists():
        db_path.unlink()
        
    manager = MissionManager(str(db_path))
    
    print("\n1. Creating Root Mission: 'Deploy scrcpy'")
    root = manager.create_mission("Deploy scrcpy")
    print(f"   Root ID: {root.id}, Root Parent: {root.parent_id}")
    assert root.depth == 0
    assert root.root_id == root.id
    
    print("\n2. Creating Sub-Mission: 'Check USB status' (Child of Root)")
    sub1 = manager.create_mission("Check USB status", parent_id=root.id)
    print(f"   Sub1 ID: {sub1.id}, Parent: {sub1.parent_id}, Depth: {sub1.depth}")
    assert sub1.parent_id == root.id
    assert sub1.depth == 1
    assert sub1.root_id == root.id
    
    print("\n3. Creating Leaf Mission: 'Run lsusb' (Child of Sub-Mission)")
    leaf = manager.create_mission("Run lsusb", parent_id=sub1.id)
    print(f"   Leaf ID: {leaf.id}, Parent: {leaf.parent_id}, Depth: {leaf.depth}")
    assert leaf.depth == 2
    assert leaf.root_id == root.id
    
    print("\n4. Verifying Lineage (Leaf -> Root)")
    lineage = manager.get_mission_lineage(leaf.id)
    print(f"   Lineage Length: {len(lineage)}")
    for i, m in enumerate(lineage):
        print(f"   [{i}] Depth {m.depth}: {m.objective}")
        
    assert len(lineage) == 3
    assert lineage[0].id == root.id
    assert lineage[1].id == sub1.id
    assert lineage[2].id == leaf.id
    
    print("\n✅ Mission Context Tree Test PASSED!")

if __name__ == "__main__":
    test_mission_tree()
