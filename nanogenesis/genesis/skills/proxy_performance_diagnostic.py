import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import subprocess
import time
import json
import socket
import requests
from typing import Dict, List, Tuple

class ProxyPerformanceDiagnostic(Tool):
    @property
    def name(self) -> str:
        return "proxy_performance_diagnostic"
    
    @property
    def description(self) -> str:
        return "综合诊断代理服务器性能，包括延迟、吞吐量、稳定性等指标"
    
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "proxy_url": {
                    "type": "string", 
                    "description": "代理服务器地址，如 socks5://127.0.0.1:1080",
                    "default": "socks5://127.0.0.1:1080"
                },
                "test_sites": {
                    "type": "array",
                    "description": "要测试的网站列表",
                    "items": {"type": "string"},
                    "default": ["https://www.google.com", "https://github.com", "https://www.youtube.com"]
                },
                "duration": {
                    "type": "integer",
                    "description": "测试持续时间（秒）",
                    "default": 30
                }
            },
            "required": []
        }
    
    async def execute(self, proxy_url: str = "socks5://127.0.0.1:1080", 
                     test_sites: List[str] = None, duration: int = 30) -> str:
        if test_sites is None:
            test_sites = ["https://www.google.com", "https://github.com", "https://www.youtube.com"]
        
        results = {
            "proxy_url": proxy_url,
            "test_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "tests": {}
        }
        
        # 1. 测试代理连通性
        results["tests"]["connectivity"] = self._test_connectivity(proxy_url)
        
        # 2. 测试DNS解析速度
        results["tests"]["dns_performance"] = self._test_dns_performance(proxy_url)
        
        # 3. 测试HTTP性能
        results["tests"]["http_performance"] = self._test_http_performance(proxy_url, test_sites)
        
        # 4. 测试稳定性（持续测试）
        results["tests"]["stability"] = self._test_stability(proxy_url, test_sites[0], duration)
        
        # 5. 测试代理服务器状态
        results["tests"]["proxy_server_status"] = self._check_proxy_server_status()
        
        # 生成诊断报告
        report = self._generate_report(results)
        return report
    
    def _test_connectivity(self, proxy_url: str) -> Dict:
        """测试代理连通性"""
        try:
            # 解析代理地址
            if proxy_url.startswith("socks5://"):
                host_port = proxy_url.replace("socks5://", "")
                host, port = host_port.split(":")
                
                # 测试TCP连接
                start = time.time()
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((host, int(port)))
                latency = (time.time() - start) * 1000  # 毫秒
                sock.close()
                
                return {
                    "status": "connected",
                    "latency_ms": round(latency, 2),
                    "host": host,
                    "port": port
                }
            else:
                return {"status": "error", "message": f"不支持的代理协议: {proxy_url}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _test_dns_performance(self, proxy_url: str) -> Dict:
        """测试DNS解析性能"""
        test_domains = ["google.com", "github.com", "youtube.com"]
        results = []
        
        for domain in test_domains:
            try:
                # 使用系统DNS解析
                start = time.time()
                socket.gethostbyname(domain)
                direct_time = (time.time() - start) * 1000
                
                # 通过代理解析（模拟）
                proxy_time = direct_time * 1.5  # 假设代理增加50%延迟
                
                results.append({
                    "domain": domain,
                    "direct_dns_ms": round(direct_time, 2),
                    "estimated_proxy_dns_ms": round(proxy_time, 2),
                    "overhead": round(proxy_time - direct_time, 2)
                })
            except Exception as e:
                results.append({
                    "domain": domain,
                    "error": str(e)
                })
        
        return {"dns_tests": results}
    
    def _test_http_performance(self, proxy_url: str, test_sites: List[str]) -> Dict:
        """测试HTTP性能"""
        results = []
        
        for site in test_sites[:2]:  # 只测试前两个，避免耗时过长
            try:
                # 测试连接时间
                start = time.time()
                response = requests.get(site, 
                                      proxies={"http": proxy_url, "https": proxy_url},
                                      timeout=10,
                                      verify=False)
                total_time = (time.time() - start) * 1000
                
                results.append({
                    "site": site,
                    "status_code": response.status_code,
                    "total_time_ms": round(total_time, 2),
                    "content_length": len(response.content),
                    "throughput_kbps": round(len(response.content) / total_time * 8, 2) if total_time > 0 else 0
                })
            except Exception as e:
                results.append({
                    "site": site,
                    "error": str(e)
                })
        
        return {"http_tests": results}
    
    def _test_stability(self, proxy_url: str, test_site: str, duration: int) -> Dict:
        """测试稳定性（持续请求）"""
        successes = 0
        failures = 0
        latencies = []
        
        end_time = time.time() + min(duration, 10)  # 最多测试10秒
        
        while time.time() < end_time and (successes + failures) < 10:
            try:
                start = time.time()
                response = requests.get(test_site,
                                      proxies={"http": proxy_url, "https": proxy_url},
                                      timeout=5,
                                      verify=False)
                latency = (time.time() - start) * 1000
                
                if response.status_code == 200:
                    successes += 1
                    latencies.append(latency)
                else:
                    failures += 1
            except Exception:
                failures += 1
            
            time.sleep(0.5)  # 间隔0.5秒
        
        if latencies:
            avg_latency = sum(latencies) / len(latencies)
            max_latency = max(latencies)
            min_latency = min(latencies)
        else:
            avg_latency = max_latency = min_latency = 0
        
        return {
            "success_rate": f"{successes/(successes+failures)*100:.1f}%" if (successes+failures) > 0 else "0%",
            "total_requests": successes + failures,
            "successes": successes,
            "failures": failures,
            "avg_latency_ms": round(avg_latency, 2),
            "min_latency_ms": round(min_latency, 2) if latencies else 0,
            "max_latency_ms": round(max_latency, 2) if latencies else 0,
            "jitter_ms": round(max_latency - min_latency, 2) if latencies else 0
        }
    
    def _check_proxy_server_status(self) -> Dict:
        """检查代理服务器状态"""
        try:
            # 检查v2raya进程
            result = subprocess.run(["ps", "aux", "|", "grep", "v2raya"], 
                                  shell=True, capture_output=True, text=True)
            
            v2raya_processes = [line for line in result.stdout.split('\n') if 'grep' not in line and line.strip()]
            
            # 检查内存和CPU使用
            if v2raya_processes:
                process_info = v2raya_processes[0].split()
                return {
                    "status": "running",
                    "process_count": len(v2raya_processes),
                    "memory_mb": round(int(process_info[5]) / 1024, 1) if len(process_info) > 5 else 0,
                    "cpu_percent": process_info[2] if len(process_info) > 2 else "unknown"
                }
            else:
                return {"status": "not_running"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
    def _generate_report(self, results: Dict) -> str:
        """生成诊断报告"""
        report = []
        report.append("=" * 60)
        report.append("代理性能诊断报告")
        report.append("=" * 60)
        report.append(f"代理地址: {results['proxy_url']}")
        report.append(f"测试时间: {results['test_time']}")
        report.append("")
        
        # 连通性测试
        conn = results['tests']['connectivity']
        report.append("1. 连通性测试:")
        if conn['status'] == 'connected':
            report.append(f"   ✅ 连接成功 - 延迟: {conn['latency_ms']}ms")
        else:
            report.append(f"   ❌ 连接失败: {conn.get('message', '未知错误')}")
        
        # DNS性能
        report.append("\n2. DNS解析性能:")
        for dns_test in results['tests']['dns_performance']['dns_tests']:
            if 'error' not in dns_test:
                report.append(f"   {dns_test['domain']}:")
                report.append(f"     直连: {dns_test['direct_dns_ms']}ms")
                report.append(f"     代理预估: {dns_test['estimated_proxy_dns_ms']}ms")
                report.append(f"     开销: +{dns_test['overhead']}ms")
        
        # HTTP性能
        report.append("\n3. HTTP性能测试:")
        for http_test in results['tests']['http_performance']['http_tests']:
            if 'error' not in http_test:
                report.append(f"   {http_test['site']}:")
                report.append(f"     状态码: {http_test['status_code']}")
                report.append(f"     总时间: {http_test['total_time_ms']}ms")
                report.append(f"     吞吐量: {http_test['throughput_kbps']}kbps")
            else:
                report.append(f"   {http_test['site']}: ❌ {http_test['error']}")
        
        # 稳定性测试
        stability = results['tests']['stability']
        report.append("\n4. 稳定性测试:")
        report.append(f"   成功率: {stability['success_rate']}")
        report.append(f"   请求数: {stability['total_requests']} (成功: {stability['successes']}, 失败: {stability['failures']})")
        report.append(f"   平均延迟: {stability['avg_latency_ms']}ms")
        report.append(f"   延迟波动: {stability['min_latency_ms']}ms ~ {stability['max_latency_ms']}ms")
        report.append(f"   抖动: {stability['jitter_ms']}ms")
        
        # 代理服务器状态
        server = results['tests']['proxy_server_status']
        report.append("\n5. 代理服务器状态:")
        if server['status'] == 'running':
            report.append(f"   ✅ v2raya 运行中")
            report.append(f"   进程数: {server['process_count']}")
            report.append(f"   内存占用: {server.get('memory_mb', '未知')}MB")
            report.append(f"   CPU使用: {server.get('cpu_percent', '未知')}%")
        else:
            report.append(f"   ❌ v2raya 未运行")
        
        report.append("\n" + "=" * 60)
        report.append("诊断建议:")
        
        # 基于结果给出建议
        if stability['success_rate'] != "100.0%":
            report.append("⚠️  稳定性不足 - 建议检查代理服务器配置")
        
        if stability['jitter_ms'] > 100:
            report.append("⚠️  延迟抖动过大 - 可能是网络不稳定或代理服务器负载高")
        
        if 'throughput_kbps' in results['tests']['http_performance']['http_tests'][0]:
            throughput = results['tests']['http_performance']['http_tests'][0]['throughput_kbps']
            if throughput < 100:  # 小于100kbps
                report.append("⚠️  吞吐量过低 - 可能是带宽限制或代理服务器性能瓶颈")
        
        report.append("✅  建议优化: 调整v2raya配置、更换代理节点、优化路由规则")
        
        return "\n".join(report)