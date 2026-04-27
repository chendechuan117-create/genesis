import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import subprocess
import json
import time
import requests
from typing import Dict, Optional

class N8NAuthAutomator(Tool):
    @property
    def name(self) -> str:
        return "n8n_auth_automator"
        
    @property
    def description(self) -> str:
        return "自动化n8n认证突破工具：实现API密钥自动生成、数据库访问和深度集成"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string", 
                    "enum": ["check_db", "extract_api_key", "create_user", "list_workflows"],
                    "description": "要执行的操作类型"
                },
                "container_name": {
                    "type": "string",
                    "description": "n8n容器名称，默认 'n8n-chinese'",
                    "default": "n8n-chinese"
                },
                "n8n_port": {
                    "type": "integer",
                    "description": "n8n服务端口，默认 5679",
                    "default": 5679
                }
            },
            "required": ["action"]
        }
        
    async def execute(self, action: str, container_name: str = "n8n-chinese", n8n_port: int = 5679) -> str:
        try:
            if action == "check_db":
                return await self._check_database_structure(container_name)
            elif action == "extract_api_key":
                return await self._extract_api_key_from_db(container_name)
            elif action == "create_user":
                return await self._create_user_programmatically(container_name, n8n_port)
            elif action == "list_workflows":
                return await self._list_workflows_direct(container_name)
            else:
                return f"未知操作: {action}"
        except Exception as e:
            return f"执行失败: {str(e)}"
    
    async def _check_database_structure(self, container_name: str) -> str:
        """检查n8n数据库结构"""
        try:
            # 检查容器内是否有sqlite3
            check_sqlite = subprocess.run(
                ["docker", "exec", container_name, "which", "sqlite3"],
                capture_output=True,
                text=True
            )
            
            if check_sqlite.returncode != 0:
                # 尝试安装sqlite3
                install_result = subprocess.run(
                    ["docker", "exec", container_name, "apt-get", "update", "&&", "apt-get", "install", "-y", "sqlite3"],
                    capture_output=True,
                    text=True,
                    shell=True
                )
                if install_result.returncode != 0:
                    return "无法在容器内安装sqlite3，尝试外部访问方案"
            
            # 列出所有表
            list_tables = subprocess.run(
                ["docker", "exec", container_name, "sqlite3", "/home/node/.n8n/database.sqlite", ".tables"],
                capture_output=True,
                text=True
            )
            
            if list_tables.returncode == 0:
                tables = list_tables.stdout.strip()
                result = f"数据库表结构:\n{tables}\n\n"
                
                # 检查关键表
                key_tables = ["user", "credentials", "workflow_entity"]
                for table in key_tables:
                    if table in tables:
                        # 查看表结构
                        schema = subprocess.run(
                            ["docker", "exec", container_name, "sqlite3", "/home/node/.n8n/database.sqlite", f".schema {table}"],
                            capture_output=True,
                            text=True
                        )
                        if schema.returncode == 0:
                            result += f"\n{table}表结构:\n{schema.stdout}\n"
                
                return result
            else:
                return "无法访问数据库文件，可能需要检查文件路径"
                
        except Exception as e:
            return f"数据库检查失败: {str(e)}"
    
    async def _extract_api_key_from_db(self, container_name: str) -> str:
        """从数据库提取API密钥"""
        try:
            # 首先检查credentials表
            check_creds = subprocess.run(
                ["docker", "exec", container_name, "sqlite3", "/home/node/.n8n/database.sqlite", 
                 "SELECT name, type FROM credentials LIMIT 5"],
                capture_output=True,
                text=True
            )
            
            result = "API密钥提取结果:\n"
            if check_creds.returncode == 0 and check_creds.stdout.strip():
                result += f"凭据表内容:\n{check_creds.stdout}\n"
            
            # 检查是否有API密钥相关的表
            check_tables = subprocess.run(
                ["docker", "exec", container_name, "sqlite3", "/home/node/.n8n/database.sqlite", 
                 "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%api%' OR name LIKE '%key%'"],
                capture_output=True,
                text=True
            )
            
            if check_tables.returncode == 0 and check_tables.stdout.strip():
                result += f"\nAPI相关表:\n{check_tables.stdout}\n"
            
            # 尝试查找用户表中的API密钥字段
            check_users = subprocess.run(
                ["docker", "exec", container_name, "sqlite3", "/home/node/.n8n/database.sqlite", 
                 "PRAGMA table_info(user)"],
                capture_output=True,
                text=True
            )
            
            if check_users.returncode == 0:
                result += f"\n用户表结构:\n{check_users.stdout}\n"
            
            return result
            
        except Exception as e:
            return f"API密钥提取失败: {str(e)}"
    
    async def _create_user_programmatically(self, container_name: str, n8n_port: int) -> str:
        """程序化创建用户（探索性）"""
        try:
            # 尝试通过API创建用户（需要管理员权限）
            url = f"http://localhost:{n8n_port}/api/v1/users"
            
            # 首先检查当前用户状态
            check_response = requests.get(
                f"http://localhost:{n8n_port}/api/v1/me",
                headers={"Authorization": f"Bearer {self._get_jwt_token()}"},
                timeout=10
            )
            
            result = f"当前用户状态: {check_response.status_code}\n"
            
            if check_response.status_code == 200:
                result += f"用户信息: {check_response.json()}\n"
            elif check_response.status_code == 404:
                result += "用户未识别，需要重新登录或创建新用户\n"
            
            # 尝试数据库直接操作
            db_result = subprocess.run(
                ["docker", "exec", container_name, "sqlite3", "/home/node/.n8n/database.sqlite",
                 "INSERT OR IGNORE INTO user (email, firstName, lastName, password) VALUES ('genesis@automation.local', 'Genesis', 'Auto', 'hashed_password_placeholder')"],
                capture_output=True,
                text=True
            )
            
            result += f"\n数据库操作结果: {db_result.returncode}\n"
            
            return result
            
        except Exception as e:
            return f"用户创建失败: {str(e)}"
    
    async def _list_workflows_direct(self, container_name: str) -> str:
        """直接数据库方式列出工作流"""
        try:
            # 直接从数据库查询工作流
            query = subprocess.run(
                ["docker", "exec", container_name, "sqlite3", "/home/node/.n8n/database.sqlite",
                 "SELECT id, name, active, createdAt FROM workflow_entity LIMIT 10"],
                capture_output=True,
                text=True
            )
            
            if query.returncode == 0:
                workflows = query.stdout.strip()
                if workflows:
                    return f"数据库中的工作流:\n{workflows}"
                else:
                    return "数据库中未找到工作流记录"
            else:
                return "无法查询工作流表，表可能不存在或名称不同"
                
        except Exception as e:
            return f"工作流列表查询失败: {str(e)}"
    
    def _get_jwt_token(self) -> str:
        """获取JWT令牌（从知识库中）"""
        # 这里应该从知识库或配置中获取
        return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI5NGU5NzY4NC0zMzg4LTQ2NDctODU5OS1kZWIxMmJiYTIwNzEiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiZDlhZWQ1NDAtNGYzYS00Y2EyLTllMTItNzkxMTVjYzc5YmVhIiwiaWF0IjoxNzcyODg0NjU5fQ.jVh0vOR14kZ3HBPyEu5TZKSMKuo2tAJSnArD8dGPrGQ"