import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

#!/usr/bin/env python3
"""
网络配置回滚工具
用于管理和回滚网络配置变更
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

class NetworkConfigRollback:
    def __init__(self, backup_dir=None):
        self.home = Path.home()
        if backup_dir:
            self.backup_dir = Path(backup_dir)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.backup_dir = self.home / f"network_backup_{timestamp}"
        
        # 确保备份目录存在
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # 重要配置文件路径
        self.config_files = {
            "resolv.conf": "/etc/resolv.conf",
            "NetworkManager": "/etc/NetworkManager/NetworkManager.conf",
            "systemd_network": "/etc/systemd/network/",
            "sysctl": "/etc/sysctl.conf",
            "sysctl.d": "/etc/sysctl.d/"
        }
        
        # Shell配置文件
        self.shell_configs = [
            "~/.bashrc",
            "~/.bash_profile",
            "~/.zshrc",
            "~/.profile",
            "~/.config/fish/config.fish"
        ]
    
    def backup_current_config(self):
        """备份当前网络配置"""
        backup_info = {
            "timestamp": datetime.now().isoformat(),
            "backup_dir": str(self.backup_dir),
            "files": {}
        }
        
        # 备份系统配置文件
        for name, path in self.config_files.items():
            src_path = Path(path)
            if src_path.exists():
                if src_path.is_dir():
                    # 备份目录
                    backup_path = self.backup_dir / name
                    if backup_path.exists():
                        shutil.rmtree(backup_path)
                    shutil.copytree(src_path, backup_path)
                    backup_info["files"][name] = {
                        "type": "directory",
                        "backup_path": str(backup_path)
                    }
                else:
                    # 备份文件
                    backup_path = self.backup_dir / f"{name}.backup"
                    shutil.copy2(src_path, backup_path)
                    backup_info["files"][name] = {
                        "type": "file",
                        "backup_path": str(backup_path)
                    }
        
        # 备份shell配置文件
        shell_backups = []
        for config in self.shell_configs:
            config_path = Path(config.replace("~", str(self.home)))
            if config_path.exists():
                backup_path = self.backup_dir / f"shell_{config_path.name}.backup"
                shutil.copy2(config_path, backup_path)
                shell_backups.append(str(config_path))
        
        # 备份当前网络状态
        network_status = {}
        commands = [
            ("ip_addr", "ip addr show"),
            ("ip_route", "ip route show"),
            ("ip_link", "ip link show"),
            ("env_proxy", "env | grep -i proxy"),
            ("firewall", "sudo iptables -L -n 2>/dev/null || echo 'No iptables'")
        ]
        
        for name, cmd in commands:
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
                output_file = self.backup_dir / f"{name}.txt"
                output_file.write_text(result.stdout)
                network_status[name] = {
                    "command": cmd,
                    "output_file": str(output_file),
                    "returncode": result.returncode
                }
            except Exception as e:
                network_status[name] = {"error": str(e)}
        
        backup_info["network_status"] = network_status
        backup_info["shell_configs"] = shell_backups
        
        # 保存备份元数据
        meta_file = self.backup_dir / "backup_metadata.json"
        meta_file.write_text(json.dumps(backup_info, indent=2))
        
        return backup_info
    
    def create_rollback_script(self):
        """创建回滚脚本"""
        script_content = f'''#!/bin/bash
# 网络配置回滚脚本
# 备份目录: {self.backup_dir}

echo "=== 网络配置回滚 ==="
echo "备份目录: {self.backup_dir}"
echo ""

# 检查备份文件是否存在
if [ ! -d "{self.backup_dir}" ]; then
    echo "错误: 备份目录不存在!"
    exit 1
fi

# 1. 恢复系统配置文件
echo "1. 恢复系统配置文件..."
for file in {self.backup_dir}/*.backup; do
    if [ -f "$file" ]; then
        filename=$(basename "$file" .backup)
        case "$filename" in
            resolv.conf)
                echo "  恢复 /etc/resolv.conf"
                sudo cp "$file" /etc/resolv.conf
                ;;
            sysctl)
                echo "  恢复 /etc/sysctl.conf"
                sudo cp "$file" /etc/sysctl.conf
                ;;
            NetworkManager)
                echo "  恢复 /etc/NetworkManager/NetworkManager.conf"
                sudo cp "$file" /etc/NetworkManager/NetworkManager.conf
                ;;
        esac
    fi
done

# 2. 恢复网络接口设置
echo "2. 恢复网络接口设置..."
if [ -f "{self.backup_dir}/ip_link.txt" ]; then
    # 提取MTU值并恢复
    OLD_MTU=$(grep -o "mtu [0-9]*" {self.backup_dir}/ip_link.txt | head -1 | cut -d' ' -f2)
    if [ ! -z "$OLD_MTU" ]; then
        echo "  恢复MTU为: $OLD_MTU"
        sudo ip link set eno1 mtu $OLD_MTU 2>/dev/null || true
    fi
fi

# 3. 清除代理环境变量
echo "3. 清除代理环境变量..."
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY

# 4. 恢复shell配置文件
echo "4. 恢复shell配置文件..."
for config in ~/.bashrc ~/.bash_profile ~/.zshrc ~/.profile; do
    if [ -f "$config" ]; then
        config_name=$(basename "$config")
        backup_file="{self.backup_dir}/shell_$config_name.backup"
        if [ -f "$backup_file" ]; then
            echo "  恢复 $config"
            cp "$backup_file" "$config"
        fi
    fi
done

# 5. 应用sysctl设置
echo "5. 应用sysctl设置..."
if [ -f /etc/sysctl.conf ]; then
    sudo sysctl -p 2>/dev/null || true
fi

echo ""
echo "=== 回滚完成 ==="
echo "建议操作:"
echo "1. 重启网络服务: sudo systemctl restart NetworkManager"
echo "2. 或重启系统使所有更改生效"
echo "3. 测试网络连接: ping -c 4 8.8.8.8"
'''
        
        script_path = self.backup_dir / "rollback.sh"
        script_path.write_text(script_content)
        script_path.chmod(0o755)
        
        return str(script_path)
    
    def analyze_current_issues(self):
        """分析当前网络问题"""
        issues = []
        
        # 检查MTU
        try:
            result = subprocess.run("ip link show eno1 | grep mtu", shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                import re
                mtu_match = re.search(r'mtu (\d+)', result.stdout)
                if mtu_match:
                    mtu = int(mtu_match.group(1))
                    if mtu != 1500:
                        issues.append({
                            "type": "mtu",
                            "severity": "medium",
                            "description": f"MTU设置异常: {mtu} (标准应为1500)",
                            "fix": "sudo ip link set eno1 mtu 1500"
                        })
        except Exception as e:
            issues.append({"type": "mtu_check_error", "description": str(e)})
        
        # 检查代理设置
        proxy_vars = ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"]
        proxy_issues = []
        for var in proxy_vars:
            value = os.environ.get(var)
            if value:
                proxy_issues.append(f"{var}={value}")
        
        if proxy_issues:
            issues.append({
                "type": "proxy",
                "severity": "low",
                "description": "存在代理环境变量",
                "variables": proxy_issues,
                "fix": "unset " + " ".join(proxy_vars)
            })
        
        # 检查DNS
        try:
            with open("/etc/resolv.conf", "r") as f:
                content = f.read()
            if "8.8.8.8" not in content and "1.1.1.1" not in content:
                issues.append({
                    "type": "dns",
                    "severity": "low",
                    "description": "DNS配置可能不是最优",
                    "fix": "添加 nameserver 8.8.8.8 到 /etc/resolv.conf"
                })
        except Exception as e:
            issues.append({"type": "dns_check_error", "description": str(e)})
        
        # 检查网络连接
        try:
            result = subprocess.run("ping -c 2 -W 2 8.8.8.8", shell=True, capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                issues.append({
                    "type": "connectivity",
                    "severity": "high",
                    "description": "无法连接到互联网",
                    "fix": "检查网络连接和防火墙设置"
                })
        except Exception as e:
            issues.append({"type": "connectivity_check_error", "description": str(e)})
        
        return issues
    
    def create_fix_script(self, issues=None):
        """创建修复脚本"""
        if issues is None:
            issues = self.analyze_current_issues()
        
        script_content = '''#!/bin/bash
echo "=== 网络问题修复脚本 ==="
echo ""

'''
        
        for issue in issues:
            if "fix" in issue:
                script_content += f'echo "修复: {issue.get("description", "Unknown")}"\n'
                script_content += f'{issue["fix"]}\n'
                script_content += 'echo ""\n'
        
        script_content += '''echo "=== 修复完成 ==="
echo "测试网络连接..."
ping -c 2 8.8.8.8 && echo "网络连接正常" || echo "网络连接可能仍有问题"
echo ""
echo "建议重启网络服务: sudo systemctl restart NetworkManager"
'''
        
        script_path = self.backup_dir / "fix_network.sh"
        script_path.write_text(script_content)
        script_path.chmod(0o755)
        
        return str(script_path)

# Tool 类定义
class Tool:
    name = "network_config_rollback"
    description = "网络配置备份和回滚工具"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["backup", "create_rollback", "analyze", "create_fix", "list_backups"],
                "description": "要执行的操作"
            },
            "backup_dir": {
                "type": "string",
                "description": "备份目录路径（可选）"
            }
        },
        "required": ["action"]
    }
    
    def __init__(self):
        self.rollback = None
    
    def execute(self, action, backup_dir=None):
        try:
            if backup_dir:
                self.rollback = NetworkConfigRollback(backup_dir)
            else:
                self.rollback = NetworkConfigRollback()
            
            if action == "backup":
                result = self.rollback.backup_current_config()
                return json.dumps(result, indent=2, ensure_ascii=False)
            
            elif action == "create_rollback":
                script_path = self.rollback.create_rollback_script()
                return json.dumps({
                    "status": "ok",
                    "rollback_script": script_path,
                    "message": f"回滚脚本已创建: {script_path}"
                }, indent=2, ensure_ascii=False)
            
            elif action == "analyze":
                issues = self.rollback.analyze_current_issues()
                return json.dumps({
                    "issues": issues,
                    "count": len(issues),
                    "has_problems": len(issues) > 0
                }, indent=2, ensure_ascii=False)
            
            elif action == "create_fix":
                issues = self.rollback.analyze_current_issues()
                script_path = self.rollback.create_fix_script(issues)
                return json.dumps({
                    "issues": issues,
                    "fix_script": script_path,
                    "message": f"修复脚本已创建: {script_path}"
                }, indent=2, ensure_ascii=False)
            
            elif action == "list_backups":
                backup_dirs = []
                home = Path.home()
                for item in home.glob("network_backup_*"):
                    if item.is_dir():
                        backup_dirs.append({
                            "path": str(item),
                            "name": item.name,
                            "created": item.stat().st_ctime
                        })
                
                backup_dirs.sort(key=lambda x: x["created"], reverse=True)
                return json.dumps({
                    "backups": backup_dirs,
                    "count": len(backup_dirs)
                }, indent=2, ensure_ascii=False)
            
            else:
                return json.dumps({"status": "error", "message": f"未知操作: {action}"})
                
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})