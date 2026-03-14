import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import json
import requests
from typing import Optional

class N8nApiClient(Tool):
    @property
    def name(self) -> str:
        return "n8n_api_client"
        
    @property
    def description(self) -> str:
        return "n8n API客户端，用于登录、获取令牌和部署工作流"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string", 
                    "description": "要执行的操作：login, create_user, get_api_token, deploy_workflow",
                    "enum": ["login", "create_user", "get_api_token", "deploy_workflow"]
                },
                "username": {
                    "type": "string", 
                    "description": "n8n用户名（邮箱）",
                    "default": "chendechuan117@gmail.com"
                },
                "password": {
                    "type": "string", 
                    "description": "n8n密码",
                    "default": "n8nadmin123"
                },
                "first_name": {
                    "type": "string", 
                    "description": "用户名字",
                    "default": "Admin"
                },
                "last_name": {
                    "type": "string", 
                    "description": "用户姓氏",
                    "default": "User"
                },
                "workflow_data": {
                    "type": "string", 
                    "description": "工作流JSON数据",
                    "default": ""
                }
            },
            "required": ["action"]
        }
        
    async def execute(self, action: str, username: str = "chendechuan117@gmail.com", 
                     password: str = "n8nadmin123", first_name: str = "Admin", 
                     last_name: str = "User", workflow_data: str = "") -> str:
        
        base_url = "http://localhost:5679"
        
        if action == "login":
            return await self._login(base_url, username, password)
        elif action == "create_user":
            return await self._create_user(base_url, username, password, first_name, last_name)
        elif action == "get_api_token":
            return await self._get_api_token(base_url, username, password)
        elif action == "deploy_workflow":
            return await self._deploy_workflow(base_url, username, password, workflow_data)
        else:
            return f"未知操作: {action}"
    
    async def _login(self, base_url: str, username: str, password: str) -> str:
        """登录n8n"""
        try:
            url = f"{base_url}/rest/login"
            data = {
                "emailOrLdapLoginId": username,
                "password": password
            }
            
            response = requests.post(url, json=data, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                return f"登录成功！响应: {json.dumps(result, indent=2)}"
            else:
                return f"登录失败 (状态码: {response.status_code}): {response.text}"
                
        except Exception as e:
            return f"登录请求失败: {str(e)}"
    
    async def _create_user(self, base_url: str, username: str, password: str, 
                          first_name: str, last_name: str) -> str:
        """创建用户（用于初始化）"""
        try:
            # 首先检查是否已经有用户
            check_url = f"{base_url}/rest/owner"
            response = requests.get(check_url, timeout=30)
            
            if response.status_code == 200:
                return "系统已经有所有者用户"
            
            # 创建所有者用户
            create_url = f"{base_url}/rest/owner/setup"
            data = {
                "email": username,
                "password": password,
                "firstName": first_name,
                "lastName": last_name
            }
            
            response = requests.post(create_url, json=data, timeout=30)
            
            if response.status_code == 200:
                return f"用户创建成功！响应: {response.text}"
            else:
                return f"用户创建失败 (状态码: {response.status_code}): {response.text}"
                
        except Exception as e:
            return f"用户创建请求失败: {str(e)}"
    
    async def _get_api_token(self, base_url: str, username: str, password: str) -> str:
        """获取API令牌"""
        try:
            # 首先登录获取会话
            login_url = f"{base_url}/rest/login"
            login_data = {
                "emailOrLdapLoginId": username,
                "password": password
            }
            
            session = requests.Session()
            login_response = session.post(login_url, json=login_data, timeout=30)
            
            if login_response.status_code != 200:
                return f"登录失败，无法获取API令牌: {login_response.text}"
            
            # 创建API令牌
            token_url = f"{base_url}/rest/api-key"
            token_data = {
                "name": "Automation Token"
            }
            
            token_response = session.post(token_url, json=token_data, timeout=30)
            
            if token_response.status_code == 200:
                result = token_response.json()
                api_key = result.get("apiKey")
                
                # 保存令牌到文件
                with open('/tmp/n8n_api_token.txt', 'w') as f:
                    f.write(api_key)
                
                return f"API令牌获取成功！\n令牌: {api_key}\n已保存到: /tmp/n8n_api_token.txt"
            else:
                return f"API令牌创建失败 (状态码: {token_response.status_code}): {token_response.text}"
                
        except Exception as e:
            return f"获取API令牌失败: {str(e)}"
    
    async def _deploy_workflow(self, base_url: str, username: str, password: str, 
                              workflow_data: str) -> str:
        """部署工作流"""
        try:
            # 首先获取API令牌
            token_result = await self._get_api_token(base_url, username, password)
            if "令牌:" not in token_result:
                return f"无法获取API令牌: {token_result}"
            
            # 从结果中提取令牌
            import re
            token_match = re.search(r'令牌:\s*([^\s\n]+)', token_result)
            if not token_match:
                return "无法从结果中提取令牌"
            
            token = token_match.group(1)
            
            # 如果没有提供工作流数据，创建一个简单的工作流
            if not workflow_data:
                workflow_data = json.dumps({
                    "name": "Test Workflow",
                    "nodes": [
                        {
                            "name": "Start",
                            "type": "n8n-nodes-base.start",
                            "position": [250, 300],
                            "parameters": {}
                        },
                        {
                            "name": "HTTP Request",
                            "type": "n8n-nodes-base.httpRequest",
                            "position": [450, 300],
                            "parameters": {
                                "url": "https://httpbin.org/get",
                                "method": "GET"
                            }
                        }
                    ],
                    "connections": {
                        "Start": {
                            "main": [
                                [
                                    {
                                        "node": "HTTP Request",
                                        "type": "main",
                                        "index": 0
                                    }
                                ]
                            ]
                        }
                    }
                })
            
            # 使用API部署工作流
            headers = {
                'X-N8N-API-KEY': token,
                'Content-Type': 'application/json'
            }
            
            workflow_json = json.loads(workflow_data)
            response = requests.post(
                f"{base_url}/api/v1/workflows",
                headers=headers,
                json=workflow_json,
                timeout=30
            )
            
            if response.status_code == 201:
                result = response.json()
                workflow_id = result.get('id')
                
                # 激活工作流
                activate_url = f"{base_url}/api/v1/workflows/{workflow_id}/activate"
                activate_response = requests.post(activate_url, headers=headers, timeout=30)
                
                if activate_response.status_code == 200:
                    return f"工作流部署成功！\n工作流ID: {workflow_id}\nAPI令牌: {token}"
                else:
                    return f"工作流创建成功但激活失败: {activate_response.text}"
            else:
                return f"工作流创建失败 (状态码: {response.status_code}): {response.text}"
                
        except Exception as e:
            return f"部署工作流失败: {str(e)}"