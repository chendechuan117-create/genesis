import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class DnsOptimizer(Tool):
    @property
    def name(self) -> str:
        return "dns_optimizer"
        
    @property
    def description(self) -> str:
        return "一键优化DNS配置，提升网络速度。支持临时修改和永久修改两种模式。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string", 
                    "enum": ["temporary", "permanent"],
                    "description": "优化模式：temporary(临时生效，重启恢复) 或 permanent(永久修改)"
                },
                "primary_dns": {
                    "type": "string",
                    "description": "主DNS服务器，默认使用阿里DNS 223.5.5.5",
                    "default": "223.5.5.5"
                },
                "secondary_dns": {
                    "type": "string", 
                    "description": "备用DNS服务器，默认使用腾讯DNS 119.29.29.29",
                    "default": "119.29.29.29"
                }
            },
            "required": ["mode"]
        }
        
    async def execute(self, mode: str, primary_dns: str = "223.5.5.5", secondary_dns: str = "119.29.29.29") -> str:
        import subprocess
        import os
        
        result_lines = []
        
        # 记录当前DNS配置
        current_dns = subprocess.run(["cat", "/etc/resolv.conf"], capture_output=True, text=True).stdout
        result_lines.append("📊 当前DNS配置：")
        result_lines.append(current_dns)
        
        if mode == "temporary":
            # 临时修改 /etc/resolv.conf
            dns_config = f"""# 临时优化配置 - 重启后恢复
nameserver {primary_dns}
nameserver {secondary_dns}
nameserver 114.114.114.114
"""
            try:
                subprocess.run(["sudo", "tee", "/etc/resolv.conf"], input=dns_config, text=True, check=True)
                result_lines.append(f"✅ 临时DNS优化完成！")
                result_lines.append(f"主DNS: {primary_dns}")
                result_lines.append(f"备DNS: {secondary_dns}")
                result_lines.append("⚠️ 注意：重启系统后会恢复原配置")
            except Exception as e:
                result_lines.append(f"❌ 临时优化失败：{str(e)}")
                
        elif mode == "permanent":
            # 永久修改 NetworkManager 配置
            try:
                # 获取当前活动连接
                conn_result = subprocess.run(
                    ["nmcli", "-t", "-f", "NAME", "connection", "show", "--active"], 
                    capture_output=True, text=True
                )
                connections = conn_result.stdout.strip().split('\n')
                if not connections:
                    return "❌ 未找到活动的网络连接"
                    
                conn_name = connections[0]
                result_lines.append(f"📡 检测到活动连接：{conn_name}")
                
                # 修改DNS配置
                subprocess.run([
                    "sudo", "nmcli", "connection", "modify", conn_name,
                    f"ipv4.dns", f"{primary_dns} {secondary_dns}",
                    "ipv4.ignore-auto-dns", "yes"
                ], check=True)
                
                # 重启连接
                subprocess.run(["sudo", "nmcli", "connection", "down", conn_name], check=True)
                subprocess.run(["sudo", "nmcli", "connection", "up", conn_name], check=True)
                
                result_lines.append(f"✅ 永久DNS优化完成！")
                result_lines.append(f"主DNS: {primary_dns}")
                result_lines.append(f"备DNS: {secondary_dns}")
                result_lines.append("🔧 配置已保存到NetworkManager，重启后依然有效")
                
            except Exception as e:
                result_lines.append(f"❌ 永久优化失败：{str(e)}")
                result_lines.append("💡 建议尝试临时模式或手动修改")
        
        # 测试优化效果
        result_lines.append("\n🔍 优化效果测试：")
        
        # 测试阿里DNS
        dig_result = subprocess.run(
            ["dig", f"@{primary_dns}", "github.com", "+short"], 
            capture_output=True, text=True
        )
        if dig_result.returncode == 0:
            result_lines.append(f"✅ {primary_dns} 解析正常")
        else:
            result_lines.append(f"⚠️ {primary_dns} 解析测试失败")
            
        # 测试当前DNS速度
        speed_test = subprocess.run(
            ["timeout", "2", "dig", "github.com", "|", "grep", "'Query time:'"],
            shell=True, capture_output=True, text=True
        )
        if "Query time:" in speed_test.stdout:
            result_lines.append(f"📈 当前解析速度：{speed_test.stdout.strip()}")
        
        return "\n".join(result_lines)