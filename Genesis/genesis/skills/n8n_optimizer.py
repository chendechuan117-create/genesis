import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

class N8nOptimizer(Tool):
    @property
    def name(self) -> str:
        return "n8n_optimizer"
        
    @property
    def description(self) -> str:
        return "专门优化n8n工作流管理的工具。提供智能工作流分析、性能优化建议、错误诊断和自动化部署功能。"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string", 
                    "enum": ["analyze_workflows", "optimize_performance", "diagnose_errors", "create_template", "test_connection"],
                    "description": "要执行的操作：analyze_workflows(分析工作流), optimize_performance(优化性能), diagnose_errors(诊断错误), create_template(创建模板), test_connection(测试连接)"
                },
                "workflow_id": {
                    "type": "string",
                    "description": "工作流ID（可选）"
                },
                "optimization_level": {
                    "type": "string",
                    "enum": ["basic", "advanced", "aggressive"],
                    "description": "优化级别",
                    "default": "basic"
                }
            },
            "required": ["action"]
        }
        
    async def execute(self, action: str, workflow_id: str = None, optimization_level: str = "basic") -> str:
        import subprocess
        import json
        import time
        from datetime import datetime
        
        base_url = "http://localhost:5678"
        api_key = None
        
        # 尝试从环境变量获取API密钥
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
            # 测试n8n连接
            health_response = call_n8n_api("/healthz")
            if health_response and health_response.status_code == 200:
                return f"✅ n8n连接正常！\n状态码: {health_response.status_code}\n响应: {health_response.text}"
            else:
                return f"❌ n8n连接失败！\n请检查n8n服务是否运行在{base_url}"
                
        elif action == "analyze_workflows":
            # 分析工作流
            workflows_response = call_n8n_api("/api/v1/workflows")
            if not workflows_response or workflows_response.status_code != 200:
                return "❌ 无法获取工作流列表"
                
            workflows = workflows_response.json().get("data", [])
            
            analysis = {
                "total_workflows": len(workflows),
                "active_workflows": sum(1 for w in workflows if w.get("active", False)),
                "inactive_workflows": sum(1 for w in workflows if not w.get("active", False)),
                "workflow_types": {},
                "complexity_stats": {
                    "simple": 0,  # < 5个节点
                    "medium": 0,  # 5-15个节点
                    "complex": 0  # > 15个节点
                }
            }
            
            for workflow in workflows:
                # 统计工作流类型
                workflow_type = workflow.get("type", "unknown")
                analysis["workflow_types"][workflow_type] = analysis["workflow_types"].get(workflow_type, 0) + 1
                
                # 分析复杂度
                nodes = workflow.get("nodes", [])
                node_count = len(nodes)
                if node_count < 5:
                    analysis["complexity_stats"]["simple"] += 1
                elif node_count <= 15:
                    analysis["complexity_stats"]["medium"] += 1
                else:
                    analysis["complexity_stats"]["complex"] += 1
            
            report = f"""
📊 n8n工作流分析报告
============================================================
📈 总体统计:
  • 总工作流数: {analysis['total_workflows']}
  • 活跃工作流: {analysis['active_workflows']}
  • 非活跃工作流: {analysis['inactive_workflows']}

🔧 工作流类型分布:
"""
            for wf_type, count in analysis["workflow_types"].items():
                report += f"  • {wf_type}: {count}个\n"
                
            report += f"""
📐 复杂度分析:
  • 简单工作流 (<5节点): {analysis['complexity_stats']['simple']}个
  • 中等工作流 (5-15节点): {analysis['complexity_stats']['medium']}个
  • 复杂工作流 (>15节点): {analysis['complexity_stats']['complex']}个

💡 优化建议:
"""
            if analysis["inactive_workflows"] > analysis["total_workflows"] * 0.5:
                report += "  • 建议清理非活跃工作流以提升性能\n"
            if analysis["complexity_stats"]["complex"] > 3:
                report += "  • 复杂工作流较多，建议拆分以提高可维护性\n"
            if len(analysis["workflow_types"]) > 5:
                report += "  • 工作流类型多样，建议建立标准化模板\n"
                
            return report
            
        elif action == "optimize_performance":
            # 性能优化
            optimization_tips = []
            
            if optimization_level == "basic":
                optimization_tips = [
                    "✅ 基础优化建议:",
                    "1. 启用工作流缓存以减少重复计算",
                    "2. 设置合理的执行超时时间",
                    "3. 定期清理日志文件",
                    "4. 使用批处理减少API调用次数",
                    "5. 配置适当的重试策略"
                ]
            elif optimization_level == "advanced":
                optimization_tips = [
                    "🚀 高级优化建议:",
                    "1. 实现工作流依赖关系管理",
                    "2. 使用Webhook替代轮询查询",
                    "3. 配置负载均衡和水平扩展",
                    "4. 实现数据库连接池",
                    "5. 优化节点执行顺序",
                    "6. 使用异步处理长时间任务"
                ]
            else:  # aggressive
                optimization_tips = [
                    "⚡ 激进优化建议:",
                    "1. 重构复杂工作流为微服务",
                    "2. 实现分布式任务队列",
                    "3. 使用内存数据库缓存热点数据",
                    "4. 实施A/B测试优化工作流逻辑",
                    "5. 自动化性能监控和告警",
                    "6. 实现蓝绿部署减少停机时间"
                ]
                
            return "\n".join(optimization_tips)
            
        elif action == "diagnose_errors":
            # 诊断错误
            import os
            import glob
            
            error_logs = []
            
            # 检查n8n日志文件
            log_patterns = [
                "/var/log/n8n/*.log",
                "/home/*/.n8n/logs/*.log",
                "./logs/*.log"
            ]
            
            for pattern in log_patterns:
                for log_file in glob.glob(pattern):
                    try:
                        with open(log_file, 'r') as f:
                            lines = f.readlines()[-50:]  # 读取最后50行
                            error_lines = [line for line in lines if "error" in line.lower() or "exception" in line.lower()]
                            if error_lines:
                                error_logs.append(f"📄 {log_file}:\n" + "\n".join(error_lines[-5:]))
                    except:
                        pass
            
            if error_logs:
                report = "🔍 发现错误日志:\n" + "\n".join(error_logs[:3])  # 显示最多3个文件
            else:
                report = "✅ 未发现明显的错误日志"
                
            # 检查系统资源
            try:
                import psutil
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                
                report += f"\n\n💾 系统资源状态:"
                report += f"\n  • CPU使用率: {cpu_percent}%"
                report += f"\n  • 内存使用率: {memory.percent}%"
                report += f"\n  • 可用内存: {memory.available / (1024**3):.1f} GB"
                
                if cpu_percent > 80:
                    report += "\n⚠️  CPU使用率较高，可能影响n8n性能"
                if memory.percent > 80:
                    report += "\n⚠️  内存使用率较高，可能导致工作流执行缓慢"
                    
            except:
                report += "\n\n⚠️  无法获取系统资源信息"
                
            return report
            
        elif action == "create_template":
            # 创建优化的工作流模板
            templates = {
                "webhook_processor": {
                    "name": "Webhook处理器模板",
                    "description": "优化的Webhook处理工作流，包含错误处理和重试机制",
                    "nodes": [
                        {
                            "name": "Webhook",
                            "type": "n8n-nodes-base.webhook",
                            "position": [250, 300],
                            "parameters": {
                                "path": "webhook-trigger",
                                "responseMode": "responseNode"
                            }
                        },
                        {
                            "name": "数据验证",
                            "type": "n8n-nodes-base.function",
                            "position": [450, 300],
                            "parameters": {
                                "functionCode": "// 数据验证逻辑\nconst data = $input.first().json;\nif (!data || !data.payload) {\n  throw new Error('无效的数据格式');\n}\nreturn data;"
                            }
                        },
                        {
                            "name": "错误处理",
                            "type": "n8n-nodes-base.errorTrigger",
                            "position": [650, 250],
                            "parameters": {}
                        },
                        {
                            "name": "成功响应",
                            "type": "n8n-nodes-base.respondToWebhook",
                            "position": [650, 350],
                            "parameters": {
                                "responseBody": "{\"status\": \"success\", \"message\": \"处理完成\"}"
                            }
                        }
                    ]
                },
                "api_integration": {
                    "name": "API集成模板",
                    "description": "标准化的API集成工作流，包含认证、限流和缓存",
                    "nodes": [
                        {
                            "name": "HTTP请求",
                            "type": "n8n-nodes-base.httpRequest",
                            "position": [250, 300],
                            "parameters": {
                                "url": "={{$parameter.url}}",
                                "authentication": "genericCredentialType",
                                "options": {
                                    "timeout": 30000
                                }
                            }
                        },
                        {
                            "name": "缓存检查",
                            "type": "n8n-nodes-base.function",
                            "position": [450, 250],
                            "parameters": {
                                "functionCode": "// 缓存逻辑\nconst cacheKey = $input.first().json.cacheKey;\n// 这里可以集成Redis或其他缓存\nreturn $input.first();"
                            }
                        },
                        {
                            "name": "速率限制",
                            "type": "n8n-nodes-base.function",
                            "position": [450, 350],
                            "parameters": {
                                "functionCode": "// 速率限制逻辑\nconst now = Date.now();\n// 实现令牌桶或漏桶算法\nreturn $input.first();"
                            }
                        }
                    ]
                }
            }
            
            if workflow_id and workflow_id in templates:
                template = templates[workflow_id]
                return f"""
📋 工作流模板: {template['name']}
============================================================
📝 描述: {template['description']}

🔧 节点配置:
{json.dumps(template['nodes'], indent=2, ensure_ascii=False)}

💡 使用说明:
1. 复制上述JSON到n8n工作流编辑器
2. 根据实际需求修改参数
3. 测试工作流功能
4. 部署到生产环境
"""
            else:
                available_templates = "\n".join([f"  • {key}: {value['name']}" for key, value in templates.items()])
                return f"""
📋 可用工作流模板:
============================================================
{available_templates}

📌 使用方法:
调用此工具时指定 workflow_id 参数，例如:
  workflow_id: "webhook_processor"
"""
        
        return f"✅ n8n优化工具执行完成: {action}"