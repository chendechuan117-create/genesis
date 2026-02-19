#!/usr/bin/env python3
"""
Genesis Mission Control (CTL)
用于从命令行直接向 Genesis Daemon 下达指令，无需进入 REPL。
用法:
    python3 genesis_ctl.py start "Your Mission Objective"
    python3 genesis_ctl.py status
    python3 genesis_ctl.py stop
    python3 genesis_ctl.py list
"""

import sys
import argparse
from pathlib import Path

# 添加项目根目录和 nanogenesis 目录到 sys.path
root_dir = Path(__file__).parent
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "nanogenesis"))

from genesis.core.mission import MissionManager

def main():
    parser = argparse.ArgumentParser(description="Genesis Mission Control")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Start Command
    start_parser = subparsers.add_parser("start", help="Start a new mission")
    start_parser.add_argument("objective", type=str, help=" The mission objective description")

    # Status Command
    subparsers.add_parser("status", help="Get status of the current active mission")

    # Stop Command
    subparsers.add_parser("stop", help="Pause/Stop the currently active mission")

    # List Command
    subparsers.add_parser("list", help="List recent missions")

    args = parser.parse_args()
    
    manager = MissionManager()

    if args.command == "start":
        print(f"🚀 Dispatching Mission to Daemon: '{args.objective}'")
        mission = manager.create_mission(args.objective)
        print(f"✅ Mission Created! (ID: {mission.id})")
        print("The Guardian Daemon will pick this up in < 5 seconds.")

    elif args.command == "status":
        mission = manager.get_active_mission()
        if mission:
            print("\n🟢 ACTIVE MISSION")
            print(f"ID: {mission.id}")
            print(f"Objective: {mission.objective}")
            print(f"Status: {mission.status}")
            print(f"Errors: {mission.error_count}")
            if mission.context_snapshot and 'last_output' in mission.context_snapshot:
                 print(f"Last Output: {mission.context_snapshot['last_output'][:100]}...")
        else:
            print("💤 No active mission. Daemon is idle.")

    elif args.command == "stop":
        mission = manager.get_active_mission()
        if mission:
            manager.update_mission(mission.id, status="paused")
            print(f"⏸️  Mission Paused: {mission.objective}")
        else:
            print("❌ No running mission to stop.")

    elif args.command == "list":
        missions = manager.list_missions()
        print(f"📜 Recent Missions ({len(missions)}):")
        for m in missions:
            print(f"[{m.status.upper().ljust(8)}] {m.created_at[:19]} - {m.objective[:50]}...")

    else:
        parser.print_help()

if __name__ == "__main__":
    main()
