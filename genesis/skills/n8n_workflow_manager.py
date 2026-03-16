import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import requests
import json
from typing import Dict, Any, Optional

class N8NWorkflowManager:
    def __init__(self, base_url: str = "http://localhost:5679"):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.logged_in = False
        
    def login(self, email: str, password: str) -> bool:
        """登录到n8n"""
        try:
            # 首先检查是否需要设置所有者
            response = self.session.get(f"{self.base_url}/rest/settings")
            if response.status_code == 200:
                settings = response.json().get('data', {})
                user_management = settings.get('userManagement', {})
                if user_management.get('showSetupOnFirstLoad', False):
                    # 需要先设置所有者
                    setup_data = {
                        "email": email,
                        "firstName": "Admin",
                        "lastName": "User",
                        "password": password
                    }
                    setup_response = self.session.post(
                        f"{self.base_url}/rest/owner/setup",
                        json=setup_data
                    )
                    if setup_response.status_code != 200:
                        return False
            
            # 登录
            login_data = {
                "emailOrLdapLoginId": email,
                "password": password
            }
            login_response = self.session.post(
                f"{self.base_url}/rest/login",
                json=login_data
            )
            
            if login_response.status_code == 200:
                self.logged_in = True
                return True
            return False
            
        except Exception as e:
            print(f"登录失败: {e}")
            return False
    
    def create_workflow(self, workflow_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建工作流"""
        if not self.logged_in:
            return None
            
        try:
            response = self.session.post(
                f"{self.base_url}/rest/workflows",
                json=workflow_data
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"创建工作流失败: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"创建工作流异常: {e}")
            return None
    
    def get_workflows(self) -> Optional[Dict[str, Any]]:
        """获取所有工作流"""
        if not self.logged_in:
            return None
            
        try:
            response = self.session.get(f"{self.base_url}/rest/workflows")
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"获取工作流失败: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"获取工作流异常: {e}")
            return None
    
    def test_connection(self) -> bool:
        """测试连接"""
        try:
            response = self.session.get(f"{self.base_url}/healthz")
            return response.status_code == 200
        except:
            return False

class N8NWorkflowManagerTool:
    @property
    def name(self) -> str:
        return "n8n_workflow_manager"
        
    @property
    def description(self) -> str:
        return "管理n8n工作流的工具，支持登录、创建和获取工作流"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string", 
                    "enum": ["login", "create_workflow", "get_workflows", "test"],
                    "description": "要执行的操作"
                },
                "email": {
                    "type": "string",
                    "description": "登录邮箱（仅login操作需要）"
                },
                "password": {
                    "type": "string", 
                    "description": "登录密码（仅login操作需要）"
                },
                "workflow_data": {
                    "type": "object",
                    "description": "工作流数据（仅create_workflow操作需要）"
                }
            },
            "required": ["action"]
        }
        
    async def execute(self, action: str, email: str = None, password: str = None, workflow_data: dict = None) -> str:
        manager = N8NWorkflowManager()
        
        if action == "test":
            if manager.test_connection():
                return "n8n服务连接正常"
            else:
                return "n8n服务连接失败"
                
        elif action == "login":
            if not email or not password:
                return "需要提供邮箱和密码"
                
            if manager.login(email, password):
                return "登录成功"
            else:
                return "登录失败"
                
        elif action == "create_workflow":
            if not workflow_data:
                return "需要提供工作流数据"
                
            result = manager.create_workflow(workflow_data)
            if result:
                return f"工作流创建成功: {json.dumps(result, ensure_ascii=False, indent=2)}"
            else:
                return "工作流创建失败"
                
        elif action == "get_workflows":
            result = manager.get_workflows()
            if result:
                return f"工作流列表: {json.dumps(result, ensure_ascii=False, indent=2)}"
            else:
                return "获取工作流失败"
                
        else:
            return f"未知操作: {action}"