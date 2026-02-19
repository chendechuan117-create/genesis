import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

import os
import sys
import subprocess
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

class SystemSnapshotTool(Tool):
    name = "SystemSnapshotTool"
    description = "Generates a comprehensive snapshot of the AI system's operational state."
    parameters = {
        "output_path": {
            "type": "string",
            "description": "Optional. The file path to save the markdown report. If not provided, the report is returned as a string.",
            "required": False
        },
        "scan_projects": {
            "type": "boolean",
            "description": "Whether to perform a deep scan of project directories for TODOs, recent changes, and structure. Defaults to True.",
            "required": False,
            "default": True
        }
    }

    def _run_shell(self, cmd: str, timeout: int = 10) -> Dict[str, Any]:
        """Run a shell command and return stdout, stderr, and returncode."""
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            return {
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "returncode": result.returncode,
                "success": result.returncode == 0
            }
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": f"Command timed out after {timeout}s", "returncode": -1, "success": False}
        except Exception as e:
            return {"stdout": "", "stderr": str(e), "returncode": -1, "success": False}

    def _get_environment_info(self) -> Dict[str, Any]:
        """Collect basic system and Python environment information."""
        info = {}
        # System info
        uname = self._run_shell("uname -a")
        info["system"] = uname["stdout"] if uname["success"] else "Unknown"
        
        # Python info
        info["python_version"] = sys.version
        info["python_path"] = sys.executable
        
        # Current user and directory
        info["current_user"] = os.getenv("USER", "unknown")
        info["current_dir"] = os.getcwd()
        
        # Check key directories
        key_dirs = ["/home/ubuntu", "/tmp", "/var/log"]
        info["key_dirs_exist"] = {d: os.path.isdir(d) for d in key_dirs}
        
        return info

    def _get_tool_health(self) -> Dict[str, Any]:
        """Perform a basic health check on available tools by testing their presence or a simple operation."""
        tools_to_check = [
            ("read_file", "ls /etc/hosts 2>/dev/null | head -1"),
            ("write_file", "echo 'test' > /tmp/tool_test.txt && rm /tmp/tool_test.txt"),
            ("shell", "echo 'ok'"),
            ("list_directory", "ls /home 2>/dev/null | head -5"),
        ]
        
        health = {}
        for tool_name, test_cmd in tools_to_check:
            result = self._run_shell(test_cmd, timeout=5)
            health[tool_name] = {
                "test_command": test_cmd,
                "success": result["success"],
                "details": result["stdout"] if result["success"] else result["stderr"]
            }
        return health

    def _scan_project_dir(self, base_path: str = "/home/ubuntu") -> Dict[str, Any]:
        """Scan for project directories and gather high-level info."""
        projects = {}
        try:
            for item in os.listdir(base_path):
                item_path = os.path.join(base_path, item)
                if os.path.isdir(item_path):
                    # Heuristic: consider directories with certain markers as projects
                    markers = [".git", "requirements.txt", "pyproject.toml", "README.md", "src"]
                    has_marker = any(os.path.exists(os.path.join(item_path, m)) for m in markers)
                    
                    if has_marker:
                        proj_info = {"path": item_path}
                        
                        # Check for .git (version control)
                        if os.path.isdir(os.path.join(item_path, ".git")):
                            git_log = self._run_shell(f"cd {item_path} && git log --oneline -3 2>/dev/null || echo 'No git info'")
                            proj_info["recent_commits"] = git_log["stdout"].split('\n')[:3] if git_log["success"] else []
                        
                        # Look for TODO/FIXME markers
                        grep_result = self._run_shell(f"grep -r -i 'TODO\\|FIXME' {item_path} 2>/dev/null | head -5")
                        if grep_result["success"] and grep_result["stdout"]:
                            proj_info["todos"] = [line.strip() for line in grep_result["stdout"].split('\n')[:5]]
                        
                        # Count files by type
                        file_count = self._run_shell(f"find {item_path} -type f -name '*.py' | wc -l")
                        proj_info["py_files"] = int(file_count["stdout"]) if file_count["success"] else 0
                        
                        projects[item] = proj_info
        except Exception as e:
            projects["_error"] = str(e)
        
        return projects

    def _generate_markdown_report(self, data: Dict[str, Any]) -> str:
        """Format the collected data into a readable markdown report."""
        report = []
        report.append(f"# System Snapshot Report")
        report.append(f"**Generated:** {datetime.now().isoformat()}")
        report.append(f"**Purpose:** Baseline for contingency planning and system state documentation")
        report.append("")
        
        # 1. Environment
        report.append("## 1. Environment Overview")
        env = data.get("environment", {})
        report.append(f"- **System:** {env.get('system', 'N/A')}")
        report.append(f"- **Python:** {env.get('python_version', 'N/A').split('\n')[0]}")
        report.append(f"- **User:** {env.get('current_user', 'N/A')}")
        report.append(f"- **Current Directory:** {env.get('current_dir', 'N/A')}")
        report.append("")
        
        # 2. Tool Health
        report.append("## 2. Tool Health Check")
        health = data.get("tool_health", {})
        for tool, info in health.items():
            status = "✅" if info.get("success") else "❌"
            report.append(f"- **{tool}:** {status}")
            if not info.get("success"):
                report.append(f"  - Error: {info.get('details', 'Unknown')}")
        report.append("")
        
        # 3. Project Scan
        report.append("## 3. Project Directory Scan")
        projects = data.get("projects", {})
        if projects:
            for name, info in projects.items():
                if name.startswith("_"):
                    continue
                report.append(f"### {name}")
                report.append(f"- Path: `{info.get('path', 'N/A')}`")
                if info.get("recent_commits"):
                    report.append("- Recent commits:")
                    for commit in info.get("recent_commits", [])[:3]:
                        report.append(f"  - {commit}")
                if info.get("todos"):
                    report.append("- TODOs/FIXMEs (sample):")
                    for todo in info.get("todos", [])[:3]:
                        report.append(f"  - `{todo}`")
                report.append(f"- Python files: {info.get('py_files', 0)}")
                report.append("")
        else:
            report.append("No projects identified with standard markers.")
            report.append("")
        
        # 4. Critical Notes & Limitations
        report.append("## 4. Critical Notes for Contingency")
        report.append("""
### What This Snapshot Captures
- **Static State:** Environment configuration, tool availability, project structure.
- **Recent Activity:** Last few git commits (if available), pending TODOs.
- **Health Indicators:** Basic operational status of core tools.

### What This Snapshot Does NOT Capture
- **Dynamic State:** Running processes, memory usage, network connections.
- **Complete Codebase:** Actual source code or data files.
- **External Dependencies:** API keys, remote services, database connections.
- **System Configuration:** Full OS config, cron jobs, service definitions.

### Immediate Contingency Steps Suggested
1. **Archive this report** along with key project directories.
2. **Document external dependencies** (APIs, credentials) separately.
3. **Establish a backup schedule** for the `/home/ubuntu` directory.
4. **Create a 'restoration checklist'** based on the components listed above.
""")
        
        return "\n".join(report)

    async def execute(self, output_path: Optional[str] = None, scan_projects: bool = True) -> str:
        """Execute the system snapshot."""
        try:
            # Collect data
            data = {}
            data["environment"] = self._get_environment_info()
            data["tool_health"] = self._get_tool_health()
            
            if scan_projects:
                data["projects"] = self._scan_project_dir("/home/ubuntu")
            
            # Generate report
            report = self._generate_markdown_report(data)
            
            # Save to file if path provided
            if output_path:
                try:
                    with open(output_path, 'w') as f:
                        f.write(report)
                    result_msg = f"Snapshot saved to {output_path}"
                except Exception as e:
                    result_msg = f"Generated report but failed to save to {output_path}: {str(e)}"
                return result_msg + "\n\n" + report[:1000] + "..." if len(report) > 1000 else report
            else:
                return report
                
        except Exception as e:
            return f"Error generating system snapshot: {str(e)}"