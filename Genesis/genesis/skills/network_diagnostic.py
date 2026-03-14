import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import subprocess
import json
import time
import socket

class NetworkDiagnosticTool:
    @property
    def name(self) -> str:
        return "network_diagnostic"
    
    @property
    def description(self) -> str:
        return "全面网络诊断工具，测试连通性、延迟、DNS、路由等"
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "测试目标，如 'google.com' 或 'all' 进行全面测试", "default": "all"}
            },
            "required": []
        }
    
    async def execute(self, target: str = "all") -> str:
        results = []
        
        if target == "all" or target == "connectivity":
            results.append(self._test_connectivity())
        
        if target == "all" or target == "dns":
            results.append(self._test_dns())
        
        if target == "all" or target == "latency":
            results.append(self._test_latency())
        
        if target == "all" or target == "route":
            results.append(self._test_routing())
        
        if target == "all" or target == "bandwidth":
            results.append(self._test_bandwidth())
        
        return "\n\n".join(results)
    
    def _test_connectivity(self) -> str:
        result = ["=== 网络连通性测试 ==="]
        sites = [
            ("本地网关", "192.168.1.1"),
            ("百度", "baidu.com"),
            ("Google", "google.com"),
            ("GitHub", "github.com"),
            ("Cloudflare DNS", "1.1.1.1"),
            ("Google DNS", "8.8.8.8")
        ]
        
        for name, addr in sites:
            try:
                if addr.replace('.', '').isdigit():
                    # IP地址
                    output = subprocess.run(
                        ["ping", "-c", "3", "-W", "2", addr],
                        capture_output=True, text=True, timeout=5
                    )
                else:
                    # 域名
                    output = subprocess.run(
                        ["ping", "-c", "3", "-W", "2", addr],
                        capture_output=True, text=True, timeout=5
                    )
                
                if output.returncode == 0:
                    # 提取平均延迟
                    lines = output.stdout.split('\n')
                    for line in lines:
                        if "rtt min/avg/max/mdev" in line:
                            parts = line.split('=')
                            if len(parts) > 1:
                                latency = parts[1].split('/')[1].strip()
                                result.append(f"✓ {name} ({addr}): 连通正常，平均延迟 {latency}ms")
                            break
                    else:
                        result.append(f"✓ {name} ({addr}): 连通正常")
                else:
                    result.append(f"✗ {name} ({addr}): 无法连接")
            except Exception as e:
                result.append(f"✗ {name} ({addr}): 测试失败 - {str(e)}")
        
        return "\n".join(result)
    
    def _test_dns(self) -> str:
        result = ["=== DNS解析测试 ==="]
        domains = ["baidu.com", "google.com", "github.com", "openai.com"]
        dns_servers = [
            ("本地DNS", "218.85.152.99"),
            ("Google DNS", "8.8.8.8"),
            ("Cloudflare DNS", "1.1.1.1")
        ]
        
        for domain in domains:
            result.append(f"\n域名: {domain}")
            for dns_name, dns_server in dns_servers:
                try:
                    start = time.time()
                    output = subprocess.run(
                        ["dig", f"@{dns_server}", domain, "+short"],
                        capture_output=True, text=True, timeout=3
                    )
                    elapsed = (time.time() - start) * 1000
                    
                    if output.returncode == 0 and output.stdout.strip():
                        ips = output.stdout.strip().split('\n')
                        result.append(f"  {dns_name}: {ips[0]} ({elapsed:.1f}ms)")
                    else:
                        result.append(f"  {dns_name}: 解析失败")
                except Exception as e:
                    result.append(f"  {dns_name}: 错误 - {str(e)}")
        
        return "\n".join(result)
    
    def _test_latency(self) -> str:
        result = ["=== 网络延迟测试 ==="]
        targets = [
            ("本地网络", "192.168.1.1"),
            ("国内网站", "baidu.com"),
            ("国际DNS", "8.8.8.8"),
            ("国际网站", "1.1.1.1")
        ]
        
        for name, target in targets:
            try:
                output = subprocess.run(
                    ["ping", "-c", "5", "-i", "0.2", "-W", "1", target],
                    capture_output=True, text=True, timeout=10
                )
                
                if output.returncode == 0:
                    lines = output.stdout.split('\n')
                    for line in lines:
                        if "rtt min/avg/max/mdev" in line:
                            parts = line.split('=')
                            if len(parts) > 1:
                                latencies = parts[1].strip().split('/')
                                result.append(f"{name} ({target}):")
                                result.append(f"  最小: {latencies[0]}ms, 平均: {latencies[1]}ms, 最大: {latencies[2]}ms")
                            break
                else:
                    result.append(f"{name} ({target}): 测试失败")
            except Exception as e:
                result.append(f"{name} ({target}): 错误 - {str(e)}")
        
        return "\n".join(result)
    
    def _test_routing(self) -> str:
        result = ["=== 路由追踪测试 ==="]
        targets = ["baidu.com", "8.8.8.8"]
        
        for target in targets:
            result.append(f"\n目标: {target}")
            try:
                output = subprocess.run(
                    ["traceroute", "-n", "-m", "8", "-w", "1", target],
                    capture_output=True, text=True, timeout=15
                )
                
                if output.returncode == 0:
                    lines = output.stdout.split('\n')
                    for i, line in enumerate(lines[:10]):  # 只显示前10跳
                        if line.strip():
                            result.append(f"  跳{i+1}: {line.strip()}")
                else:
                    result.append("  路由追踪失败")
            except Exception as e:
                result.append(f"  错误: {str(e)}")
        
        return "\n".join(result)
    
    def _test_bandwidth(self) -> str:
        result = ["=== 带宽测试 ==="]
        
        # 测试下载速度
        try:
            start = time.time()
            output = subprocess.run(
                ["curl", "-o", "/dev/null", "-s", "-w", "%{speed_download}", 
                 "https://speed.cloudflare.com/__down?bytes=5000000"],
                capture_output=True, text=True, timeout=10
            )
            elapsed = time.time() - start
            
            if output.returncode == 0 and output.stdout.strip():
                speed_bytes = float(output.stdout.strip())
                speed_mbps = (speed_bytes * 8) / 1_000_000
                result.append(f"下载速度: {speed_mbps:.2f} Mbps ({speed_bytes/1_000_000:.2f} MB/s)")
                result.append(f"测试时间: {elapsed:.2f}秒")
            else:
                result.append("下载速度测试失败")
        except Exception as e:
            result.append(f"下载测试错误: {str(e)}")
        
        return "\n".join(result)