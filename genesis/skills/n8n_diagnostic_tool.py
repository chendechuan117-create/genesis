import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import subprocess
import json
import time
import requests
from typing import Dict, Any, List

class N8nDiagnosticTool(Tool):
    @property
    def name(self) -> str:
        return "n8n_diagnostic_tool"
        
    @property
    def description(self) -> str:
        return "n8n诊断工具，用于全面检查n8n服务状态、配置、工作流和性能问题"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "check_type": {
                    "type": "string", 
                    "enum": ["full", "service", "workflows", "performance", "config"],
                    "description": "检查类型：full(全面检查), service(服务状态), workflows(工作流), performance(性能), config(配置)",
                    "default": "full"
                },
                "api_key": {
                    "type": "string",
                    "description": "n8n API密钥（可选）"
                },
                "base_url": {
                    "type": "string",
                    "description": "n8n基础URL",
                    "default": "http://localhost:5678"
                }
            },
            "required": []
        }
        
    async def execute(self, check_type: str = "full", api_key: str = None, base_url: str = "http://localhost:5678") -> str:
        results = []
        
        # 检查服务状态
        if check_type in ["full", "service"]:
            results.append(await self._check_service_status(base_url))
        
        # 检查工作流
        if check_type in ["full", "workflows"]:
            results.append(await self._check_workflows(base_url, api_key))
        
        # 检查性能
        if check_type in ["full", "performance"]:
            results.append(await self._check_performance(base_url))
        
        # 检查配置
        if check_type in ["full", "config"]:
            results.append(await self._check_configuration())
        
        return "\n\n".join(results)
    
    async def _check_service_status(self, base_url: str) -> str:
        """检查n8n服务状态"""
        result = ["🔍 n8n服务状态检查", "=" * 40]
        
        try:
            # 检查健康端点
            response = requests.get(f"{base_url}/healthz", timeout=5)
            result.append(f"✅ 健康检查: {response.status_code} - {response.text}")
        except Exception as e:
            result.append(f"❌ 健康检查失败: {str(e)}")
        
        try:
            # 检查进程
            proc = subprocess.run(["ps", "aux", "|", "grep", "n8n", "|", "grep", "-v", "grep"], 
                                capture_output=True, text=True, shell=True)
            if proc.stdout:
                result.append(f"✅ n8n进程运行中:")
                for line in proc.stdout.strip().split('\n'):
                    result.append(f"  {line}")
            else:
                result.append("❌ 未找到n8n进程")
        except Exception as e:
            result.append(f"❌ 进程检查失败: {str(e)}")
        
        try:
            # 检查端口
            proc = subprocess.run(["ss", "-tlnp", "|", "grep", ":5678"], 
                                capture_output=True, text=True, shell=True)
            if proc.stdout:
                result.append(f"✅ 端口监听: {proc.stdout.strip()}")
            else:
                result.append("❌ 端口5678未监听")
        except Exception as e:
            result.append(f"❌ 端口检查失败: {str(e)}")
        
        return "\n".join(result)
    
    async def _check_workflows(self, base_url: str, api_key: str = None) -> str:
        """检查n8n工作流"""
        result = ["🔍 n8n工作流检查", "=" * 40]
        
        headers = {}
        if api_key:
            headers["X-N8N-API-KEY"] = api_key
        
        try:
            # 尝试获取工作流列表
            response = requests.get(f"{base_url}/api/v1/workflows", headers=headers, timeout=10)
            if response.status_code == 200:
                workflows = response.json().get("data", [])
                result.append(f"✅ 找到 {len(workflows)} 个工作流")
                
                # 统计工作流状态
                active_count = sum(1 for wf in workflows if wf.get("active", False))
                result.append(f"  - 活跃工作流: {active_count}")
                result.append(f"  - 非活跃工作流: {len(workflows) - active_count}")
                
                # 显示前5个工作流
                for i, wf in enumerate(workflows[:5]):
                    result.append(f"  {i+1}. {wf.get('name', '未命名')} (ID: {wf.get('id')}, 活跃: {wf.get('active', False)})")
                
                if len(workflows) > 5:
                    result.append(f"  ... 还有 {len(workflows) - 5} 个工作流")
            elif response.status_code == 401:
                result.append("⚠️ 需要API密钥访问工作流")
            else:
                result.append(f"❌ 获取工作流失败: {response.status_code} - {response.text}")
        except Exception as e:
            result.append(f"❌ 工作流检查失败: {str(e)}")
        
        return "\n".join(result)
    
    async def _check_performance(self, base_url: str) -> str:
        """检查n8n性能"""
        result = ["🔍 n8n性能检查", "=" * 40]
        
        try:
            # 检查系统资源
            proc = subprocess.run(["top", "-bn1", "|", "grep", "n8n"], 
                                capture_output=True, text=True, shell=True)
            if proc.stdout:
                result.append("✅ n8n资源使用:")
                for line in proc.stdout.strip().split('\n'):
                    result.append(f"  {line}")
            
            # 检查内存使用
            proc = subprocess.run(["ps", "-eo", "pid,comm,%mem,%cpu", "|", "grep", "n8n"], 
                                capture_output=True, text=True, shell=True)
            if proc.stdout:
                result.append("✅ n8n进程资源:")
                for line in proc.stdout.strip().split('\n'):
                    result.append(f"  {line}")
        except Exception as e:
            result.append(f"❌ 性能检查失败: {str(e)}")
        
        return "\n".join(result)
    
    async def _check_configuration(self) -> str:
        """检查n8n配置"""
        result = ["🔍 n8n配置检查", "=" * 40]
        
        try:
            # 检查配置文件
            config_paths = [
                "~/.n8n/config",
                "/etc/n8n/config",
                "/usr/local/etc/n8n/config"
            ]
            
            found_config = False
            for path in config_paths:
                expanded_path = subprocess.run(["echo", path], capture_output=True, text=True, shell=True).stdout.strip()
                proc = subprocess.run(["ls", "-la", expanded_path], capture_output=True, text=True)
                if proc.returncode == 0:
                    result.append(f"✅ 找到配置文件: {expanded_path}")
                    found_config = True
                    break
            
            if not found_config:
                result.append("⚠️ 未找到标准配置文件")
            
            # 检查环境变量
            proc = subprocess.run(["env", "|", "grep", "-i", "n8n"], 
                                capture_output=True, text=True, shell=True)
            if proc.stdout:
                result.append("✅ n8n环境变量:")
                for line in proc.stdout.strip().split('\n'):
                    if "N8N" in line:
                        result.append(f"  {line}")
            
            # 检查版本
            proc = subprocess.run(["n8n", "--version"], capture_output=True, text=True)
            if proc.returncode == 0:
                result.append(f"✅ n8n版本: {proc.stdout.strip()}")
            else:
                result.append("⚠️ 无法获取n8n版本")
                
        except Exception as e:
            result.append(f"❌ 配置检查失败: {str(e)}")
        
        return "\n".join(result)