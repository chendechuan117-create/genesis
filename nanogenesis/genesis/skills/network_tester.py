import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class NetworkTester(Tool):
    @property
    def name(self) -> str:
        return "network_tester"
        
    @property
    def description(self) -> str:
        return "测试网络连接和DNS解析，验证系统能否访问外部网络"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "targets": {
                    "type": "string", 
                    "description": "要测试的目标网站，用逗号分隔，默认测试常用网站",
                    "default": "google.com,baidu.com,github.com,openai.com"
                }
            },
            "required": []
        }
        
    async def execute(self, targets: str = "google.com,baidu.com,github.com,openai.com") -> str:
        import subprocess
        import socket
        import time
        
        results = []
        target_list = [t.strip() for t in targets.split(",")]
        
        for target in target_list:
            try:
                # 测试DNS解析
                start_time = time.time()
                ip = socket.gethostbyname(target)
                dns_time = (time.time() - start_time) * 1000
                
                # 测试ping（单次）
                ping_cmd = ["ping", "-c", "1", "-W", "2", target]
                ping_result = subprocess.run(ping_cmd, capture_output=True, text=True)
                
                if ping_result.returncode == 0:
                    # 提取ping时间
                    ping_lines = ping_result.stdout.split('\n')
                    ping_time = "N/A"
                    for line in ping_lines:
                        if "time=" in line:
                            parts = line.split("time=")
                            if len(parts) > 1:
                                ping_time = parts[1].split()[0]
                                break
                    
                    results.append(f"✅ {target}: DNS={dns_time:.1f}ms, Ping={ping_time}ms, IP={ip}")
                else:
                    results.append(f"⚠️ {target}: DNS解析成功({dns_time:.1f}ms, IP={ip})但ping失败")
                    
            except socket.gaierror:
                results.append(f"❌ {target}: DNS解析失败")
            except Exception as e:
                results.append(f"❌ {target}: 错误 - {str(e)}")
        
        # 测试curl访问（测试HTTP连接）
        http_results = []
        for target in ["https://www.baidu.com", "https://www.github.com"]:
            try:
                curl_cmd = ["curl", "-I", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-m", "5", target]
                http_code = subprocess.run(curl_cmd, capture_output=True, text=True).stdout.strip()
                
                if http_code.isdigit():
                    http_results.append(f"🌐 {target}: HTTP {http_code}")
                else:
                    http_results.append(f"🌐 {target}: 连接超时")
            except Exception as e:
                http_results.append(f"🌐 {target}: 错误 - {str(e)}")
        
        report = "📡 网络连接测试报告\n"
        report += "=" * 40 + "\n"
        report += "\n".join(results)
        report += "\n\n" + "=" * 40 + "\n"
        report += "HTTP连接测试:\n"
        report += "\n".join(http_results)
        
        return report