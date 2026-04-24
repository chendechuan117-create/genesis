import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import json
import subprocess
import tempfile
import os
import time

class N8nApiKeyGenerator(Tool):
    @property
    def name(self) -> str:
        return "n8n_api_key_generator"
        
    @property
    def description(self) -> str:
        return "自动化生成n8n API密钥的工具，通过浏览器自动化访问设置页面"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "n8n_url": {"type": "string", "description": "n8n服务地址", "default": "http://localhost:5679"},
                "cookie_file": {"type": "string", "description": "cookie文件路径", "default": "/tmp/n8n_cookies.txt"},
                "key_name": {"type": "string", "description": "API密钥名称", "default": "Genesis_Generated_Key"}
            },
            "required": []
        }
        
    async def execute(self, n8n_url: str = "http://localhost:5679", cookie_file: str = "/tmp/n8n_cookies.txt", key_name: str = "Genesis_Generated_Key") -> str:
        try:
            # 第一步：访问API密钥页面获取CSRF令牌
            print("🔍 访问API密钥设置页面...")
            
            # 获取页面内容
            result = subprocess.run([
                'curl', '-s', '-X', 'GET', f'{n8n_url}/settings/api',
                '-H', 'accept: text/html',
                '-b', cookie_file
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                return f"❌ 访问API密钥页面失败: {result.stderr}"
            
            html_content = result.stdout
            
            # 查找可能的CSRF令牌
            csrf_token = None
            import re
            csrf_patterns = [
                r'name="_csrf" value="([^"]+)"',
                r'csrf-token" content="([^"]+)"',
                r'csrfToken.*?"([^"]+)"'
            ]
            
            for pattern in csrf_patterns:
                match = re.search(pattern, html_content)
                if match:
                    csrf_token = match.group(1)
                    break
            
            if not csrf_token:
                # 尝试从cookie中获取
                with open(cookie_file, 'r') as f:
                    for line in f:
                        if '_csrf' in line:
                            parts = line.strip().split('\t')
                            if len(parts) >= 7:
                                csrf_token = parts[6]
                                break
            
            if not csrf_token:
                return "❌ 无法找到CSRF令牌，可能需要手动登录"
            
            print(f"✅ 找到CSRF令牌: {csrf_token[:20]}...")
            
            # 第二步：尝试生成API密钥
            print(f"🔧 尝试生成API密钥: {key_name}")
            
            # 创建临时文件存储请求数据
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                request_data = {
                    "name": key_name,
                    "_csrf": csrf_token
                }
                json.dump(request_data, f)
                request_file = f.name
            
            try:
                # 发送创建API密钥的请求
                result = subprocess.run([
                    'curl', '-s', '-X', 'POST', f'{n8n_url}/rest/api-keys',
                    '-H', 'Content-Type: application/json',
                    '-H', 'accept: application/json',
                    '-b', cookie_file,
                    '-d', f'{{"name":"{key_name}"}}'
                ], capture_output=True, text=True)
                
                if result.returncode != 0:
                    return f"❌ 创建API密钥失败: {result.stderr}"
                
                response_text = result.stdout
                
                # 尝试解析响应
                try:
                    response_data = json.loads(response_text)
                    if 'apiKey' in response_data:
                        api_key = response_data['apiKey']
                        return f"""
🎯 API密钥生成成功！

📋 **密钥详情**：
- 名称：{key_name}
- API密钥：{api_key}
- 创建时间：{time.strftime('%Y-%m-%d %H:%M:%S')}

🔧 **使用方法**：
```bash
curl -X GET 'http://localhost:5679/api/v1/workflows' \\
  -H 'X-N8N-API-KEY: {api_key}' \\
  -H 'accept: application/json'
```

⚠️ **重要提示**：
1. 请立即保存此密钥，页面刷新后将无法再次查看
2. 密钥格式不是JWT令牌，而是随机字符串
3. 用于访问所有工作流API端点
"""
                    else:
                        return f"❌ 响应中未找到API密钥字段。响应内容：{response_text}"
                except json.JSONDecodeError:
                    # 尝试从HTML响应中提取
                    if 'apiKey' in response_text:
                        import re
                        key_match = re.search(r'apiKey.*?["\']([^"\']+)["\']', response_text)
                        if key_match:
                            api_key = key_match.group(1)
                            return f"✅ API密钥生成成功：{api_key}"
                    
                    return f"📋 原始响应：{response_text[:500]}..."
                
            finally:
                # 清理临时文件
                if os.path.exists(request_file):
                    os.unlink(request_file)
                    
        except Exception as e:
            return f"❌ 生成API密钥时发生错误：{str(e)}"