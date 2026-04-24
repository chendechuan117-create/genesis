import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class N8nWorkflowDebugger(Tool):
    @property
    def name(self) -> str:
        return "n8n_workflow_debugger"
        
    @property
    def description(self) -> str:
        return "n8n工作流调试助手：基于用户实际痛点，提供工作流导入、调试、健康检查和错误诊断功能"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string", 
                    "description": "调试操作类型：health_check(健康检查), import_workflow(导入工作流), diagnose_error(错误诊断), list_workflows(列出工作流)",
                    "enum": ["health_check", "import_workflow", "diagnose_error", "list_workflows"]
                },
                "workflow_file": {
                    "type": "string", 
                    "description": "工作流文件路径（仅import_workflow和diagnose_error时需要）",
                    "default": ""
                },
                "n8n_url": {
                    "type": "string",
                    "description": "n8n服务地址，默认http://localhost:5678",
                    "default": "http://localhost:5678"
                },
                "jwt_token": {
                    "type": "string",
                    "description": "n8n JWT令牌（可选，用于认证访问）",
                    "default": ""
                }
            },
            "required": ["action"]
        }
        
    async def execute(self, action: str, workflow_file: str = "", n8n_url: str = "http://localhost:5678", jwt_token: str = "") -> str:
        import subprocess
        import json
        import os
        import requests
        from pathlib import Path
        
        result_lines = []
        
        # 健康检查
        if action == "health_check":
            try:
                health_url = f"{n8n_url.rstrip('/')}/healthz"
                result_lines.append(f"🔍 检查n8n服务健康状态: {health_url}")
                
                response = requests.get(health_url, timeout=10)
                if response.status_code == 200:
                    result_lines.append(f"✅ n8n服务运行正常: {response.json()}")
                    
                    # 检查工作流目录
                    workflow_dir = Path.home() / "Desktop" / "n8n_workflows"
                    if workflow_dir.exists():
                        workflow_files = list(workflow_dir.glob("*.json"))
                        result_lines.append(f"📁 发现工作流文件: {len(workflow_files)}个")
                        for wf in workflow_files[:5]:  # 只显示前5个
                            result_lines.append(f"  - {wf.name}")
                    else:
                        result_lines.append("⚠️ 未找到工作流目录，建议创建: ~/Desktop/n8n_workflows/")
                        
                else:
                    result_lines.append(f"❌ n8n服务异常: HTTP {response.status_code}")
                    
            except Exception as e:
                result_lines.append(f"❌ 健康检查失败: {str(e)}")
                result_lines.append("💡 建议检查:")
                result_lines.append("  1. n8n服务是否启动: docker ps | grep n8n")
                result_lines.append("  2. 端口是否正确: 默认5678")
                result_lines.append("  3. 防火墙设置")
        
        # 导入工作流
        elif action == "import_workflow":
            if not workflow_file:
                return "❌ 请提供workflow_file参数"
                
            workflow_path = Path(workflow_file)
            if not workflow_path.exists():
                return f"❌ 工作流文件不存在: {workflow_file}"
                
            try:
                # 读取工作流文件
                with open(workflow_path, 'r', encoding='utf-8') as f:
                    workflow_data = json.load(f)
                
                result_lines.append(f"📄 读取工作流文件: {workflow_path.name}")
                result_lines.append(f"📊 工作流信息:")
                result_lines.append(f"  - 名称: {workflow_data.get('name', '未命名')}")
                result_lines.append(f"  - 节点数量: {len(workflow_data.get('nodes', []))}")
                result_lines.append(f"  - 连接数量: {len(workflow_data.get('connections', {}))}")
                
                # 分析工作流结构
                node_types = {}
                for node in workflow_data.get('nodes', []):
                    node_type = node.get('type', 'unknown')
                    node_types[node_type] = node_types.get(node_type, 0) + 1
                
                result_lines.append("🔧 节点类型分布:")
                for node_type, count in node_types.items():
                    result_lines.append(f"  - {node_type}: {count}个")
                
                # 检查常见问题
                issues = []
                if len(workflow_data.get('nodes', [])) == 0:
                    issues.append("⚠️ 工作流没有节点")
                
                # 检查认证节点
                auth_nodes = [n for n in workflow_data.get('nodes', []) 
                             if 'http' in n.get('type', '').lower() or 'api' in n.get('type', '').lower()]
                if auth_nodes:
                    result_lines.append("🔐 发现API/HTTP节点:")
                    for node in auth_nodes[:3]:  # 只显示前3个
                        result_lines.append(f"  - {node.get('name', '未命名')} ({node.get('type')})")
                
                # 保存到标准位置
                target_dir = Path.home() / "Desktop" / "n8n_workflows"
                target_dir.mkdir(exist_ok=True)
                target_file = target_dir / workflow_path.name
                
                with open(target_file, 'w', encoding='utf-8') as f:
                    json.dump(workflow_data, f, indent=2, ensure_ascii=False)
                
                result_lines.append(f"💾 工作流已保存到: {target_file}")
                result_lines.append("🚀 导入完成！下一步:")
                result_lines.append("  1. 登录n8n界面 (http://localhost:5678)")
                result_lines.append("  2. 点击'导入工作流'")
                result_lines.append(f"  3. 选择文件: {target_file}")
                
                if issues:
                    result_lines.append("⚠️ 潜在问题:")
                    for issue in issues:
                        result_lines.append(f"  - {issue}")
                
            except json.JSONDecodeError as e:
                return f"❌ JSON解析错误: {str(e)}"
            except Exception as e:
                return f"❌ 导入失败: {str(e)}"
        
        # 错误诊断
        elif action == "diagnose_error":
            if not workflow_file:
                return "❌ 请提供workflow_file参数"
                
            workflow_path = Path(workflow_file)
            if not workflow_path.exists():
                return f"❌ 工作流文件不存在: {workflow_file}"
                
            try:
                with open(workflow_path, 'r', encoding='utf-8') as f:
                    workflow_data = json.load(f)
                
                result_lines.append(f"🔍 诊断工作流: {workflow_path.name}")
                
                # 常见错误模式检查
                checks = []
                
                # 1. 检查节点配置
                for node in workflow_data.get('nodes', []):
                    node_name = node.get('name', '未命名')
                    node_type = node.get('type', '')
                    
                    # HTTP节点检查
                    if 'http' in node_type.lower():
                        if not node.get('parameters', {}).get('authentication'):
                            checks.append(f"⚠️ HTTP节点 '{node_name}' 未配置认证")
                    
                    # 代码节点检查
                    if 'code' in node_type.lower():
                        code = node.get('parameters', {}).get('jsCode', '')
                        if not code.strip():
                            checks.append(f"⚠️ 代码节点 '{node_name}' 代码为空")
                
                # 2. 检查连接
                connections = workflow_data.get('connections', {})
                if not connections:
                    checks.append("⚠️ 工作流没有节点连接")
                
                # 3. 检查触发器
                trigger_nodes = [n for n in workflow_data.get('nodes', []) 
                               if 'trigger' in n.get('type', '').lower()]
                if not trigger_nodes:
                    checks.append("⚠️ 工作流没有触发器节点")
                
                # 4. 检查输出节点
                output_nodes = [n for n in workflow_data.get('nodes', []) 
                              if 'output' in n.get('type', '').lower() or 'write' in n.get('type', '').lower()]
                if not output_nodes:
                    checks.append("⚠️ 工作流没有输出节点")
                
                if checks:
                    result_lines.append("🔧 诊断结果:")
                    for check in checks:
                        result_lines.append(f"  - {check}")
                else:
                    result_lines.append("✅ 工作流结构基本正常")
                
                # 提供调试建议
                result_lines.append("💡 调试建议:")
                result_lines.append("  1. 在n8n中启用调试模式")
                result_lines.append("  2. 逐个节点测试功能")
                result_lines.append("  3. 检查API认证配置")
                result_lines.append("  4. 查看n8n日志: docker logs n8n")
                
            except Exception as e:
                return f"❌ 诊断失败: {str(e)}"
        
        # 列出工作流
        elif action == "list_workflows":
            try:
                workflow_dir = Path.home() / "Desktop" / "n8n_workflows"
                if not workflow_dir.exists():
                    return "📁 工作流目录不存在，请先创建: ~/Desktop/n8n_workflows/"
                
                workflow_files = list(workflow_dir.glob("*.json"))
                if not workflow_files:
                    return "📁 工作流目录为空"
                
                result_lines.append(f"📁 发现 {len(workflow_files)} 个工作流文件:")
                
                for wf in workflow_files:
                    try:
                        with open(wf, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        name = data.get('name', '未命名')
                        nodes = len(data.get('nodes', []))
                        result_lines.append(f"  - {wf.name}: {name} ({nodes}个节点)")
                    except:
                        result_lines.append(f"  - {wf.name}: 解析失败")
                
                result_lines.append("")
                result_lines.append("💡 使用建议:")
                result_lines.append("  1. 导入工作流: action='import_workflow', workflow_file='路径'")
                result_lines.append("  2. 诊断工作流: action='diagnose_error', workflow_file='路径'")
                
            except Exception as e:
                return f"❌ 列出工作流失败: {str(e)}"
        
        return "\n".join(result_lines)