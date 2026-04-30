import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import asyncio
import json
import time
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

class N8nBrowserAutomation(Tool):
    @property
    def name(self) -> str:
        return "n8n_browser_automation"
        
    @property
    def description(self) -> str:
        return "用于自动化登录n8n、获取API令牌和部署工作流的浏览器自动化工具"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string", 
                    "description": "要执行的操作：login, get_api_token, deploy_workflow",
                    "enum": ["login", "get_api_token", "deploy_workflow"]
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
                "workflow_data": {
                    "type": "string", 
                    "description": "工作流JSON数据（仅deploy_workflow时使用）",
                    "default": ""
                }
            },
            "required": ["action"]
        }
        
    async def execute(self, action: str, username: str = "chendechuan117@gmail.com", 
                     password: str = "n8nadmin123", workflow_data: str = "") -> str:
        
        if action == "login":
            return await self._login_n8n(username, password)
        elif action == "get_api_token":
            return await self._get_api_token(username, password)
        elif action == "deploy_workflow":
            return await self._deploy_workflow(username, password, workflow_data)
        else:
            return f"未知操作: {action}"
    
    async def _login_n8n(self, username: str, password: str) -> str:
        """登录n8n"""
        try:
            async with async_playwright() as p:
                # 启动浏览器，配置代理
                browser = await p.chromium.launch(
                    headless=False,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        f'--proxy-server=socks5://127.0.0.1:20170'
                    ]
                )
                
                context = await browser.new_context(
                    viewport={'width': 1280, 'height': 800},
                    proxy={
                        'server': 'socks5://127.0.0.1:20170'
                    }
                )
                
                page = await context.new_page()
                page.set_default_timeout(60000)
                
                # 访问n8n
                await page.goto('http://localhost:5679')
                
                # 等待页面加载
                await page.wait_for_load_state('networkidle')
                
                # 检查是否已经登录
                try:
                    await page.wait_for_selector('text=Workflows', timeout=5000)
                    return "已经登录到n8n"
                except:
                    pass
                
                # 查找登录表单
                await page.wait_for_selector('input[name="emailOrLdapLoginId"]', timeout=10000)
                
                # 输入用户名和密码
                await page.fill('input[name="emailOrLdapLoginId"]', username)
                await page.fill('input[name="password"]', password)
                
                # 点击登录按钮
                await page.click('button[type="submit"]')
                
                # 等待登录成功
                try:
                    await page.wait_for_selector('text=Workflows', timeout=15000)
                    # 截图保存
                    await page.screenshot(path='/tmp/n8n_login_success.png')
                    
                    # 获取cookies
                    cookies = await context.cookies()
                    cookies_json = json.dumps(cookies, indent=2)
                    
                    await browser.close()
                    
                    return f"登录成功！\n截图保存到: /tmp/n8n_login_success.png\nCookies: {cookies_json}"
                    
                except Exception as e:
                    # 尝试截图错误页面
                    await page.screenshot(path='/tmp/n8n_login_error.png')
                    await browser.close()
                    return f"登录失败: {str(e)}\n错误截图保存到: /tmp/n8n_login_error.png"
                    
        except Exception as e:
            return f"浏览器自动化错误: {str(e)}"
    
    async def _get_api_token(self, username: str, password: str) -> str:
        """获取API令牌"""
        try:
            async with async_playwright() as p:
                # 启动浏览器
                browser = await p.chromium.launch(
                    headless=False,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        f'--proxy-server=socks5://127.0.0.1:20170'
                    ]
                )
                
                context = await browser.new_context(
                    viewport={'width': 1280, 'height': 800},
                    proxy={
                        'server': 'socks5://127.0.0.1:20170'
                    }
                )
                
                page = await context.new_page()
                page.set_default_timeout(60000)
                
                # 访问n8n
                await page.goto('http://localhost:5679')
                await page.wait_for_load_state('networkidle')
                
                # 检查是否已经登录
                try:
                    await page.wait_for_selector('text=Workflows', timeout=5000)
                except:
                    # 需要先登录
                    await page.wait_for_selector('input[name="emailOrLdapLoginId"]', timeout=10000)
                    await page.fill('input[name="emailOrLdapLoginId"]', username)
                    await page.fill('input[name="password"]', password)
                    await page.click('button[type="submit"]')
                    await page.wait_for_selector('text=Workflows', timeout=15000)
                
                # 导航到设置页面
                await page.click('button[aria-label="User menu"]')
                await page.click('text=Settings')
                
                # 等待设置页面加载
                await page.wait_for_selector('text=API', timeout=10000)
                
                # 点击API菜单
                await page.click('text=API')
                
                # 等待API页面加载
                await page.wait_for_selector('text=Personal Access Tokens', timeout=10000)
                
                # 创建新的令牌
                await page.click('button:has-text("Create new token")')
                
                # 填写令牌信息
                await page.wait_for_selector('input[name="name"]', timeout=5000)
                await page.fill('input[name="name"]', 'Automation Token')
                
                # 生成令牌
                await page.click('button:has-text("Create")')
                
                # 等待令牌显示
                await page.wait_for_selector('code', timeout=10000)
                
                # 获取令牌
                token_element = await page.query_selector('code')
                token = await token_element.text_content()
                
                # 截图保存
                await page.screenshot(path='/tmp/n8n_api_token.png')
                
                # 保存令牌到文件
                with open('/tmp/n8n_api_token.txt', 'w') as f:
                    f.write(token)
                
                await browser.close()
                
                return f"API令牌获取成功！\n令牌: {token}\n已保存到: /tmp/n8n_api_token.txt\n截图: /tmp/n8n_api_token.png"
                
        except Exception as e:
            return f"获取API令牌失败: {str(e)}"
    
    async def _deploy_workflow(self, username: str, password: str, workflow_data: str) -> str:
        """部署工作流"""
        try:
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
            
            # 首先获取API令牌
            token_result = await self._get_api_token(username, password)
            if "令牌:" not in token_result:
                return f"无法获取API令牌: {token_result}"
            
            # 从结果中提取令牌
            import re
            token_match = re.search(r'令牌:\s*([^\s\n]+)', token_result)
            if not token_match:
                return "无法从结果中提取令牌"
            
            token = token_match.group(1)
            
            # 使用API部署工作流
            import aiohttp
            import asyncio
            
            async with aiohttp.ClientSession() as session:
                headers = {
                    'X-N8N-API-KEY': token,
                    'Content-Type': 'application/json'
                }
                
                # 创建工作流
                workflow_json = json.loads(workflow_data)
                async with session.post(
                    'http://localhost:5679/api/v1/workflows',
                    headers=headers,
                    json=workflow_json
                ) as response:
                    if response.status == 201:
                        result = await response.json()
                        workflow_id = result.get('id')
                        
                        # 激活工作流
                        activate_url = f'http://localhost:5679/api/v1/workflows/{workflow_id}/activate'
                        async with session.post(activate_url, headers=headers) as activate_response:
                            if activate_response.status == 200:
                                return f"工作流部署成功！\n工作流ID: {workflow_id}\nAPI令牌: {token}"
                            else:
                                return f"工作流创建成功但激活失败: {await activate_response.text()}"
                    else:
                        return f"工作流创建失败: {await response.text()}"
                        
        except Exception as e:
            return f"部署工作流失败: {str(e)}"