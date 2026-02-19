
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "nanogenesis"))

from genesis.core.entropy import EntropyMonitor

def test_entropy_logic():
    print("🚀 Testing EntropyMonitor Logic...")
    
    monitor = EntropyMonitor(window_size=3)
    
    # State 1
    monitor.capture("Output A", "/tmp", "mission_1")
    print(f"1. Captured State A. Stagnant? {monitor.is_stagnant()}")
    assert not monitor.is_stagnant()
    
    # State 2 (Different)
    monitor.capture("Output B", "/tmp", "mission_1")
    print(f"2. Captured State B. Stagnant? {monitor.is_stagnant()}")
    assert not monitor.is_stagnant()
    
    # State 3 (Same as B - Repeat 1)
    monitor.capture("Output B", "/tmp", "mission_1")
    print(f"3. Captured State B (Repeat 1). Stagnant? {monitor.is_stagnant()}")
    assert not monitor.is_stagnant() # History: [A, B, B] -> Not all same
    
    # State 4 (Same as B - Repeat 2)
    monitor.capture("Output B", "/tmp", "mission_1")
    print(f"4. Captured State B (Repeat 2). Stagnant? {monitor.is_stagnant()}")
    # History: [B, B, B] -> All same!
    assert monitor.is_stagnant()
    print("✅ Stagnation Detected correctly!")

    # State 5 (New State)
    monitor.capture("Output C", "/tmp", "mission_1")
    print(f"5. Captured State C. Stagnant? {monitor.is_stagnant()}")
    assert not monitor.is_stagnant()
    print("✅ Stagnation Cleared correctly!")
    
    print("\n✅ EntropyMonitor Test PASSED!")

if __name__ == "__main__":
    test_entropy_logic()
