import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

#!/usr/bin/env python3
"""
Steam修复验证工具
用于检查Steam修复后的状态并提供详细诊断报告
"""

import subprocess
import os
import json
import time
from pathlib import Path

class SteamRepairVerifier:
    name = "steam_repair_verifier"
    description = "验证Steam修复结果，提供全面的诊断报告"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string", 
                "enum": ["diagnose", "test_connection", "check_process", "read_logs"],
                "description": "执行的操作：diagnose(完整诊断), test_connection(测试连接), check_process(检查进程), read_logs(读取日志)"
            }
        },
        "required": ["action"]
    }

    def execute(self, params):
        action = params.get("action", "diagnose")
        
        if action == "diagnose":
            return self.full_diagnosis()
        elif action == "test_connection":
            return self.test_steam_connection()
        elif action == "check_process":
            return self.check_steam_process()
        elif action == "read_logs":
            return self.read_steam_logs()
        else:
            return {"status": "error", "message": f"未知操作: {action}"}

    def full_diagnosis(self):
        """执行完整的Steam诊断"""
        results = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "running",
            "checks": {},
            "summary": {},
            "recommendations": []
        }
        
        # 1. 测试网络连接
        connection_result = self.test_steam_connection()
        results["checks"]["network_connection"] = connection_result
        
        # 2. 检查Steam进程
        process_result = self.check_steam_process()
        results["checks"]["process_status"] = process_result
        
        # 3. 读取Steam日志
        log_result = self.read_steam_logs()
        results["checks"]["logs"] = log_result
        
        # 4. 检查Steam安装
        install_result = self.check_steam_installation()
        results["checks"]["installation"] = install_result
        
        # 5. 检查代理设置
        proxy_result = self.check_proxy_settings()
        results["checks"]["proxy_settings"] = proxy_result
        
        # 生成总结
        results["summary"] = self.generate_summary(results["checks"])
        
        return results

    def test_steam_connection(self):
        """测试Steam服务器连接"""
        test_points = [
            ("store.steampowered.com", "Steam商店"),
            ("steamcommunity.com", "Steam社区"),
            ("api.steampowered.com", "Steam API")
        ]
        
        results = []
        for domain, description in test_points:
            try:
                # 使用ping测试
                ping_result = subprocess.run(
                    ["ping", "-c", "2", "-W", "2", domain],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                # 使用curl测试HTTP连接
                curl_result = subprocess.run(
                    ["curl", "-I", "-s", "-L", f"https://{domain}", "--max-time", "5"],
                    capture_output=True,
                    text=True,
                    timeout=6
                )
                
                ping_success = ping_result.returncode == 0
                http_success = curl_result.returncode == 0
                
                results.append({
                    "domain": domain,
                    "description": description,
                    "ping": "成功" if ping_success else "失败",
                    "http": "成功" if http_success else "失败",
                    "ping_output": ping_result.stdout[:200] if ping_success else ping_result.stderr,
                    "http_status": curl_result.stdout.split('\n')[0] if http_success else "连接失败"
                })
                
            except subprocess.TimeoutExpired:
                results.append({
                    "domain": domain,
                    "description": description,
                    "ping": "超时",
                    "http": "超时",
                    "ping_output": "测试超时",
                    "http_status": "测试超时"
                })
            except Exception as e:
                results.append({
                    "domain": domain,
                    "description": description,
                    "ping": "错误",
                    "http": "错误",
                    "ping_output": str(e),
                    "http_status": str(e)
                })
        
        return {
            "status": "complete",
            "test_points": results,
            "success_count": sum(1 for r in results if r["ping"] == "成功" and r["http"] == "成功"),
            "total_count": len(results)
        }

    def check_steam_process(self):
        """检查Steam相关进程"""
        try:
            # 查找Steam进程
            ps_result = subprocess.run(
                ["ps", "aux", "|", "grep", "-i", "steam"],
                shell=True,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            processes = []
            for line in ps_result.stdout.split('\n'):
                if line and "grep" not in line:
                    parts = line.split()
                    if len(parts) >= 11:
                        processes.append({
                            "user": parts[0],
                            "pid": parts[1],
                            "cpu": parts[2],
                            "mem": parts[3],
                            "command": " ".join(parts[10:])
                        })
            
            return {
                "status": "complete",
                "process_count": len(processes),
                "processes": processes,
                "raw_output": ps_result.stdout[:500]
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "process_count": 0,
                "processes": []
            }

    def read_steam_logs(self):
        """读取Steam日志文件"""
        log_paths = [
            Path.home() / ".steam" / "error.log",
            Path.home() / ".steam" / "steam.log",
            Path.home() / ".local" / "share" / "Steam" / "logs",
            Path.home() / ".steam" / "logs"
        ]
        
        logs_found = []
        for log_path in log_paths:
            if log_path.exists():
                try:
                    if log_path.is_dir():
                        # 如果是目录，列出其中的日志文件
                        log_files = list(log_path.glob("*.log"))
                        for log_file in log_files[:3]:  # 只读取前3个
                            try:
                                content = log_file.read_text(errors='ignore')
                                logs_found.append({
                                    "path": str(log_file),
                                    "size": log_file.stat().st_size,
                                    "last_lines": content[-2000:] if content else "空文件"
                                })
                            except:
                                pass
                    else:
                        # 如果是文件，直接读取
                        content = log_path.read_text(errors='ignore')
                        logs_found.append({
                            "path": str(log_path),
                            "size": log_path.stat().st_size,
                            "last_lines": content[-2000:] if content else "空文件"
                        })
                except Exception as e:
                    logs_found.append({
                        "path": str(log_path),
                        "error": str(e)
                    })
        
        return {
            "status": "complete",
            "log_files_found": len(logs_found),
            "logs": logs_found
        }

    def check_steam_installation(self):
        """检查Steam安装状态"""
        checks = []
        
        # 检查steam命令
        steam_cmd = subprocess.run(["which", "steam"], capture_output=True, text=True)
        checks.append({
            "check": "steam命令位置",
            "result": steam_cmd.stdout.strip() if steam_cmd.returncode == 0 else "未找到",
            "status": "success" if steam_cmd.returncode == 0 else "failed"
        })
        
        # 检查Steam目录
        steam_dirs = [
            Path.home() / ".steam",
            Path.home() / ".local" / "share" / "Steam",
            Path("/usr/share/steam")
        ]
        
        for steam_dir in steam_dirs:
            exists = steam_dir.exists()
            checks.append({
                "check": f"目录存在: {steam_dir}",
                "result": "存在" if exists else "不存在",
                "status": "success" if exists else "info"
            })
        
        return {
            "status": "complete",
            "checks": checks
        }

    def check_proxy_settings(self):
        """检查代理设置"""
        proxy_vars = ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy"]
        results = {}
        
        for var in proxy_vars:
            value = os.environ.get(var, "")
            results[var] = {
                "value": value,
                "status": "set" if value else "not_set"
            }
        
        return {
            "status": "complete",
            "proxy_variables": results,
            "has_proxy": any(results[var]["status"] == "set" for var in proxy_vars)
        }

    def generate_summary(self, checks):
        """生成诊断总结"""
        summary = {
            "overall_status": "unknown",
            "issues_found": [],
            "suggestions": []
        }
        
        # 分析网络连接
        network = checks.get("network_connection", {})
        if network.get("success_count", 0) < network.get("total_count", 3):
            summary["issues_found"].append("部分Steam服务器连接失败")
            summary["suggestions"].append("检查网络设置和防火墙规则")
        
        # 分析代理设置
        proxy = checks.get("proxy_settings", {})
        if proxy.get("has_proxy", False):
            summary["issues_found"].append("检测到代理设置，可能影响Steam连接")
            summary["suggestions"].append("临时清除代理变量或配置Steam使用代理")
        
        # 分析进程状态
        process = checks.get("process_status", {})
        if process.get("process_count", 0) == 0:
            summary["issues_found"].append("未发现运行的Steam进程")
            summary["suggestions"].append("尝试启动Steam客户端")
        
        # 分析日志错误
        logs = checks.get("logs", {})
        if logs.get("log_files_found", 0) > 0:
            for log in logs.get("logs", []):
                if "error" in log.get("last_lines", "").lower():
                    summary["issues_found"].append("日志中发现错误信息")
                    summary["suggestions"].append("查看详细日志以了解具体错误")
                    break
        
        # 确定整体状态
        if len(summary["issues_found"]) == 0:
            summary["overall_status"] = "healthy"
            summary["suggestions"].append("Steam状态正常，可以尝试启动")
        elif len(summary["issues_found"]) <= 2:
            summary["overall_status"] = "warning"
        else:
            summary["overall_status"] = "problem"
        
        return summary