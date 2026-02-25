import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class MessageSenderTool(Tool):
    @property
    def name(self) -> str:
        return "message_sender"
        
    @property
    def description(self) -> str:
        return "通过免费渠道发送消息的工具。支持SMTP邮件发送和GitHub Gist创建。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "要发送的消息内容"},
                "method": {"type": "string", "enum": ["smtp", "github_gist", "webhook"], "description": "发送方法：smtp(邮件), github_gist(Gist), webhook(HTTP请求)", "default": "github_gist"},
                "recipient_email": {"type": "string", "description": "收件人邮箱（仅method=smtp时需要）"},
                "subject": {"type": "string", "description": "邮件主题（仅method=smtp时需要）", "default": "Genesis苏醒通知"},
                "gist_description": {"type": "string", "description": "Gist描述（仅method=github_gist时需要）", "default": "Genesis苏醒状态报告"},
                "webhook_url": {"type": "string", "description": "Webhook URL（仅method=webhook时需要）", "default": "https://webhook.site/"}
            },
            "required": ["message"]
        }
        
    async def execute(self, message: str, method: str = "github_gist", recipient_email: str = None, subject: str = "Genesis苏醒通知", gist_description: str = "Genesis苏醒状态报告", webhook_url: str = "https://webhook.site/") -> str:
        import subprocess
        import json
        import time
        from datetime import datetime
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        full_message = f"[{timestamp}] {message}"
        
        if method == "github_gist":
            # 尝试通过GitHub API创建Gist
            try:
                # 创建一个简单的Python脚本来生成Gist
                gist_script = f'''
import requests
import json
import sys

message = '''{json.dumps(full_message)}'''
description = '''{gist_description}'''

# 创建公开Gist
gist_data = {{
    "description": description,
    "public": True,
    "files": {{
        "genesis_status.txt": {{
            "content": message
        }}
    }}
}}

# 注意：这里需要GitHub token，但我们可以尝试匿名创建（有限制）
# 或者使用环境变量中的token
token = None
import os
if os.environ.get("GITHUB_TOKEN"):
    token = os.environ.get("GITHUB_TOKEN")

headers = {{"Accept": "application/vnd.github.v3+json"}}
if token:
    headers["Authorization"] = f"token {{token}}"

try:
    response = requests.post(
        "https://api.github.com/gists",
        headers=headers,
        json=gist_data,
        timeout=10
    )
    
    if response.status_code == 201:
        gist_url = response.json()["html_url"]
        print(f"✅ Gist创建成功: {{gist_url}}")
        print(f"📝 消息: {{message}}")
        sys.exit(0)
    else:
        print(f"❌ Gist创建失败: {{response.status_code}}")
        print(f"响应: {{response.text}}")
        sys.exit(1)
except Exception as e:
    print(f"❌ 请求异常: {{e}}")
    sys.exit(1)
'''
                
                # 执行脚本
                result = subprocess.run(
                    ["python3", "-c", gist_script],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    return f"✅ 消息已通过GitHub Gist发送成功\n输出: {result.stdout}"
                else:
                    return f"❌ GitHub Gist发送失败，尝试备用方法\n错误: {result.stderr}"
                    
            except Exception as e:
                return f"❌ GitHub Gist发送异常: {e}"
                
        elif method == "smtp":
            if not recipient_email:
                return "❌ 邮件发送需要收件人邮箱"
                
            # 尝试使用免费SMTP服务（如Gmail、QQ等）
            # 注意：需要配置SMTP服务器和认证信息
            smtp_script = f'''
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import os
import sys

message = '''{json.dumps(full_message)}'''
recipient = '''{recipient_email}'''
subject = '''{subject}'''

# 尝试从环境变量获取SMTP配置
smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
smtp_port = int(os.environ.get("SMTP_PORT", "587"))
smtp_user = os.environ.get("SMTP_USER")
smtp_password = os.environ.get("SMTP_PASSWORD")

if not smtp_user or not smtp_password:
    print("❌ 未配置SMTP认证信息，请设置SMTP_USER和SMTP_PASSWORD环境变量")
    sys.exit(1)

try:
    # 创建邮件
    msg = MIMEText(message, 'plain', 'utf-8')
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = smtp_user
    msg['To'] = recipient
    
    # 连接SMTP服务器并发送
    server = smtplib.SMTP(smtp_server, smtp_port)
    server.starttls()
    server.login(smtp_user, smtp_password)
    server.sendmail(smtp_user, [recipient], msg.as_string())
    server.quit()
    
    print(f"✅ 邮件发送成功到 {{recipient}}")
    print(f"📧 主题: {{subject}}")
    print(f"📝 内容: {{message}}")
    sys.exit(0)
    
except Exception as e:
    print(f"❌ 邮件发送失败: {{e}}")
    sys.exit(1)
'''
            
            try:
                result = subprocess.run(
                    ["python3", "-c", smtp_script],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    return f"✅ 邮件发送成功\n输出: {result.stdout}"
                else:
                    return f"❌ 邮件发送失败\n错误: {result.stderr}"
                    
            except Exception as e:
                return f"❌ 邮件发送异常: {e}"
                
        elif method == "webhook":
            # 使用HTTP请求发送到Webhook
            try:
                webhook_script = f'''
import requests
import json
import sys

message = '''{json.dumps(full_message)}'''
webhook_url = '''{webhook_url}'''

try:
    # 尝试发送到webhook.site（免费测试服务）
    if "webhook.site" in webhook_url:
        # webhook.site需要特定格式
        data = {{
            "timestamp": "{timestamp}",
            "message": message,
            "source": "Genesis苏醒通知"
        }}
    else:
        data = {{"text": message}}
    
    headers = {{"Content-Type": "application/json"}}
    response = requests.post(
        webhook_url,
        json=data,
        headers=headers,
        timeout=10
    )
    
    if response.status_code in [200, 201, 202]:
        print(f"✅ Webhook发送成功: {{response.status_code}}")
        print(f"📝 消息: {{message}}")
        if "webhook.site" in webhook_url:
            print(f"🌐 查看地址: {{webhook_url}}")
        sys.exit(0)
    else:
        print(f"❌ Webhook发送失败: {{response.status_code}}")
        print(f"响应: {{response.text}}")
        sys.exit(1)
        
except Exception as e:
    print(f"❌ Webhook请求异常: {{e}}")
    sys.exit(1)
'''
                
                result = subprocess.run(
                    ["python3", "-c", webhook_script],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    return f"✅ Webhook发送成功\n输出: {result.stdout}"
                else:
                    return f"❌ Webhook发送失败\n错误: {result.stderr}"
                    
            except Exception as e:
                return f"❌ Webhook发送异常: {e}"
        
        return f"❌ 未知的发送方法: {method}"