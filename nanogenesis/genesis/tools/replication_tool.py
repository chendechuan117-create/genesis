import shutil
import subprocess
import os
from pathlib import Path
from typing import Dict, Any, Optional

class ReplicationTool:
    """
    Tool for Genesis to clone itself (Self-Replication).
    Enables Phase 10: Hive Mind Scaling.
    """
    
    def __init__(self):
        self.name = "replication_tool"
        self.description = "Clone the Genesis agent's source code to a new location (mitosis)."
        self.parameters = {
            "type": "object",
            "properties": {
                "target_path": {
                    "type": "string",
                    "description": "Absolute path to the target directory for the new clone."
                },
                "worker_id": {
                    "type": "string",
                    "description": "Optional ID for the new worker (e.g., 'worker_1'). used for config naming."
                }
            },
            "required": ["target_path"]
        }

    def execute(self, target_path: str, worker_id: str = "worker_unknown") -> Dict[str, Any]:
        """Execute self-replication logic"""
        try:
            target = Path(target_path).resolve()
            source = Path.cwd().resolve() # Assuming we run from root
            
            # Safety Checks
            if target == source:
                return {"status": "error", "error": "Cannot clone into self."}
            if target.exists() and any(target.iterdir()):
                 return {"status": "error", "error": f"Target directory {target} is not empty."}
            if not str(target).startswith("/home/chendechusn"):
                 return {"status": "error", "error": "Permission Denied: Can only clone within user home."}

            # 1. Try Git Clone (cleanest method)
            if (source / ".git").exists():
                try:
                    subprocess.run(
                        ["git", "clone", str(source), str(target)], 
                        check=True, 
                        capture_output=True
                    )
                    method = "git_clone"
                except subprocess.CalledProcessError as e:
                    return {"status": "error", "error": f"Git clone failed: {e.stderr.decode()}"}
            else:
                # Fallback: Copy files (excluding .git, venv, brain, etc.)
                ignore_patterns = shutil.ignore_patterns(
                    ".git", "__pycache__", "venv", ".nanogenesis", "brain", "*.pyc", ".env"
                )
                shutil.copytree(source, target, ignore=ignore_patterns)
                method = "direct_copy"

            # 2. Post-Replication Cleanup (Resource Negotiation Prep)
            # Remove existing config to force new worker to "negotiate" (ask user)
            config_path = target / "config.json"
            if config_path.exists():
                os.remove(config_path)
            
            # Create a marker file
            with open(target / "GENESIS_WORKER_ID", "w") as f:
                f.write(worker_id)

            return {
                "status": "success",
                "message": f"Successfully cloned Genesis to {target}",
                "method": method,
                "worker_id": worker_id,
                "next_steps": "Navigate to target and run 'python3 genesis_daemon.py'. Note: You will need to provide API keys."
            }

        except Exception as e:
            return {"status": "error", "error": str(e)}
