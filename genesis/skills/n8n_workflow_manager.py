import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import json
import requests
import subprocess
import time
from typing import Dict, List, Optional, Any

class N8nWorkflowManager(Tool):
    @property
    def name(self) -> str:
        return "n8n_workflow_manager"
        
    @property
    def description(self) -> str:
        return "强大的n8n工作流管理器，支持工作流分析、创建、更新、删除、执行和监控"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "get", "create", "update", "delete", "execute", "analyze", "export", "import", "test_connection"],
                    "description": "要执行的操作"
                },
                "workflow_id": {
                    "type": "string",
                    "description": "工作流ID（对于get、update、delete、execute操作）"
                },
                "workflow_data": {
                    "type": "object",
                    "description": "工作流数据（JSON格式，对于create和update操作）"
                },
                "file_path": {
                    "type": "string",
                    "description": "文件路径（对于export和import操作）"
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
            "required": ["action"]
        }
        
    async def execute(self, action: str, workflow_id: Optional[str] = None, 
                     workflow_data: Optional[Dict] = None, file_path: Optional[str] = None,
                     api_key: Optional[str] = None, base_url: str = "http://localhost:5678") -> str:
        
        try:
            # 设置API端点
            api_endpoint = f"{base_url}/api/v1"
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["X-N8N-API-KEY"] = api_key
            
            if action == "test_connection":
                return await self._test_connection(base_url)
                
            elif action == "list":
                return await self._list_workflows(api_endpoint, headers)
                
            elif action == "get":
                if not workflow_id:
                    return "❌ 需要提供workflow_id参数"
                return await self._get_workflow(api_endpoint, headers, workflow_id)
                
            elif action == "create":
                if not workflow_data:
                    return "❌ 需要提供workflow_data参数"
                return await self._create_workflow(api_endpoint, headers, workflow_data)
                
            elif action == "update":
                if not workflow_id or not workflow_data:
                    return "❌ 需要提供workflow_id和workflow_data参数"
                return await self._update_workflow(api_endpoint, headers, workflow_id, workflow_data)
                
            elif action == "delete":
                if not workflow_id:
                    return "❌ 需要提供workflow_id参数"
                return await self._delete_workflow(api_endpoint, headers, workflow_id)
                
            elif action == "execute":
                if not workflow_id:
                    return "❌ 需要提供workflow_id参数"
                return await self._execute_workflow(api_endpoint, headers, workflow_id)
                
            elif action == "analyze":
                return await self._analyze_workflows(api_endpoint, headers)
                
            elif action == "export":
                if not file_path:
                    return "❌ 需要提供file_path参数"
                return await self._export_workflows(api_endpoint, headers, file_path)
                
            elif action == "import":
                if not file_path:
                    return "❌ 需要提供file_path参数"
                return await self._import_workflows(api_endpoint, headers, file_path)
                
            else:
                return f"❌ 不支持的操作: {action}"
                
        except Exception as e:
            return f"❌ 执行失败: {str(e)}"
    
    async def _test_connection(self, base_url: str) -> str:
        try:
            response = requests.get(f"{base_url}/healthz", timeout=10)
            if response.status_code == 200:
                return f"✅ n8n连接正常！\nURL: {base_url}\n状态码: {response.status_code}"
            else:
                return f"⚠️ n8n连接异常\nURL: {base_url}\n状态码: {response.status_code}"
        except Exception as e:
            return f"❌ n8n连接失败: {str(e)}"
    
    async def _list_workflows(self, api_endpoint: str, headers: Dict) -> str:
        try:
            response = requests.get(f"{api_endpoint}/workflows", headers=headers, timeout=10)
            if response.status_code == 200:
                workflows = response.json().get("data", [])
                if not workflows:
                    return "📭 没有找到工作流"
                
                result = ["📋 n8n工作流列表:"]
                for wf in workflows:
                    wf_id = wf.get("id", "N/A")
                    wf_name = wf.get("name", "未命名")
                    wf_active = "✅" if wf.get("active", False) else "❌"
                    wf_nodes = len(wf.get("nodes", []))
                    result.append(f"  {wf_active} [{wf_id}] {wf_name} - {wf_nodes}个节点")
                
                return "\n".join(result)
            else:
                return f"❌ 获取工作流列表失败: {response.status_code} - {response.text}"
        except Exception as e:
            return f"❌ 获取工作流列表异常: {str(e)}"
    
    async def _get_workflow(self, api_endpoint: str, headers: Dict, workflow_id: str) -> str:
        try:
            response = requests.get(f"{api_endpoint}/workflows/{workflow_id}", headers=headers, timeout=10)
            if response.status_code == 200:
                wf = response.json().get("data", {})
                return json.dumps(wf, indent=2, ensure_ascii=False)
            else:
                return f"❌ 获取工作流失败: {response.status_code} - {response.text}"
        except Exception as e:
            return f"❌ 获取工作流异常: {str(e)}"
    
    async def _create_workflow(self, api_endpoint: str, headers: Dict, workflow_data: Dict) -> str:
        try:
            response = requests.post(f"{api_endpoint}/workflows", 
                                   json=workflow_data, 
                                   headers=headers, 
                                   timeout=10)
            if response.status_code in [200, 201]:
                wf = response.json().get("data", {})
                wf_id = wf.get("id", "N/A")
                wf_name = wf.get("name", "未命名")
                return f"✅ 工作流创建成功！\nID: {wf_id}\n名称: {wf_name}"
            else:
                return f"❌ 创建工作流失败: {response.status_code} - {response.text}"
        except Exception as e:
            return f"❌ 创建工作流异常: {str(e)}"
    
    async def _update_workflow(self, api_endpoint: str, headers: Dict, workflow_id: str, workflow_data: Dict) -> str:
        try:
            response = requests.put(f"{api_endpoint}/workflows/{workflow_id}", 
                                  json=workflow_data, 
                                  headers=headers, 
                                  timeout=10)
            if response.status_code == 200:
                return f"✅ 工作流更新成功！\nID: {workflow_id}"
            else:
                return f"❌ 更新工作流失败: {response.status_code} - {response.text}"
        except Exception as e:
            return f"❌ 更新工作流异常: {str(e)}"
    
    async def _delete_workflow(self, api_endpoint: str, headers: Dict, workflow_id: str) -> str:
        try:
            response = requests.delete(f"{api_endpoint}/workflows/{workflow_id}", 
                                     headers=headers, 
                                     timeout=10)
            if response.status_code == 200:
                return f"✅ 工作流删除成功！\nID: {workflow_id}"
            else:
                return f"❌ 删除工作流失败: {response.status_code} - {response.text}"
        except Exception as e:
            return f"❌ 删除工作流异常: {str(e)}"
    
    async def _execute_workflow(self, api_endpoint: str, headers: Dict, workflow_id: str) -> str:
        try:
            response = requests.post(f"{api_endpoint}/workflows/{workflow_id}/execute", 
                                   headers=headers, 
                                   timeout=30)
            if response.status_code == 200:
                result = response.json()
                return f"✅ 工作流执行成功！\n结果: {json.dumps(result, indent=2, ensure_ascii=False)}"
            else:
                return f"❌ 执行工作流失败: {response.status_code} - {response.text}"
        except Exception as e:
            return f"❌ 执行工作流异常: {str(e)}"
    
    async def _analyze_workflows(self, api_endpoint: str, headers: Dict) -> str:
        try:
            response = requests.get(f"{api_endpoint}/workflows", headers=headers, timeout=10)
            if response.status_code != 200:
                return f"❌ 获取工作流列表失败: {response.status_code}"
            
            workflows = response.json().get("data", [])
            if not workflows:
                return "📭 没有找到工作流，无法进行分析"
            
            # 分析统计
            total_workflows = len(workflows)
            active_workflows = sum(1 for wf in workflows if wf.get("active", False))
            total_nodes = sum(len(wf.get("nodes", [])) for wf in workflows)
            avg_nodes = total_nodes / total_workflows if total_workflows > 0 else 0
            
            # 节点类型统计
            node_types = {}
            for wf in workflows:
                for node in wf.get("nodes", []):
                    node_type = node.get("type", "unknown")
                    node_types[node_type] = node_types.get(node_type, 0) + 1
            
            # 构建分析报告
            result = [
                "📊 n8n工作流分析报告:",
                "==========================================",
                f"📈 工作流总数: {total_workflows}",
                f"✅ 活跃工作流: {active_workflows}",
                f"❌ 非活跃工作流: {total_workflows - active_workflows}",
                f"🔧 总节点数: {total_nodes}",
                f"📐 平均节点数: {avg_nodes:.1f}",
                "",
                "🔍 节点类型分布:"
            ]
            
            for node_type, count in sorted(node_types.items(), key=lambda x: x[1], reverse=True):
                result.append(f"  {node_type}: {count}个")
            
            # 建议
            result.extend([
                "",
                "💡 优化建议:",
                "1. 检查非活跃工作流是否可以删除或归档",
                "2. 对于复杂工作流（节点数>20），考虑拆分",
                "3. 定期备份重要工作流",
                "4. 使用webhook触发器替代轮询以提高性能"
            ])
            
            return "\n".join(result)
            
        except Exception as e:
            return f"❌ 分析工作流异常: {str(e)}"
    
    async def _export_workflows(self, api_endpoint: str, headers: Dict, file_path: str) -> str:
        try:
            response = requests.get(f"{api_endpoint}/workflows", headers=headers, timeout=10)
            if response.status_code != 200:
                return f"❌ 获取工作流失败: {response.status_code}"
            
            workflows = response.json().get("data", [])
            
            # 保存到文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(workflows, f, indent=2, ensure_ascii=False)
            
            return f"✅ 工作流导出成功！\n文件: {file_path}\n导出数量: {len(workflows)}"
            
        except Exception as e:
            return f"❌ 导出工作流异常: {str(e)}"
    
    async def _import_workflows(self, api_endpoint: str, headers: Dict, file_path: str) -> str:
        try:
            # 读取文件
            with open(file_path, 'r', encoding='utf-8') as f:
                workflows = json.load(f)
            
            if not isinstance(workflows, list):
                return "❌ 文件格式错误：应该包含工作流列表"
            
            results = []
            for wf in workflows:
                try:
                    # 移除ID以确保创建新工作流
                    wf.pop("id", None)
                    wf.pop("createdAt", None)
                    wf.pop("updatedAt", None)
                    
                    response = requests.post(f"{api_endpoint}/workflows", 
                                           json=wf, 
                                           headers=headers, 
                                           timeout=10)
                    
                    if response.status_code in [200, 201]:
                        results.append(f"✅ 导入成功: {wf.get('name', '未命名')}")
                    else:
                        results.append(f"❌ 导入失败: {wf.get('name', '未命名')} - {response.status_code}")
                        
                except Exception as e:
                    results.append(f"❌ 导入异常: {wf.get('name', '未命名')} - {str(e)}")
            
            return "📋 工作流导入结果:\n" + "\n".join(results)
            
        except Exception as e:
            return f"❌ 导入工作流异常: {str(e)}"