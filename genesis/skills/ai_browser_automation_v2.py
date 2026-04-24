import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import subprocess
import json
import asyncio
from typing import Dict, Any, Optional
import os
import sys

class AIBrowserAutomationToolV2(Tool):
    @property
    def name(self) -> str:
        return "ai_browser_automation_v2"
        
    @property
    def description(self) -> str:
        return "AI驱动的浏览器自动化工具V2，基于Browser-use库，支持自然语言指令控制浏览器操作"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string", 
                    "description": "要执行的操作类型：install（安装依赖）、run_task（运行自动化任务）、start_server（启动Web UI服务器）",
                    "enum": ["install", "run_task", "start_server"]
                },
                "task_instruction": {
                    "type": "string", 
                    "description": "自然语言任务指令，例如：'打开百度搜索AI技术'、'登录Gmail并检查邮件'",
                    "default": ""
                },
                "llm_provider": {
                    "type": "string",
                    "description": "LLM提供商：openai、claude、gemini等",
                    "default": "openai"
                },
                "api_key": {
                    "type": "string",
                    "description": "LLM API密钥",
                    "default": ""
                },
                "port": {
                    "type": "integer",
                    "description": "Web UI服务器端口",
                    "default": 8000
                }
            },
            "required": ["action"]
        }
        
    async def execute(self, action: str, task_instruction: str = "", llm_provider: str = "openai", 
                     api_key: str = "", port: int = 8000) -> str:
        
        if action == "install":
            return await self._install_dependencies()
        elif action == "run_task":
            return await self._run_automation_task(task_instruction, llm_provider, api_key)
        elif action == "start_server":
            return await self._start_webui_server(port)
        else:
            return f"未知操作: {action}"
    
    async def _install_dependencies(self) -> str:
        """安装Browser-use和相关依赖"""
        try:
            # 检查是否已安装
            import browser_use
            result = "✅ Browser-use已安装\n"
            
            # 尝试安装Playwright（跳过浏览器下载）
            try:
                import playwright
                result += "✅ Playwright已安装\n"
            except ImportError:
                cmd = "pip install playwright"
                install_result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                result += f"安装Playwright: {install_result.stdout}\n"
            
            return result
            
        except Exception as e:
            return f"❌ 安装检查失败: {str(e)}"
    
    async def _run_automation_task(self, task_instruction: str, llm_provider: str, api_key: str) -> str:
        """运行自动化任务"""
        if not task_instruction:
            return "❌ 请提供任务指令"
        
        if not api_key:
            return "❌ 请提供LLM API密钥"
        
        try:
            # 直接使用Browser-use库
            from browser_use import Agent
            from browser_use.browser.browser import BrowserConfig
            
            # 配置浏览器
            browser_config = BrowserConfig(
                headless=False,  # 显示浏览器界面
                disable_security=True
            )
            
            # 创建Agent
            agent = Agent(
                task=task_instruction,
                llm_provider=llm_provider,
                llm_config={"api_key": api_key},
                browser_config=browser_config
            )
            
            # 执行任务
            result = await agent.run()
            return f"✅ 任务执行成功:\n{result}"
            
        except Exception as e:
            return f"❌ 任务执行失败: {str(e)}\n提示：可能需要先安装系统浏览器或配置代理"
    
    async def _start_webui_server(self, port: int) -> str:
        """启动Browser-use Web UI服务器"""
        try:
            # 检查是否安装了web-ui
            cmd = f"python3 -c \"import sys; sys.path.insert(0, '.'); from browser_use.web.ui import main; main()\" --port {port}"
            
            # 启动服务器（后台运行）
            process = subprocess.Popen(
                ["python3", "-c", f"""
import sys
sys.path.insert(0, '.')
try:
    from browser_use.web.ui import main
    import asyncio
    asyncio.run(main(port={port}))
except ImportError as e:
    print(f"导入失败: {{e}}")
    print("可能需要安装: pip install browser-use[web]")
except Exception as e:
    print(f"启动失败: {{e}}")
"""],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # 等待一下看是否启动成功
            import time
            time.sleep(2)
            
            # 检查进程状态
            if process.poll() is None:
                return f"✅ Browser-use Web UI服务器已启动在后台\n访问地址: http://localhost:{port}\n进程ID: {process.pid}"
            else:
                stdout, stderr = process.communicate()
                return f"❌ 服务器启动失败:\nstdout: {stdout}\nstderr: {stderr}"
            
        except Exception as e:
            return f"❌ 启动服务器失败: {str(e)}"