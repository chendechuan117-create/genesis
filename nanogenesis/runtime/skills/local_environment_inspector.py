from core.base import Tool
import subprocess
import platform
import os
import json

class LocalEnvironmentInspector(Tool):
    name = "local_environment_inspector"
    description = "探测本地系统环境信息，包括操作系统、硬件、网络配置等"
    parameters = {
        "type": "object",
        "properties": {
            "detail_level": {
                "type": "string", 
                "enum": ["basic", "full"],
                "description": "信息详细程度：basic（基本信息）或 full（完整信息）",
                "default": "basic"
            }
        }
    }
    
    def execute(self, detail_level="basic"):
        """执行系统环境探测"""
        result = {
            "system": {},
            "hardware": {},
            "network": {},
            "environment": {},
            "disk": {}
        }
        
        try:
            # 操作系统信息
            result["system"]["platform"] = platform.platform()
            result["system"]["system"] = platform.system()
            result["system"]["release"] = platform.release()
            result["system"]["version"] = platform.version()
            result["system"]["machine"] = platform.machine()
            result["system"]["processor"] = platform.processor()
            
            # 环境变量
            env_vars = {}
            for key in ["HOME", "USER", "SHELL", "PATH", "PWD", "LANG", "TERM"]:
                if key in os.environ:
                    env_vars[key] = os.environ[key]
            result["environment"]["variables"] = env_vars
            
            # 当前工作目录
            result["environment"]["cwd"] = os.getcwd()
            
            # 用户信息
            result["environment"]["user"] = os.environ.get("USER", "unknown")
            
            if detail_level == "full":
                try:
                    # 网络接口信息
                    if platform.system() == "Windows":
                        ipconfig = subprocess.run(["ipconfig", "/all"], capture_output=True, text=True, timeout=5)
                        result["network"]["interfaces"] = ipconfig.stdout[:1000] if ipconfig.returncode == 0 else "Failed to get network info"
                    else:
                        ifconfig = subprocess.run(["ifconfig", "-a"], capture_output=True, text=True, timeout=5)
                        if ifconfig.returncode != 0:
                            ifconfig = subprocess.run(["ip", "addr"], capture_output=True, text=True, timeout=5)
                        result["network"]["interfaces"] = ifconfig.stdout[:1000] if ifconfig.returncode == 0 else "Failed to get network info"
                    
                    # 磁盘使用情况
                    if platform.system() == "Windows":
                        df = subprocess.run(["wmic", "logicaldisk", "get", "size,freespace,caption"], capture_output=True, text=True, timeout=5)
                        result["disk"]["usage"] = df.stdout[:500] if df.returncode == 0 else "Failed to get disk info"
                    else:
                        df = subprocess.run(["df", "-h"], capture_output=True, text=True, timeout=5)
                        result["disk"]["usage"] = df.stdout[:500] if df.returncode == 0 else "Failed to get disk info"
                    
                    # CPU信息
                    if platform.system() == "Linux":
                        cpuinfo = subprocess.run(["lscpu"], capture_output=True, text=True, timeout=5)
                        if cpuinfo.returncode == 0:
                            result["hardware"]["cpu"] = cpuinfo.stdout[:500]
                        
                        # 内存信息
                        meminfo = subprocess.run(["free", "-h"], capture_output=True, text=True, timeout=5)
                        if meminfo.returncode == 0:
                            result["hardware"]["memory"] = meminfo.stdout[:300]
                    
                except Exception as e:
                    result["network"]["error"] = str(e)
            
            return json.dumps(result, indent=2, ensure_ascii=False)
            
        except Exception as e:
            return f"环境探测失败: {str(e)}"