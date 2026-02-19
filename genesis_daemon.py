#!/usr/bin/env python3

import sys
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent / "nanogenesis"))

from genesis.daemon import GenesisDaemon

def main():
    daemon = GenesisDaemon()
    try:
        asyncio.run(daemon.run_forever())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
