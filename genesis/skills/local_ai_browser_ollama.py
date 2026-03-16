import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import subprocess
import json
import os
import tempfile
import time
from typing import Optional

class LocalAIBrowserOllama(Tool):
    @property
    def name(self) -> str:
        return "local_ai_browser_ollama"
        
    @property
    def description(self) -> str:
        return "使用本地Ollama LLM的AI浏览器自动化工具。支持完全本地运行的浏览器自动化任务，无需云API密钥。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string", 
                    "description": "要执行的浏览器任务，如'打开百度搜索AI技术'或'访问GitHub查看trending项目'"
                },
                "ollama_model": {
                    "type": "string",
                    "description": "使用的Ollama模型名称，默认'llama3.2'",
                    "default": "llama3.2"
                },
                "headless": {
                    "type": "boolean",
                    "description": "是否使用无头模式（不显示浏览器窗口），默认true",
                    "default": True
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "任务超时时间（秒），默认120",
                    "default": 120
                }
            },
            "required": ["task"]
        }
        
    async def execute(self, task: str, ollama_model: str = "llama3.2", headless: bool = True, timeout_seconds: int = 120) -> str:
        try:
            # 1. 检查Ollama服务是否运行
            ollama_status = await self._check_ollama_service()
            if not ollama_status["running"]:
                return f"❌ Ollama服务未运行。请先启动Ollama服务：\n命令: ollama serve\n\n或者使用：ollama pull {ollama_model} 下载模型"
            
            # 2. 检查模型是否可用
            model_available = await self._check_ollama_model(ollama_model)
            if not model_available:
                return f"❌ Ollama模型 '{ollama_model}' 未下载。请先下载模型：\n命令: ollama pull {ollama_model}"
            
            # 3. 创建Python脚本执行browser-use任务
            script_content = self._create_browser_use_script(task, ollama_model, headless)
            
            # 4. 执行脚本
            result = await self._run_browser_use_script(script_content, timeout_seconds)
            
            return result
            
        except Exception as e:
            return f"❌ 执行失败: {str(e)}\n\n建议：\n1. 确保Ollama服务运行: ollama serve\n2. 下载模型: ollama pull {ollama_model}\n3. 检查browser-use安装: pip install browser-use[web]"
    
    async def _check_ollama_service(self) -> dict:
        """检查Ollama服务状态"""
        try:
            result = subprocess.run(["ollama", "list"], 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=10)
            return {"running": result.returncode == 0, "output": result.stdout}
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return {"running": False, "output": "Ollama服务未运行或未安装"}
    
    async def _check_ollama_model(self, model_name: str) -> bool:
        """检查Ollama模型是否可用"""
        try:
            result = subprocess.run(["ollama", "list"], 
                                  capture_output=True, 
                                  text=True, 
                                  timeout=10)
            return model_name in result.stdout
        except:
            return False
    
    def _create_browser_use_script(self, task: str, model: str, headless: bool) -> str:
        """创建browser-use执行脚本"""
        headless_str = "True" if headless else "False"
        
        script = f'''#!/usr/bin/env python3
import asyncio
import sys
from browser_use import Agent
from browser_use.browser.browser import BrowserConfig

async def main():
    try:
        print("🚀 启动本地AI浏览器自动化...")
        print(f"任务: {task}")
        print(f"使用模型: {model}")
        print(f"无头模式: {headless_str}")
        
        # 配置浏览器
        browser_config = BrowserConfig(
            headless={headless_str},
            disable_security=True
        )
        
        # 创建Agent，使用本地Ollama
        agent = Agent(
            task="{task}",
            browser_config=browser_config,
            llm_config={{
                "type": "ollama",
                "model": "{model}",
                "base_url": "http://localhost:11434"
            }}
        )
        
        print("🤖 AI Agent正在执行任务...")
        result = await agent.run()
        
        print("✅ 任务完成！")
        print(f"执行结果: {{result}}")
        
        # 返回结构化结果
        return {{
            "success": True,
            "task": "{task}",
            "model": "{model}",
            "result": str(result)
        }}
        
    except Exception as e:
        print(f"❌ 执行失败: {{e}}")
        return {{
            "success": False,
            "error": str(e),
            "task": "{task}",
            "model": "{model}"
        }}

if __name__ == "__main__":
    result = asyncio.run(main())
    print("\\n📊 执行摘要:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
'''
        return script
    
    async def _run_browser_use_script(self, script_content: str, timeout: int) -> str:
        """执行browser-use脚本"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(script_content)
            script_path = f.name
        
        try:
            # 执行Python脚本
            process = subprocess.Popen(
                ["python3", script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            try:
                stdout, stderr = process.communicate(timeout=timeout)
                return_code = process.returncode
                
                result = f"📋 执行结果 (退出码: {return_code}):\n\n"
                result += "=== 标准输出 ===\n"
                result += stdout + "\n\n"
                
                if stderr:
                    result += "=== 标准错误 ===\n"
                    result += stderr + "\n\n"
                
                if return_code == 0:
                    result += "✅ 任务执行成功！"
                else:
                    result += "⚠️ 任务执行遇到问题，请检查错误信息。"
                
                return result
                
            except subprocess.TimeoutExpired:
                process.kill()
                return "⏰ 任务执行超时！建议：\n1. 增加timeout_seconds参数\n2. 检查网络连接\n3. 简化任务复杂度"
                
        finally:
            # 清理临时文件
            try:
                os.unlink(script_path)
            except:
                pass