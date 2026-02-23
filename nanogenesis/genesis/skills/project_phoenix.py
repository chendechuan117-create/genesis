import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import os
import subprocess
import sys
from datetime import datetime

class ProjectPhoenixTool:
    name = "project_phoenix"
    description = "Executes the Project Phoenix protocols (Lightweight Mode) in sequence."
    parameters = {
        "type": "object",
        "properties": {}
    }

    def execute(self, args):
        """Execute the four-step protocol."""
        results = {}
        
        # Step 1: List files in 'nanogenesis/genesis/core' to verify structure.
        print("=== Step 1: Verifying 'nanogenesis/genesis/core' structure ===")
        target_path = "/home/chendechusn/nanabot/nanogenesis/genesis/core"
        if os.path.isdir(target_path):
            try:
                list_output = subprocess.check_output(["ls", "-la", target_path], 
                                                    stderr=subprocess.STDOUT, 
                                                    text=True)
                results['step1'] = {"status": "SUCCESS", "output": list_output}
                print(f"Directory exists. Contents:\n{list_output}")
            except subprocess.CalledProcessError as e:
                results['step1'] = {"status": "FAILED", "error": e.output}
                print(f"Failed to list directory: {e.output}")
        else:
            results['step1'] = {"status": "FAILED", "error": f"Directory not found: {target_path}"}
            print(f"ERROR: Directory not found: {target_path}")
            # Attempt to find the correct path
            print("Searching for 'nanogenesis' root...")
            try:
                find_output = subprocess.check_output(["find", "/home/chendechusn", "-type", "d", "-name", "nanogenesis"], 
                                                    stderr=subprocess.DEVNULL, 
                                                    text=True)
                print(f"Found 'nanogenesis' at:\n{find_output}")
                results['step1_alternative'] = find_output
            except Exception as e:
                print(f"Search failed: {e}")
        
        # Step 2: Create a file 'stress_test_log.txt' with the current timestamp.
        print("\n=== Step 2: Creating 'stress_test_log.txt' ===")
        log_file = "stress_test_log.txt"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(log_file, 'w') as f:
                f.write(f"Project Phoenix Stress Test Log\n")
                f.write(f"Timestamp: {timestamp}\n")
                f.write(f"Status: INITIATED\n")
            results['step2'] = {"status": "SUCCESS", "file": log_file, "timestamp": timestamp}
            print(f"Created '{log_file}' with timestamp: {timestamp}")
        except Exception as e:
            results['step2'] = {"status": "FAILED", "error": str(e)}
            print(f"Failed to create log file: {e}")
        
        # Step 3: Execute 'replication_tool' to clone the entire Genesis system.
        print("\n=== Step 3: Executing replication_tool ===")
        backup_dir = "/home/chendechusn/Genesis_Phoenix_Backup"
        # First, check if replication_tool exists and is executable
        replication_tool_path = None
        potential_paths = [
            "/home/chendechusn/nanabot/nanogenesis/scripts/replication_tool",
            "/home/chendechusn/nanabot/nanogenesis/replication_tool",
            "./replication_tool",
            "replication_tool"
        ]
        for path in potential_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                replication_tool_path = path
                break
        
        if replication_tool_path:
            print(f"Found replication_tool at: {replication_tool_path}")
            try:
                # Ensure backup directory exists or create it
                os.makedirs(backup_dir, exist_ok=True)
                cmd = [replication_tool_path, backup_dir]
                # Use a timeout to prevent hanging
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if proc.returncode == 0:
                    results['step3'] = {"status": "SUCCESS", "output": proc.stdout, "backup_dir": backup_dir}
                    print(f"Replication completed to: {backup_dir}")
                else:
                    results['step3'] = {"status": "FAILED", "error": proc.stderr, "returncode": proc.returncode}
                    print(f"Replication failed with return code {proc.returncode}: {proc.stderr}")
            except subprocess.TimeoutExpired:
                results['step3'] = {"status": "TIMEOUT", "note": "Replication may still be running in background."}
                print("Replication tool timed out (120s). It may be running in background.")
            except Exception as e:
                results['step3'] = {"status": "FAILED", "error": str(e)}
                print(f"Failed to execute replication_tool: {e}")
        else:
            results['step3'] = {"status": "FAILED", "error": "Could not find executable 'replication_tool'."}
            print("ERROR: Could not find executable 'replication_tool'. Searching...")
            try:
                find_tool = subprocess.check_output(["find", "/home/chendechusn", "-type", "f", "-name", "replication_tool", "-executable"], 
                                                  stderr=subprocess.DEVNULL, 
                                                  text=True)
                print(f"Found replication_tool candidates:\n{find_tool}")
                results['step3_search'] = find_tool
            except Exception as e:
                print(f"Search failed: {e}")
        
        # Step 4: Verify the backup exists.
        print("\n=== Step 4: Verifying backup ===")
        if os.path.isdir(backup_dir):
            try:
                verify_output = subprocess.check_output(["ls", "-F", backup_dir], 
                                                      stderr=subprocess.STDOUT, 
                                                      text=True)
                results['step4'] = {"status": "SUCCESS", "output": verify_output}
                print(f"Backup directory exists. Contents:\n{verify_output}")
            except subprocess.CalledProcessError as e:
                results['step4'] = {"status": "FAILED", "error": e.output}
                print(f"Failed to list backup directory: {e.output}")
        else:
            results['step4'] = {"status": "FAILED", "error": f"Backup directory not found: {backup_dir}"}
            print(f"ERROR: Backup directory not found: {backup_dir}")
        
        # Final Status Report
        print("\n=== Project Phoenix Protocol Completion Report ===")
        all_success = all(step.get('status') == 'SUCCESS' for step in [results.get('step1'), results.get('step2'), results.get('step3'), results.get('step4')] if step)
        
        if all_success:
            print("✅ ALL STEPS COMPLETED SUCCESSFULLY")
        else:
            print("⚠️  SOME STEPS FAILED OR HAD ISSUES")
            for step_name, step_result in results.items():
                if 'status' in step_result:
                    print(f"  {step_name}: {step_result['status']}")
        
        # Append final status to log file
        try:
            with open(log_file, 'a') as f:
                f.write(f"\nCompletion Report: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Overall Status: {'SUCCESS' if all_success else 'PARTIAL/FAILURE'}\n")
                for step_name, step_result in results.items():
                    if 'status' in step_result:
                        f.write(f"  {step_name}: {step_result['status']}\n")
        except Exception as e:
            print(f"Could not update log file: {e}")
        
        return {"results": results, "overall_success": all_success}

# Tool class must be named 'Tool' for the system to load it
Tool = ProjectPhoenixTool