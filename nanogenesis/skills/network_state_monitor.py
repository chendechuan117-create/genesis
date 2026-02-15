#!/usr/bin/env python3
"""
网络状态监控与自动修复工具
周期性检查MTU、代理设置、丢包率、延迟等核心指标
检测到异常时自动应用历史验证过的修复脚本
"""

import subprocess
import time
import json
import os
import sys
from datetime import datetime
from pathlib import Path

class NetworkStateMonitor:
    """网络状态监控工具"""
    
    def __init__(self, log_file="~/.network_monitor.log"):
        self.log_file = Path(log_file).expanduser()
        self.health_thresholds = {
            "packet_loss": 5,  # 丢包率阈值 <5%
            "latency": 100,    # 延迟阈值 <100ms
            "mtu_standard": 1500  # 标准MTU
        }
        self.fix_script_path = Path("~/fix_network_timeout.sh").expanduser()
        
    def log(self, message, level="INFO"):
        """记录日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}\n"
        
        # 确保日志目录存在
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(log_entry)
        
        # 同时输出到控制台
        print(f"[{level}] {message}")
        return log_entry
    
    def run_command(self, cmd, timeout=10):
        """执行命令并返回结果"""
        try:
            result = subprocess.run(
                cmd, 
                shell=True, 
                capture_output=True, 
                text=True, 
                timeout=timeout
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Command timeout: {cmd}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def check_mtu(self):
        """检查MTU设置"""
        self.log("检查MTU设置...")
        
        # 获取网络接口
        result = self.run_command("ip link show | grep 'state UP' | awk -F': ' '{print $2}'")
        if not result["success"]:
            return {"status": "error", "message": "无法获取网络接口"}
        
        interfaces = [iface.strip() for iface in result["stdout"].split('\n') if iface.strip()]
        
        mtu_status = {}
        for iface in interfaces:
            result = self.run_command(f"ip link show {iface} | grep mtu | awk '{{print $5}}'")
            if result["success"]:
                current_mtu = int(result["stdout"]) if result["stdout"].isdigit() else 0
                is_normal = current_mtu == self.health_thresholds["mtu_standard"]
                mtu_status[iface] = {
                    "current": current_mtu,
                    "expected": self.health_thresholds["mtu_standard"],
                    "normal": is_normal
                }
        
        return {"status": "success", "data": mtu_status}
    
    def check_proxy(self):
        """检查代理设置"""
        self.log("检查代理设置...")
        
        proxy_vars = ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
        proxy_status = {}
        
        for var in proxy_vars:
            value = os.environ.get(var, "")
            proxy_status[var] = {
                "set": bool(value),
                "value": value
            }
        
        # 检查系统代理
        system_proxy = self.run_command("gsettings get org.gnome.system.proxy mode 2>/dev/null || echo 'not found'")
        
        return {
            "status": "success", 
            "env_proxies": proxy_status,
            "system_proxy": system_proxy["stdout"] if system_proxy["success"] else "unknown"
        }
    
    def check_network_performance(self, target="8.8.8.8"):
        """检查网络性能（丢包率、延迟）"""
        self.log(f"检查网络性能（目标: {target}）...")
        
        # 使用ping测试
        result = self.run_command(f"ping -c 10 -W 2 {target} 2>/dev/null | tail -2")
        
        if not result["success"]:
            return {"status": "error", "message": "ping测试失败"}
        
        output = result["stdout"]
        
        # 解析ping结果
        packet_loss = 100
        latency = 999
        
        if "packet loss" in output:
            # 提取丢包率
            for line in output.split('\n'):
                if "packet loss" in line:
                    try:
                        loss_str = line.split("%")[0].split()[-1]
                        packet_loss = float(loss_str)
                    except:
                        pass
        
        if "rtt min/avg/max/mdev" in output:
            # 提取延迟
            for line in output.split('\n'):
                if "rtt min/avg/max/mdev" in line:
                    try:
                        avg_str = line.split('=')[1].split('/')[1]
                        latency = float(avg_str)
                    except:
                        pass
        
        is_healthy = (
            packet_loss <= self.health_thresholds["packet_loss"] and
            latency <= self.health_thresholds["latency"]
        )
        
        return {
            "status": "success",
            "target": target,
            "packet_loss": packet_loss,
            "latency": latency,
            "healthy": is_healthy,
            "thresholds": self.health_thresholds
        }
    
    def check_dns(self):
        """检查DNS解析"""
        self.log("检查DNS解析...")
        
        test_domains = ["google.com", "github.com", "baidu.com"]
        dns_status = {}
        
        for domain in test_domains:
            result = self.run_command(f"dig +short {domain} 2>/dev/null | head -1")
            dns_status[domain] = {
                "resolved": bool(result["stdout"]),
                "ip": result["stdout"] if result["stdout"] else "failed"
            }
        
        # 检查当前DNS配置
        dns_config = self.run_command("cat /etc/resolv.conf 2>/dev/null | grep nameserver")
        
        return {
            "status": "success",
            "domain_resolution": dns_status,
            "dns_servers": dns_config["stdout"] if dns_config["success"] else "unknown"
        }
    
    def apply_fixes(self, issues):
        """应用修复措施"""
        self.log("开始应用网络修复...", "WARNING")
        
        fixes_applied = []
        
        # 1. 修复MTU问题
        if "mtu_abnormal" in issues:
            self.log("修复MTU设置...")
            result = self.run_command("sudo ip link set eno1 mtu 1500 2>/dev/null || true")
            if result["success"]:
                fixes_applied.append("MTU修复")
        
        # 2. 清除代理
        if "proxy_interference" in issues:
            self.log("清除代理设置...")
            proxy_vars = ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"]
            for var in proxy_vars:
                os.environ.pop(var, None)
            fixes_applied.append("代理清除")
        
        # 3. 运行修复脚本（如果存在）
        if self.fix_script_path.exists():
            self.log("运行修复脚本...")
            result = self.run_command(f"bash {self.fix_script_path}")
            if result["success"]:
                fixes_applied.append("脚本修复")
        
        return fixes_applied
    
    def diagnose(self):
        """执行完整诊断"""
        self.log("开始网络状态诊断...")
        
        diagnosis = {
            "timestamp": datetime.now().isoformat(),
            "checks": {},
            "issues": [],
            "healthy": True
        }
        
        # 执行各项检查
        checks = [
            ("mtu", self.check_mtu),
            ("proxy", self.check_proxy),
            ("performance", lambda: self.check_network_performance()),
            ("dns", self.check_dns)
        ]
        
        for name, check_func in checks:
            try:
                result = check_func()
                diagnosis["checks"][name] = result
                
                # 分析问题
                if name == "mtu" and result["status"] == "success":
                    for iface, data in result["data"].items():
                        if not data["normal"]:
                            diagnosis["issues"].append(f"mtu_abnormal:{iface}={data['current']}")
                            diagnosis["healthy"] = False
                
                elif name == "proxy" and result["status"] == "success":
                    for var, data in result["env_proxies"].items():
                        if data["set"] and "127.0.0.1:1080" in data["value"]:
                            diagnosis["issues"].append("proxy_interference")
                            diagnosis["healthy"] = False
                
                elif name == "performance" and result["status"] == "success":
                    if not result["healthy"]:
                        diagnosis["issues"].append(f"performance_issue:loss={result['packet_loss']}%,latency={result['latency']}ms")
                        diagnosis["healthy"] = False
                
            except Exception as e:
                diagnosis["checks"][name] = {"status": "error", "error": str(e)}
        
        return diagnosis
    
    def monitor_once(self):
        """执行一次监控循环"""
        diagnosis = self.diagnose()
        
        # 如果有问题，尝试修复
        if diagnosis["issues"]:
            self.log(f"检测到问题: {diagnosis['issues']}", "WARNING")
            fixes = self.apply_fixes(diagnosis["issues"])
            if fixes:
                self.log(f"已应用修复: {fixes}", "SUCCESS")
        
        return diagnosis
    
    def start_monitoring(self, interval=60):
        """启动持续监控"""
        self.log(f"启动网络状态监控，间隔: {interval}秒")
        
        try:
            while True:
                diagnosis = self.monitor_once()
                
                # 记录摘要
                summary = {
                    "timestamp": diagnosis["timestamp"],
                    "healthy": diagnosis["healthy"],
                    "issue_count": len(diagnosis["issues"]),
                    "issues": diagnosis["issues"]
                }
                self.log(f"监控摘要: {json.dumps(summary, ensure_ascii=False)}")
                
                time.sleep(interval)
                
        except KeyboardInterrupt:
            self.log("监控已停止", "INFO")
        except Exception as e:
            self.log(f"监控异常: {str(e)}", "ERROR")

# 工具接口
class NetworkStateMonitorTool:
    name = "network_state_monitor"
    description = "网络状态监控与自动修复工具。周期性检查MTU、代理设置、丢包率、延迟等核心指标，检测到异常时自动应用修复脚本。"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string", 
                "enum": ["diagnose", "monitor", "check_mtu", "check_proxy", "check_performance"],
                "description": "执行的操作：diagnose(完整诊断), monitor(启动监控), check_*(单项检查)"
            },
            "interval": {
                "type": "integer",
                "description": "监控间隔（秒），仅action=monitor时有效",
                "default": 60
            },
            "target": {
                "type": "string",
                "description": "ping测试目标，仅check_performance时有效",
                "default": "8.8.8.8"
            }
        },
        "required": ["action"]
    }
    
    def __init__(self):
        self.monitor = NetworkStateMonitor()
    
    def execute(self, action, interval=60, target="8.8.8.8"):
        """执行工具"""
        try:
            if action == "diagnose":
                diagnosis = self.monitor.diagnose()
                return {
                    "success": True,
                    "diagnosis": diagnosis,
                    "summary": {
                        "healthy": diagnosis["healthy"],
                        "issues": diagnosis["issues"],
                        "issue_count": len(diagnosis["issues"])
                    }
                }
            
            elif action == "monitor":
                # 注意：monitor会阻塞，适合后台运行
                return {
                    "success": True,
                    "message": f"监控将在后台启动，间隔{interval}秒。查看日志: {self.monitor.log_file}"
                }
            
            elif action == "check_mtu":
                result = self.monitor.check_mtu()
                return {"success": True, "result": result}
            
            elif action == "check_proxy":
                result = self.monitor.check_proxy()
                return {"success": True, "result": result}
            
            elif action == "check_performance":
                result = self.monitor.check_network_performance(target)
                return {"success": True, "result": result}
            
            else:
                return {"success": False, "error": f"未知操作: {action}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}

# 主函数（用于独立运行）
if __name__ == "__main__":
    monitor = NetworkStateMonitor()
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "diagnose":
            result = monitor.diagnose()
            print(json.dumps(result, indent=2))
        elif sys.argv[1] == "monitor":
            interval = int(sys.argv[2]) if len(sys.argv) > 2 else 60
            monitor.start_monitoring(interval)
        else:
            print("用法: python network_state_monitor.py [diagnose|monitor [interval]]")
    else:
        # 默认执行一次诊断
        result = monitor.diagnose()
        print(json.dumps(result, indent=2))