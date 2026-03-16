import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import subprocess
import json
import os
import tempfile
from pathlib import Path

class N8nBrowserAutomator(Tool):
    @property
    def name(self) -> str:
        return "n8n_browser_automator"
        
    @property
    def description(self) -> str:
        return "使用agent-browser自动化n8n Web界面操作，解决工作流不可见、用户登录和API密钥生成问题"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "操作类型：login(登录n8n), check_workflows(检查工作流), generate_api_key(生成API密钥), screenshot(截图)",
                    "enum": ["login", "check_workflows", "generate_api_key", "screenshot"]
                },
                "email": {
                    "type": "string",
                    "description": "n8n登录邮箱（login操作需要）",
                    "default": ""
                },
                "password": {
                    "type": "string", 
                    "description": "n8n登录密码（login操作需要）",
                    "default": ""
                },
                "n8n_url": {
                    "type": "string",
                    "description": "n8n服务地址",
                    "default": "http://localhost:5679"
                },
                "output_file": {
                    "type": "string",
                    "description": "输出文件路径（screenshot操作需要）",
                    "default": "/tmp/n8n_screenshot.png"
                }
            },
            "required": ["action"]
        }
        
    async def execute(self, action: str, email: str = "", password: str = "", 
                     n8n_url: str = "http://localhost:5679", output_file: str = "/tmp/n8n_screenshot.png") -> str:
        
        # 设置环境变量
        env = os.environ.copy()
        env["PATH"] = f"/home/chendechusn/.npm-global/bin:{env.get('PATH', '')}"
        
        def run_agent_command(cmd):
            """运行agent-browser命令"""
            try:
                result = subprocess.run(
                    cmd,
                    shell=True,
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=30
                )
                return result.returncode, result.stdout, result.stderr
            except subprocess.TimeoutExpired:
                return 1, "", "命令执行超时"
            except Exception as e:
                return 1, "", str(e)
        
        # 关闭现有会话
        run_agent_command("agent-browser close")
        
        if action == "login":
            if not email or not password:
                return "❌ 登录需要提供邮箱和密码"
            
            # 访问n8n
            code, out, err = run_agent_command(f'agent-browser open "{n8n_url}"')
            if code != 0:
                return f"❌ 无法访问n8n: {err}"
            
            # 等待页面加载
            run_agent_command("agent-browser wait --load networkidle")
            
            # 填写登录表单
            run_agent_command(f'agent-browser fill @e1 "{email}"')
            run_agent_command(f'agent-browser fill @e2 "{password}"')
            run_agent_command("agent-browser click @e3")
            
            # 等待登录完成
            run_agent_command("agent-browser wait --load networkidle")
            
            # 检查是否登录成功
            code, out, err = run_agent_command("agent-browser get title")
            if "n8n.io" in out and "登录" not in out:
                return f"✅ 登录成功！当前页面: {out.strip()}"
            else:
                return f"❌ 登录失败，可能密码错误或账户不存在。页面标题: {out.strip()}"
                
        elif action == "check_workflows":
            # 访问工作流页面
            code, out, err = run_agent_command(f'agent-browser open "{n8n_url}/workflows"')
            if code != 0:
                return f"❌ 无法访问工作流页面: {err}"
            
            # 等待页面加载
            run_agent_command("agent-browser wait --load networkidle")
            
            # 获取页面快照
            code, out, err = run_agent_command("agent-browser snapshot -i")
            if code != 0:
                return f"❌ 无法获取页面快照: {err}"
            
            # 分析工作流
            workflows_found = "工作流" in out or "Workflow" in out
            empty_state = "没有工作流" in out or "No workflows" in out or "empty" in out.lower()
            
            if empty_state:
                return "📭 工作流列表为空，没有找到任何工作流"
            elif workflows_found:
                # 提取工作流信息
                lines = out.split('\n')
                workflow_lines = [line for line in lines if "workflow" in line.lower() or "工作流" in line]
                return f"✅ 找到工作流！\n页面元素:\n{out}\n\n工作流相关元素: {len(workflow_lines)} 个"
            else:
                return f"🔍 页面内容:\n{out}\n\n可能需要先登录才能查看工作流"
                
        elif action == "generate_api_key":
            # 访问设置页面
            code, out, err = run_agent_command(f'agent-browser open "{n8n_url}/settings/api"')
            if code != 0:
                return f"❌ 无法访问API设置页面: {err}"
            
            # 等待页面加载
            run_agent_command("agent-browser wait --load networkidle")
            
            # 获取页面快照
            code, out, err = run_agent_command("agent-browser snapshot -i")
            if code != 0:
                return f"❌ 无法获取页面快照: {err}"
            
            # 分析API密钥相关元素
            api_key_elements = [line for line in out.split('\n') if "api" in line.lower() or "密钥" in line or "key" in line.lower()]
            
            if not api_key_elements:
                return f"🔍 未找到API密钥相关元素。页面内容:\n{out}"
            
            return f"🔑 API密钥设置页面已找到。相关元素:\n" + "\n".join(api_key_elements)
            
        elif action == "screenshot":
            # 访问n8n
            code, out, err = run_agent_command(f'agent-browser open "{n8n_url}"')
            if code != 0:
                return f"❌ 无法访问n8n: {err}"
            
            # 等待页面加载
            run_agent_command("agent-browser wait --load networkidle")
            
            # 截图
            code, out, err = run_agent_command(f'agent-browser screenshot "{output_file}"')
            if code != 0:
                return f"❌ 截图失败: {err}"
            
            return f"✅ 截图已保存到: {output_file}\n文件大小: {Path(output_file).stat().st_size if Path(output_file).exists() else 0} 字节"
        
        return f"❌ 未知操作: {action}"