import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class N8nWorkflowDeployer(Tool):
    @property
    def name(self) -> str:
        return "n8n_workflow_deployer"
        
    @property
    def description(self) -> str:
        return "用于部署和管理n8n工作流的工具。支持创建工作流、更新工作流、获取工作流列表等功能。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string", 
                    "enum": ["create", "update", "list", "get", "delete", "test_connection"],
                    "description": "要执行的操作：create(创建), update(更新), list(列表), get(获取), delete(删除), test_connection(测试连接)"
                },
                "workflow_data": {
                    "type": "object",
                    "description": "工作流数据（JSON格式），用于create和update操作"
                },
                "workflow_id": {
                    "type": "string",
                    "description": "工作流ID，用于get、update、delete操作"
                },
                "api_key": {
                    "type": "string",
                    "description": "n8n API密钥，如果未提供则尝试从环境变量获取"
                },
                "base_url": {
                    "type": "string",
                    "description": "n8n基础URL，默认http://localhost:5678",
                    "default": "http://localhost:5678"
                }
            },
            "required": ["action"]
        }
        
    async def execute(self, action: str, workflow_data: dict = None, workflow_id: str = None, 
                     api_key: str = None, base_url: str = "http://localhost:5678") -> str:
        import subprocess
        import json
        import time
        from datetime import datetime
        
        # 使用提供的API密钥或环境变量
        if not api_key:
            try:
                import os
                api_key = os.environ.get("N8N_API_KEY")
            except:
                pass
        
        def call_n8n_api(endpoint, method="GET", data=None):
            import requests
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
                
            url = f"{base_url}{endpoint}"
            try:
                if method == "GET":
                    response = requests.get(url, headers=headers, timeout=10)
                elif method == "POST":
                    response = requests.post(url, headers=headers, json=data, timeout=10)
                elif method == "PUT":
                    response = requests.put(url, headers=headers, json=data, timeout=10)
                elif method == "DELETE":
                    response = requests.delete(url, headers=headers, timeout=10)
                    
                return response
            except Exception as e:
                return None
        
        if action == "test_connection":
            # 测试连接
            health_response = call_n8n_api("/healthz")
            if health_response and health_response.status_code == 200:
                return f"✅ n8n连接正常！\nURL: {base_url}\n状态码: {health_response.status_code}"
            else:
                return f"❌ n8n连接失败！\n请检查n8n服务是否运行在{base_url}"
                
        elif action == "list":
            # 获取工作流列表
            workflows_response = call_n8n_api("/api/v1/workflows")
            if not workflows_response or workflows_response.status_code != 200:
                return "❌ 无法获取工作流列表"
                
            workflows = workflows_response.json().get("data", [])
            
            if not workflows:
                return "📭 当前没有工作流"
                
            result = f"📋 n8n工作流列表 (共{len(workflows)}个):\n"
            result += "=" * 60 + "\n"
            
            for i, workflow in enumerate(workflows, 1):
                wf_id = workflow.get("id", "N/A")
                wf_name = workflow.get("name", "未命名")
                wf_active = "✅" if workflow.get("active", False) else "⏸️"
                wf_updated = workflow.get("updatedAt", "未知")
                wf_nodes = len(workflow.get("nodes", []))
                
                result += f"{i}. {wf_name}\n"
                result += f"   ID: {wf_id} | 状态: {wf_active} | 节点数: {wf_nodes}\n"
                result += f"   最后更新: {wf_updated}\n"
                result += "-" * 40 + "\n"
                
            return result
            
        elif action == "get":
            # 获取特定工作流
            if not workflow_id:
                return "❌ 需要提供workflow_id参数"
                
            workflow_response = call_n8n_api(f"/api/v1/workflows/{workflow_id}")
            if not workflow_response or workflow_response.status_code != 200:
                return f"❌ 无法获取工作流 {workflow_id}"
                
            workflow = workflow_response.json().get("data", {})
            
            result = f"📄 工作流详情: {workflow.get('name', '未命名')}\n"
            result += "=" * 60 + "\n"
            result += f"ID: {workflow.get('id', 'N/A')}\n"
            result += f"状态: {'✅ 活跃' if workflow.get('active', False) else '⏸️ 非活跃'}\n"
            result += f"节点数: {len(workflow.get('nodes', []))}\n"
            result += f"创建时间: {workflow.get('createdAt', '未知')}\n"
            result += f"更新时间: {workflow.get('updatedAt', '未知')}\n"
            
            # 显示节点信息
            nodes = workflow.get("nodes", [])
            if nodes:
                result += "\n🔧 节点列表:\n"
                for node in nodes[:10]:  # 只显示前10个节点
                    node_name = node.get("name", "未命名")
                    node_type = node.get("type", "未知")
                    result += f"  • {node_name} ({node_type})\n"
                if len(nodes) > 10:
                    result += f"  ... 还有{len(nodes)-10}个节点\n"
                    
            return result
            
        elif action == "create":
            # 创建工作流
            if not workflow_data:
                return "❌ 需要提供workflow_data参数"
                
            create_response = call_n8n_api("/api/v1/workflows", method="POST", data=workflow_data)
            if not create_response:
                return "❌ 创建工作流失败：无法连接到n8n"
                
            if create_response.status_code in [200, 201]:
                created_workflow = create_response.json().get("data", {})
                wf_id = created_workflow.get("id", "未知")
                wf_name = created_workflow.get("name", "未命名")
                
                return f"✅ 工作流创建成功！\n名称: {wf_name}\nID: {wf_id}\n状态: {'活跃' if created_workflow.get('active', False) else '非活跃'}"
            else:
                return f"❌ 创建工作流失败！\n状态码: {create_response.status_code}\n响应: {create_response.text}"
                
        elif action == "update":
            # 更新工作流
            if not workflow_id:
                return "❌ 需要提供workflow_id参数"
            if not workflow_data:
                return "❌ 需要提供workflow_data参数"
                
            update_response = call_n8n_api(f"/api/v1/workflows/{workflow_id}", method="PUT", data=workflow_data)
            if not update_response:
                return "❌ 更新工作流失败：无法连接到n8n"
                
            if update_response.status_code == 200:
                updated_workflow = update_response.json().get("data", {})
                wf_name = updated_workflow.get("name", "未命名")
                
                return f"✅ 工作流更新成功！\n名称: {wf_name}\nID: {workflow_id}"
            else:
                return f"❌ 更新工作流失败！\n状态码: {update_response.status_code}\n响应: {update_response.text}"
                
        elif action == "delete":
            # 删除工作流
            if not workflow_id:
                return "❌ 需要提供workflow_id参数"
                
            # 先获取工作流信息用于确认
            workflow_response = call_n8n_api(f"/api/v1/workflows/{workflow_id}")
            if not workflow_response or workflow_response.status_code != 200:
                return f"❌ 工作流 {workflow_id} 不存在或无法访问"
                
            workflow_name = workflow_response.json().get("data", {}).get("name", "未知")
            
            # 执行删除
            delete_response = call_n8n_api(f"/api/v1/workflows/{workflow_id}", method="DELETE")
            if not delete_response:
                return "❌ 删除工作流失败：无法连接到n8n"
                
            if delete_response.status_code == 200:
                return f"✅ 工作流删除成功！\n名称: {workflow_name}\nID: {workflow_id}"
            else:
                return f"❌ 删除工作流失败！\n状态码: {delete_response.status_code}\n响应: {delete_response.text}"
        
        return f"✅ n8n工作流部署工具执行完成: {action}"