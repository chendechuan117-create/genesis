import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

#!/usr/bin/env python3
"""
Antigravity Native 调试工具
用于诊断和修复 antigravity-native 启动问题
"""

import os
import sys
import subprocess
import json
import re
from pathlib import Path

class AntigravityNativeDebugger:
    def __init__(self):
        self.home = Path.home()
        self.bin_path = self.home / "bin" / "antigravity-native"
        self.proxy_host = "127.0.0.1"
        self.http_port = 20171
        self.socks_port = 1080
        
    def check_script(self):
        """检查启动脚本"""
        if not self.bin_path.exists():
            return {"status": "error", "message": f"启动脚本不存在: {self.bin_path}"}
        
        try:
            content = self.bin_path.read_text()
            return {
                "status": "ok",
                "path": str(self.bin_path),
                "size": len(content),
                "proxy_config": {
                    "http_proxy": f"http://{self.proxy_host}:{self.http_port}",
                    "https_proxy": f"http://{self.proxy_host}:{self.http_port}",
                    "all_proxy": f"socks5://{self.proxy_host}:{self.socks_port}"
                }
            }
        except Exception as e:
            return {"status": "error", "message": f"读取脚本失败: {e}"}
    
    def check_proxy_service(self):
        """检查代理服务状态"""
        results = {}
        
        # 检查HTTP代理
        try:
            cmd = f"curl -s --connect-timeout 5 --proxy http://{self.proxy_host}:{self.http_port} http://www.google.com"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            results["http_proxy"] = {
                "status": "reachable" if result.returncode == 0 else "unreachable",
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            results["http_proxy"] = {"status": "timeout"}
        except Exception as e:
            results["http_proxy"] = {"status": "error", "message": str(e)}
        
        # 检查SOCKS5代理
        try:
            cmd = f"curl -s --connect-timeout 5 --socks5 {self.proxy_host}:{self.socks_port} http://www.google.com"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            results["socks5_proxy"] = {
                "status": "reachable" if result.returncode == 0 else "unreachable",
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            results["socks5_proxy"] = {"status": "timeout"}
        except Exception as e:
            results["socks5_proxy"] = {"status": "error", "message": str(e)}
        
        return results
    
    def check_network_config(self):
        """检查网络配置"""
        results = {}
        
        # 检查MTU
        try:
            cmd = "ip link show eno1 | grep mtu"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            mtu_match = re.search(r'mtu (\d+)', result.stdout)
            if mtu_match:
                mtu = int(mtu_match.group(1))
                results["mtu"] = {
                    "value": mtu,
                    "status": "normal" if mtu == 1500 else "abnormal",
                    "recommended": 1500
                }
        except Exception as e:
            results["mtu"] = {"status": "error", "message": str(e)}
        
        # 检查环境变量
        proxy_vars = ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"]
        env_proxies = {}
        for var in proxy_vars:
            value = os.environ.get(var)
            if value:
                env_proxies[var] = value
        
        results["environment_variables"] = env_proxies
        
        # 检查DNS
        try:
            with open("/etc/resolv.conf", "r") as f:
                dns_content = f.read()
            results["dns"] = {
                "file": "/etc/resolv.conf",
                "content": dns_content
            }
        except Exception as e:
            results["dns"] = {"status": "error", "message": str(e)}
        
        return results
    
    def test_direct_connection(self):
        """测试直连网络"""
        results = {}
        
        test_targets = [
            ("8.8.8.8", "Google DNS"),
            ("1.1.1.1", "Cloudflare DNS"),
            ("www.google.com", "Google"),
            ("www.baidu.com", "Baidu")
        ]
        
        for target, name in test_targets:
            try:
                cmd = f"ping -c 2 -W 2 {target}"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
                
                if result.returncode == 0:
                    # 提取ping统计
                    lines = result.stdout.strip().split('\n')
                    stats = lines[-2] if len(lines) >= 2 else ""
                    results[target] = {
                        "status": "reachable",
                        "name": name,
                        "stats": stats
                    }
                else:
                    results[target] = {
                        "status": "unreachable",
                        "name": name,
                        "error": result.stderr[:100] if result.stderr else "Unknown error"
                    }
            except subprocess.TimeoutExpired:
                results[target] = {"status": "timeout", "name": name}
            except Exception as e:
                results[target] = {"status": "error", "name": name, "message": str(e)}
        
        return results
    
    def diagnose(self):
        """综合诊断"""
        diagnosis = {
            "script_check": self.check_script(),
            "proxy_service": self.check_proxy_service(),
            "network_config": self.check_network_config(),
            "direct_connection": self.test_direct_connection()
        }
        
        # 分析问题
        issues = []
        
        # 检查MTU问题
        mtu_info = diagnosis["network_config"].get("mtu", {})
        if mtu_info.get("value") != 1500:
            issues.append(f"MTU设置异常: {mtu_info.get('value')} (应为1500)")
        
        # 检查代理服务
        proxy_status = diagnosis["proxy_service"]
        if proxy_status.get("http_proxy", {}).get("status") != "reachable":
            issues.append("HTTP代理服务不可用")
        if proxy_status.get("socks5_proxy", {}).get("status") != "reachable":
            issues.append("SOCKS5代理服务不可用")
        
        # 检查直连
        direct = diagnosis["direct_connection"]
        unreachable = [k for k, v in direct.items() if v.get("status") != "reachable"]
        if unreachable:
            issues.append(f"直连测试失败: {', '.join(unreachable)}")
        
        diagnosis["issues"] = issues
        diagnosis["summary"] = {
            "total_issues": len(issues),
            "needs_fix": len(issues) > 0
        }
        
        return diagnosis
    
    def create_fix_script(self, output_path=None):
        """创建修复脚本"""
        if output_path is None:
            output_path = self.home / "fix_antigravity.sh"
        
        script_content = f'''#!/bin/bash
echo "=== 修复 Antigravity Native 启动问题 ==="

# 1. 修复MTU设置
echo "1. 修复MTU设置 (1280 -> 1500)..."
sudo ip link set eno1 mtu 1500
echo "当前MTU: $(ip link show eno1 | grep -o 'mtu [0-9]*' | cut -d' ' -f2)"

# 2. 清除可能干扰的代理环境变量
echo "2. 清除干扰的代理设置..."
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY

# 3. 创建干净的启动脚本
echo "3. 创建干净的启动脚本..."
cat > ~/bin/antigravity-native-clean << 'EOF'
#!/usr/bin/bash
# Antigravity Native Clean Launcher
# 无代理版本

# Electron settings
export ELECTRON_IS_DEV=0
export ELECTRON_FORCE_IS_PACKAGED=true

# Launch antigravity
echo "Starting Antigravity (Clean Mode)..."
exec electron37 --app=/usr/lib/antigravity/ "$@"
EOF
chmod +x ~/bin/antigravity-native-clean

# 4. 测试网络连接
echo "4. 测试网络连接..."
ping -c 2 8.8.8.8 && echo "网络连接正常" || echo "网络连接有问题"

echo "=== 修复完成 ==="
echo "尝试启动: ~/bin/antigravity-native-clean &"
echo "或使用原脚本: ~/bin/antigravity-native &"
'''
        
        try:
            Path(output_path).write_text(script_content)
            os.chmod(output_path, 0o755)
            return {"status": "ok", "path": str(output_path)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

# Tool 类定义
class Tool:
    name = "antigravity_native_debugger"
    description = "诊断和修复 antigravity-native 启动问题的工具"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["diagnose", "check_script", "check_proxy", "check_network", "test_connection", "create_fix"],
                "description": "要执行的操作"
            },
            "output_path": {
                "type": "string",
                "description": "修复脚本输出路径（仅create_fix需要）"
            }
        },
        "required": ["action"]
    }
    
    def __init__(self):
        self.debugger = AntigravityNativeDebugger()
    
    def execute(self, action, output_path=None):
        try:
            if action == "diagnose":
                result = self.debugger.diagnose()
                return json.dumps(result, indent=2, ensure_ascii=False)
            
            elif action == "check_script":
                result = self.debugger.check_script()
                return json.dumps(result, indent=2, ensure_ascii=False)
            
            elif action == "check_proxy":
                result = self.debugger.check_proxy_service()
                return json.dumps(result, indent=2, ensure_ascii=False)
            
            elif action == "check_network":
                result = self.debugger.check_network_config()
                return json.dumps(result, indent=2, ensure_ascii=False)
            
            elif action == "test_connection":
                result = self.debugger.test_direct_connection()
                return json.dumps(result, indent=2, ensure_ascii=False)
            
            elif action == "create_fix":
                result = self.debugger.create_fix_script(output_path)
                return json.dumps(result, indent=2, ensure_ascii=False)
            
            else:
                return json.dumps({"status": "error", "message": f"未知操作: {action}"})
                
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})