import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.base import Tool

#!/usr/bin/env python3
"""
网络优化建议生成器
基于系统诊断数据，提供针对性的网络优化建议
"""

class NetworkOptimizer:
    def __init__(self):
        self.name = "network_optimizer"
        self.description = "分析网络诊断数据，生成针对性的优化建议"
        self.parameters = {
            "type": "object",
            "properties": {
                "diagnostic_data": {
                    "type": "string", 
                    "description": "网络诊断数据文本"
                }
            },
            "required": ["diagnostic_data"]
        }
    
    def execute(self, diagnostic_data: str):
        """分析诊断数据并生成优化建议"""
        import re
        
        # 解析关键指标
        metrics = self._parse_diagnostics(diagnostic_data)
        
        # 生成优化建议
        recommendations = self._generate_recommendations(metrics)
        
        return {
            "summary": self._generate_summary(metrics),
            "recommendations": recommendations,
            "priority_order": self._prioritize_recommendations(recommendations),
            "executable_commands": self._generate_commands(recommendations)
        }
    
    def _parse_diagnostics(self, data: str):
        """解析诊断数据"""
        metrics = {
            "mtu": 1500,
            "rx_drops": 0,
            "tcp_connections": 0,
            "proxy_configured": False,
            "dns_servers": [],
            "tcp_parameters": {},
            "latency_ms": 0,
            "packet_loss_percent": 0,
            "failed_services": []
        }
        
        # 解析MTU
        mtu_match = re.search(r'eno1\s+(\d+)', data)
        if mtu_match:
            metrics["mtu"] = int(mtu_match.group(1))
        
        # 解析接收丢包
        eno1_stats = re.search(r'eno1\s+\d+\s+(\d+)\s+(\d+)\s+(\d+)', data)
        if eno1_stats:
            metrics["rx_drops"] = int(eno1_stats.group(3))
        
        # 解析TCP连接数
        tcp_match = re.search(r'TCP:\s+(\d+)', data)
        if tcp_match:
            metrics["tcp_connections"] = int(tcp_match.group(1))
        
        # 检查代理配置
        metrics["proxy_configured"] = "http_proxy=socks5://127.0.0.1:1080" in data
        
        # 解析DNS服务器
        dns_matches = re.findall(r'nameserver\s+([\d\.:a-fA-F]+)', data)
        metrics["dns_servers"] = dns_matches
        
        # 解析TCP参数
        tcp_params = re.findall(r'(net\.(?:core|ipv4\.tcp)_\w+)\s*=\s*([\d\.]+)', data)
        metrics["tcp_parameters"] = dict(tcp_params)
        
        # 解析延迟和丢包
        ping_match = re.search(r'时间=(\d+)', data)
        if ping_match:
            metrics["latency_ms"] = int(ping_match.group(1))
        
        loss_match = re.search(r'(\d+\.?\d*)% packet loss', data)
        if loss_match:
            metrics["packet_loss_percent"] = float(loss_match.group(1))
        
        # 解析失败服务
        if "shadow.service" in data:
            metrics["failed_services"].append("shadow.service")
        if "systemd-vconsole-setup.service" in data:
            metrics["failed_services"].append("systemd-vconsole-setup.service")
        
        return metrics
    
    def _generate_recommendations(self, metrics):
        """基于指标生成优化建议"""
        recommendations = []
        
        # 1. MTU优化
        if metrics["mtu"] < 1500:
            recommendations.append({
                "id": "mtu_optimization",
                "title": "优化MTU设置",
                "description": f"当前MTU为{metrics['mtu']}，低于标准1500，可能导致性能下降",
                "priority": "high",
                "risk": "low",
                "impact": "medium"
            })
        
        # 2. 代理配置清理
        if metrics["proxy_configured"]:
            recommendations.append({
                "id": "proxy_cleanup",
                "title": "清理代理配置",
                "description": "检测到SOCKS5代理配置，可能导致部分应用网络异常",
                "priority": "high",
                "risk": "low",
                "impact": "high"
            })
        
        # 3. DNS优化
        if len(metrics["dns_servers"]) > 3:
            recommendations.append({
                "id": "dns_optimization",
                "title": "优化DNS配置",
                "description": f"检测到{len(metrics['dns_servers'])}个DNS服务器，libc可能只支持前3个",
                "priority": "medium",
                "risk": "low",
                "impact": "medium"
            })
        
        # 4. TCP缓冲区优化
        current_rmem_max = int(metrics["tcp_parameters"].get("net.core.rmem_max", 0))
        if current_rmem_max < 16777216:  # 16MB
            recommendations.append({
                "id": "tcp_buffer_optimization",
                "title": "优化TCP缓冲区",
                "description": f"当前TCP接收缓冲区最大值为{current_rmem_max}字节，可提升到16MB以上",
                "priority": "medium",
                "risk": "low",
                "impact": "medium"
            })
        
        # 5. 修复失败服务
        if metrics["failed_services"]:
            recommendations.append({
                "id": "service_repair",
                "title": "修复失败的系统服务",
                "description": f"检测到失败的服务: {', '.join(metrics['failed_services'])}",
                "priority": "high",
                "risk": "low",
                "impact": "low"
            })
        
        # 6. 网络延迟优化
        if metrics["latency_ms"] > 100:
            recommendations.append({
                "id": "latency_optimization",
                "title": "优化网络延迟",
                "description": f"当前延迟{metrics['latency_ms']}ms较高，可调整TCP参数",
                "priority": "medium",
                "risk": "low",
                "impact": "high"
            })
        
        return recommendations
    
    def _generate_summary(self, metrics):
        """生成问题摘要"""
        issues = []
        
        if metrics["mtu"] < 1500:
            issues.append(f"MTU偏低 ({metrics['mtu']})")
        
        if metrics["proxy_configured"]:
            issues.append("代理配置冲突")
        
        if metrics["rx_drops"] > 1000:
            issues.append(f"网络丢包 ({metrics['rx_drops']} packets)")
        
        if metrics["latency_ms"] > 100:
            issues.append(f"延迟较高 ({metrics['latency_ms']}ms)")
        
        if metrics["failed_services"]:
            issues.append(f"{len(metrics['failed_services'])}个服务失败")
        
        if issues:
            return f"检测到{len(issues)}个主要问题: {', '.join(issues)}"
        else:
            return "网络配置基本正常，可进行性能优化"
    
    def _prioritize_recommendations(self, recommendations):
        """按优先级排序建议"""
        priority_map = {"high": 3, "medium": 2, "low": 1}
        
        sorted_recs = sorted(
            recommendations,
            key=lambda x: (priority_map[x["priority"]], -priority_map[x["risk"]], priority_map[x["impact"]]),
            reverse=True
        )
        
        return [rec["id"] for rec in sorted_recs]
    
    def _generate_commands(self, recommendations):
        """生成可执行的优化命令"""
        commands = {}
        
        for rec in recommendations:
            if rec["id"] == "mtu_optimization":
                commands[rec["id"]] = [
                    "# 临时设置MTU为1500",
                    "sudo ip link set eno1 mtu 1500",
                    "# 永久设置（编辑NetworkManager配置）",
                    "sudo nmcli connection modify 'Wired connection 1' 802-3-ethernet.mtu 1500"
                ]
            
            elif rec["id"] == "proxy_cleanup":
                commands[rec["id"]] = [
                    "# 临时清理代理环境变量",
                    "unset http_proxy https_proxy ftp_proxy all_proxy HTTP_PROXY HTTPS_PROXY FTP_PROXY ALL_PROXY",
                    "# 永久清理（编辑shell配置文件）",
                    "sed -i '/proxy=/d' ~/.bashrc ~/.zshrc ~/.profile 2>/dev/null || true"
                ]
            
            elif rec["id"] == "dns_optimization":
                commands[rec["id"]] = [
                    "# 优化DNS配置（保留前3个）",
                    "sudo nmcli connection modify 'Wired connection 1' ipv4.dns '218.85.152.99 218.85.157.99 192.168.1.1'",
                    "sudo systemctl restart NetworkManager"
                ]
            
            elif rec["id"] == "tcp_buffer_optimization":
                commands[rec["id"]] = [
                    "# 临时优化TCP缓冲区",
                    "sudo sysctl -w net.core.rmem_max=16777216",
                    "sudo sysctl -w net.core.wmem_max=16777216",
                    "sudo sysctl -w net.ipv4.tcp_rmem='4096 87380 16777216'",
                    "sudo sysctl -w net.ipv4.tcp_wmem='4096 65536 16777216'",
                    "# 永久设置",
                    "echo 'net.core.rmem_max = 16777216' | sudo tee -a /etc/sysctl.d/99-network-optimization.conf",
                    "echo 'net.core.wmem_max = 16777216' | sudo tee -a /etc/sysctl.d/99-network-optimization.conf"
                ]
            
            elif rec["id"] == "service_repair":
                commands[rec["id"]] = [
                    "# 修复失败的服务",
                    "sudo systemctl reset-failed shadow.service systemd-vconsole-setup.service",
                    "sudo systemctl daemon-reload"
                ]
            
            elif rec["id"] == "latency_optimization":
                commands[rec["id"]] = [
                    "# 优化TCP延迟参数",
                    "sudo sysctl -w net.ipv4.tcp_slow_start_after_idle=0",
                    "sudo sysctl -w net.ipv4.tcp_no_metrics_save=1",
                    "sudo sysctl -w net.ipv4.tcp_low_latency=1",
                    "# 启用TCP快速打开",
                    "sudo sysctl -w net.ipv4.tcp_fastopen=3"
                ]
        
        return commands