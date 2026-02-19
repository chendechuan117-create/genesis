
import sys
from pathlib import Path

# Add CWD to sys.path (Assuming running from /home/chendechusn/Genesis/nanogenesis)
sys.path.insert(0, str(Path.cwd()))

def verify():
    try:
        print("Testing genesis.core...")
        import genesis.core
        print("✓ genesis.core loaded")

        print("Testing genesis.memory...")
        import genesis.memory
        print("✓ genesis.memory loaded")

        print("Testing genesis.agent...")
        from genesis.agent import NanoGenesis
        print("✓ genesis.agent loaded")

        print("✨ STRUCTURE VERIFICATION PASSED ✨")
    except ImportError as e:
        print(f"❌ Import Failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ General Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    verify()
