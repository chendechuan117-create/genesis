import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

import subprocess
import os
import json
import time

class SteamChecker:
    name = "steam_checker"
    description = "检查Steam状态和修复结果"
    parameters = {
        "type": "object",
        "properties": {
            "check_type": {
                "type": "string", 
                "enum": ["all", "network", "process", "logs", "proxy"],
                "description": "检查类型"
            }
        },
        "required": ["check_type"]
    }

    def execute(self, params):
        check_type = params.get("check_type", "all")
        
        if check_type == "all":
            return self.check_all()
        elif check_type == "network":
            return self.check_network()
        elif check_type == "process":
            return self.check_process()
        elif check_type == "logs":
            return self.check_logs()
        elif check_type == "proxy":
            return self.check_proxy()
        else:
            return {"error": "未知检查类型"}

    def check_all(self):
        """执行所有检查"""
        result = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "network": self.check_network(),
            "process": self.check_process(),
            "proxy": self.check_proxy(),
            "installation": self.check_installation()
        }
        
        # 生成总结
        issues = []
        if result["network"]["steam_connectable"] == False:
            issues.append("Steam服务器连接失败")
        if result["process"]["running"] == False:
            issues.append("Steam进程未运行")
        if result["proxy"]["has_proxy"] == True:
            issues.append("检测到代理设置")
        
        result["summary"] = {
            "issues_found": len(issues),
            "issues": issues,
            "status": "正常" if len(issues) == 0 else "需要关注"
        }
        
        return result

    def check_network(self):
        """检查网络连接"""
        try:
            # 测试Steam主要域名
            domains = ["store.steampowered.com", "steamcommunity.com"]
            results = []
            
            for domain in domains:
                # ping测试
                ping = subprocess.run(
                    ["ping", "-c", "2", "-W", "2", domain],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                # HTTP测试
                http = subprocess.run(
                    ["curl", "-I", "-s", "-L", f"https://{domain}", "--max-time", "5"],
                    capture_output=True,
                    text=True,
                    timeout=6
                )
                
                results.append({
                    "domain": domain,
                    "ping_ok": ping.returncode == 0,
                    "http_ok": http.returncode == 0
                })
            
            steam_connectable = all(r["ping_ok"] and r["http_ok"] for r in results)
            
            return {
                "steam_connectable": steam_connectable,
                "details": results,
                "message": "Steam服务器可连接" if steam_connectable else "Steam服务器连接有问题"
            }
            
        except Exception as e:
            return {
                "steam_connectable": False,
                "error": str(e),
                "message": "网络检查失败"
            }

    def check_process(self):
        """检查Steam进程"""
        try:
            # 查找Steam进程
            ps = subprocess.run(
                "ps aux | grep -i steam | grep -v grep",
                shell=True,
                capture_output=True,
                text=True
            )
            
            processes = []
            for line in ps.stdout.strip().split('\n'):
                if line:
                    processes.append(line)
            
            return {
                "running": len(processes) > 0,
                "process_count": len(processes),
                "processes": processes,
                "message": f"找到 {len(processes)} 个Steam进程" if processes else "未找到运行的Steam进程"
            }
            
        except Exception as e:
            return {
                "running": False,
                "error": str(e),
                "message": "进程检查失败"
            }

    def check_proxy(self):
        """检查代理设置"""
        proxy_vars = ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy"]
        proxy_values = {}
        
        for var in proxy_vars:
            value = os.environ.get(var, "")
            proxy_values[var] = value
        
        has_proxy = any(proxy_values.values())
        
        return {
            "has_proxy": has_proxy,
            "proxy_values": proxy_values,
            "message": "检测到代理设置" if has_proxy else "未检测到代理设置"
        }

    def check_installation(self):
        """检查Steam安装"""
        try:
            # 检查steam命令
            which = subprocess.run(["which", "steam"], capture_output=True, text=True)
            steam_path = which.stdout.strip() if which.returncode == 0 else None
            
            # 检查Steam目录
            steam_dir = os.path.expanduser("~/.steam")
            dir_exists = os.path.exists(steam_dir)
            
            return {
                "installed": steam_path is not None,
                "steam_path": steam_path,
                "steam_dir_exists": dir_exists,
                "message": f"Steam已安装 ({steam_path})" if steam_path else "Steam可能未安装"
            }
            
        except Exception as e:
            return {
                "installed": False,
                "error": str(e),
                "message": "安装检查失败"
            }

    def check_logs(self):
        """检查Steam日志"""
        log_paths = [
            os.path.expanduser("~/.steam/error.log"),
            os.path.expanduser("~/.steam/steam.log")
        ]
        
        logs_found = []
        for path in log_paths:
            if os.path.exists(path):
                try:
                    with open(path, 'r', errors='ignore') as f:
                        content = f.read()
                        logs_found.append({
                            "path": path,
                            "size": os.path.getsize(path),
                            "last_lines": content[-1000:] if content else "空文件"
                        })
                except Exception as e:
                    logs_found.append({
                        "path": path,
                        "error": str(e)
                    })
        
        return {
            "logs_found": len(logs_found),
            "logs": logs_found,
            "message": f"找到 {len(logs_found)} 个日志文件" if logs_found else "未找到Steam日志文件"
        }