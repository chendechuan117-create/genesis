
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "nanogenesis"))

from genesis.core.capability import CapabilityScanner

def test_capability_scanner():
    print("🚀 Initializing Capability Scanner...")
    
    print("\n1. Running Full Scan...")
    snapshot = CapabilityScanner.scan()
    
    # OS
    print(f"   OS: {snapshot['os']}")
    assert snapshot['os'] != "Unknown OS"
    
    # Network
    print(f"   Network: {snapshot['network']}")
    
    # Permissions
    print(f"   Permissions: {snapshot['permissions']}")
    
    # Tools
    print(f"   Tools: {snapshot['tools']}")
    assert "git" in snapshot['tools']
    assert "python3" in snapshot['tools']
    
    # ADB
    print(f"   ADB: {snapshot['adb']}")
    
    print("\n✅ Capability Scanner Test PASSED!")
    
    return snapshot

if __name__ == "__main__":
    test_capability_scanner()
