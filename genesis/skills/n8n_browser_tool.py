import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class N8nBrowserTool:
    @property
    def name(self) -> str:
        return "n8n_browser_tool"
        
    @property
    def description(self) -> str:
        return "AI浏览器工具，用于访问n8n Web界面，检查工作流状态，并执行必要的操作"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string", 
                    "description": "要执行的操作：check_status, open_web, list_workflows, check_ai_report",
                    "default": "check_status"
                },
                "url": {
                    "type": "string",
                    "description": "n8n Web界面URL",
                    "default": "http://localhost:5679"
                }
            },
            "required": []
        }
        
    async def execute(self, action: str = "check_status", url: str = "http://localhost:5679") -> str:
        if action == "check_status":
            return await self.check_n8n_status(url)
        elif action == "open_web":
            return await self.open_n8n_web(url)
        elif action == "list_workflows":
            return await self.list_workflows(url)
        elif action == "check_ai_report":
            return await self.check_ai_report_workflow(url)
        else:
            return f"未知操作: {action}"
    
    async def check_n8n_status(self, url: str) -> str:
        """检查n8n服务状态"""
        try:
            import requests
            response = requests.get(f"{url}/healthz", timeout=5)
            if response.status_code == 200:
                return f"✅ n8n服务正常运行: {response.json()}"
            else:
                return f"⚠️ n8n服务状态异常: {response.status_code}"
        except Exception as e:
            return f"❌ 无法连接到n8n服务: {str(e)}"
    
    async def open_n8n_web(self, url: str) -> str:
        """打开n8n Web界面"""
        try:
            import subprocess
            subprocess.Popen(["xdg-open", url])
            return f"✅ 已尝试打开n8n Web界面: {url}\n请手动检查工作流状态。"
        except Exception as e:
            return f"❌ 无法打开浏览器: {str(e)}\n请手动访问: {url}"
    
    async def list_workflows(self, url: str) -> str:
        """列出所有工作流（需要API密钥）"""
        try:
            import requests
            
            # 首先尝试获取工作流列表
            response = requests.get(f"{url}/api/v1/workflows", timeout=10)
            
            if response.status_code == 200:
                workflows = response.json()
                result = f"✅ 找到 {len(workflows.get('data', []))} 个工作流:\n"
                for wf in workflows.get('data', []):
                    result += f"- {wf.get('name', '未命名')} (ID: {wf.get('id', '未知')})\n"
                return result
            elif response.status_code == 401:
                return "❌ 需要API密钥认证。错误信息:\n" + response.text
            else:
                return f"⚠️ 获取工作流列表失败: {response.status_code}\n{response.text}"
                
        except Exception as e:
            return f"❌ 获取工作流列表时出错: {str(e)}"
    
    async def check_ai_report_workflow(self, url: str) -> str:
        """检查AI早报工作流状态"""
        try:
            import requests
            import os
            import json
            
            # 1. 检查工作流文件
            workflow_file = os.path.expanduser("~/Desktop/ai_morning_report_n8n_workflow.json")
            if not os.path.exists(workflow_file):
                return "❌ AI早报工作流文件不存在"
            
            # 2. 读取工作流内容
            with open(workflow_file, 'r', encoding='utf-8') as f:
                workflow_data = json.load(f)
            
            workflow_name = workflow_data.get('name', '未命名')
            
            # 3. 尝试获取工作流列表
            response = requests.get(f"{url}/api/v1/workflows", timeout=10)
            
            result = f"📋 AI早报工作流检查报告:\n"
            result += f"📁 本地文件: {workflow_file}\n"
            result += f"📝 工作流名称: {workflow_name}\n"
            result += f"📊 文件大小: {os.path.getsize(workflow_file)} 字节\n"
            
            if response.status_code == 200:
                workflows = response.json()
                workflow_list = workflows.get('data', [])
                
                # 检查是否已存在同名工作流
                existing_workflows = [wf for wf in workflow_list if wf.get('name') == workflow_name]
                if existing_workflows:
                    result += f"✅ 工作流已存在于n8n中 (ID: {existing_workflows[0].get('id')})\n"
                else:
                    result += "❌ 工作流未在n8n中找到\n"
                    result += "💡 建议: 需要通过Web界面或API导入工作流\n"
            else:
                result += f"⚠️ 无法获取工作流列表: {response.status_code}\n"
                result += f"🔑 需要API密钥认证\n"
            
            # 4. 检查工作流配置
            nodes = workflow_data.get('nodes', [])
            result += f"🔧 工作流包含 {len(nodes)} 个节点\n"
            
            # 检查定时触发器
            cron_nodes = [node for node in nodes if node.get('type') == 'n8n-nodes-base.cron']
            if cron_nodes:
                for cron in cron_nodes:
                    rule = cron.get('parameters', {}).get('rule', {})
                    result += f"⏰ 定时触发器: {rule}\n"
            
            return result
            
        except Exception as e:
            return f"❌ 检查AI早报工作流时出错: {str(e)}"