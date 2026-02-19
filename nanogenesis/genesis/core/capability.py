
import shutil
import subprocess
import platform
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class CapabilityScanner:
    """
    World Model Sensor (Prudent Cognition Layer).
    Performs fast, local checks to build a 'Reality Snapshot' before planning.
    """
    
    @staticmethod
    def scan() -> Dict[str, Any]:
        """Run all sensors and return a snapshot"""
        snapshot = {
            "os": CapabilityScanner._check_os(),
            "network": CapabilityScanner._check_network(),
            "permissions": CapabilityScanner._check_permissions(),
            "tools": CapabilityScanner._check_critical_tools(),
            "adb": CapabilityScanner._check_adb_status()
        }
        return snapshot

    @staticmethod
    def _check_os() -> str:
        try:
            return f"{platform.system()} ({platform.release()})"
        except:
            return "Unknown OS"

    @staticmethod
    def _check_network() -> str:
        # Simple ping check
        try:
            # Ping is slow, maybe just check if we can resolve main provider?
            # Or just assume online if not explicit error?
            # Let's try a quick ping to 8.8.8.8 with low timeout
            cmd = ['ping', '-c', '1', '-W', '1', '8.8.8.8']
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return "Online"
        except:
            return "Offline/Unstable"

    @staticmethod
    def _check_permissions() -> str:
        import os
        try:
            return "Root" if os.geteuid() == 0 else "User"
        except:
            return "Unknown"

    @staticmethod
    def _check_critical_tools() -> Dict[str, str]:
        # Generic binaries
        tools = ["git", "python3", "node", "docker", "npm", "gcc", "scrcpy"]
        result = {}
        for t in tools:
            path = shutil.which(t)
            result[t] = "Installed" if path else "Missing"
            
        # Detect Package Manager (Capabilities, not Hardcoded Rules)
        pkg_managers = ["pacman", "apt", "dnf", "yum", "apk", "brew"]
        for pm in pkg_managers:
            if shutil.which(pm):
                result["package_manager"] = pm
                break
        
        return result

    @staticmethod
    def _check_adb_status() -> Dict[str, Any]:
        """Check ADB specifically as it's critical for phone tasks"""
        status = {"installed": False, "devices": []}
        adb_path = shutil.which("adb")
        
        if adb_path:
            status["installed"] = True
            try:
                # Check devices (fast)
                output = subprocess.check_output([adb_path, "devices"], timeout=2).decode().strip()
                lines = output.split('\n')[1:] # Skip header
                devices = [line.split()[0] for line in lines if line.strip() and 'device' in line]
                status["devices"] = devices
            except:
                status["error"] = "ADB unresponsive"
        
        return status
