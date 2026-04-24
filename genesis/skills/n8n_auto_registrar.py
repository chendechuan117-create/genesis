import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import subprocess
import time
import json
import os
from pathlib import Path

class N8NAutoRegistrar(Tool):
    @property
    def name(self) -> str:
        return "n8n_auto_registrar"
        
    @property
    def description(self) -> str:
        return "自动化注册n8n账号并生成API密钥的工具，用于测试工作流可见性问题"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "n8n_url": {
                    "type": "string", 
                    "description": "n8n服务地址，默认http://localhost:5679",
                    "default": "http://localhost:5679"
                },
                "username": {
                    "type": "string",
                    "description": "要注册的用户名",
                    "default": "test_user_001"
                },
                "email": {
                    "type": "string",
                    "description": "邮箱地址",
                    "default": "test@example.com"
                },
                "password": {
                    "type": "string",
                    "description": "密码",
                    "default": "TestPassword123!"
                }
            },
            "required": []
        }
        
    async def execute(self, n8n_url: str = "http://localhost:5679", 
                     username: str = "test_user_001",
                     email: str = "test@example.com",
                     password: str = "TestPassword123!") -> str:
        
        try:
            # 首先检查n8n服务是否运行
            result = subprocess.run(
                ["curl", "-s", f"{n8n_url}/healthz"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0 or '"status":"ok"' not in result.stdout:
                return f"❌ n8n服务不可用: {result.stdout}"
            
            # 创建测试账号信息文件
            account_info = {
                "n8n_url": n8n_url,
                "username": username,
                "email": email,
                "password": password,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": "pending_registration"
            }
            
            # 保存账号信息
            info_file = Path("/tmp/n8n_test_account.json")
            info_file.write_text(json.dumps(account_info, indent=2, ensure_ascii=False))
            
            # 尝试使用curl进行API注册（如果支持）
            registration_result = subprocess.run(
                ["curl", "-s", "-X", "POST", f"{n8n_url}/api/v1/users"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            result_text = f"✅ n8n服务运行正常: {n8n_url}\n"
            result_text += f"📋 测试账号信息已保存到: {info_file}\n"
            result_text += f"👤 用户名: {username}\n"
            result_text += f"📧 邮箱: {email}\n"
            result_text += f"🔑 密码: {password}\n\n"
            
            if registration_result.returncode == 0:
                result_text += f"📝 API注册尝试结果: {registration_result.stdout}\n"
            else:
                result_text += f"⚠️ API注册可能不支持，需要通过Web界面手动注册\n"
                result_text += f"请访问: {n8n_url}\n"
                result_text += "使用上述账号信息进行注册\n\n"
                result_text += "注册后请执行以下步骤:\n"
                result_text += "1. 登录到n8n Web界面\n"
                result_text += "2. 进入'设置' → 'API密钥'\n"
                result_text += "3. 生成新的API密钥\n"
                result_text += "4. 使用API密钥测试工作流API访问\n"
            
            return result_text
            
        except Exception as e:
            return f"❌ 注册过程中出现错误: {str(e)}"