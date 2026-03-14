import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import json
import yaml
import os
from typing import Dict, List, Any, Optional

class N8nWorkflowAnalyzer(Tool):
    @property
    def name(self) -> str:
        return "n8n_workflow_analyzer"
        
    @property
    def description(self) -> str:
        return "分析n8n工作流JSON文件，检查结构完整性，特别是坐标字段和节点布局问题"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "workflow_file": {"type": "string", "description": "工作流JSON文件路径"},
                "check_position": {"type": "boolean", "description": "是否检查坐标字段", "default": True},
                "check_nodes": {"type": "boolean", "description": "是否检查节点结构", "default": True},
                "check_connections": {"type": "boolean", "description": "是否检查连接关系", "default": True}
            },
            "required": ["workflow_file"]
        }
        
    async def execute(self, workflow_file: str, check_position: bool = True, 
                     check_nodes: bool = True, check_connections: bool = True) -> str:
        try:
            if not os.path.exists(workflow_file):
                return f"❌ 文件不存在: {workflow_file}"
            
            with open(workflow_file, 'r', encoding='utf-8') as f:
                workflow_data = json.load(f)
            
            analysis_result = []
            analysis_result.append(f"📊 工作流分析报告: {workflow_file}")
            analysis_result.append(f"📁 文件大小: {os.path.getsize(workflow_file)} 字节")
            
            # 检查基本结构
            if "name" in workflow_data:
                analysis_result.append(f"📝 工作流名称: {workflow_data['name']}")
            
            if "nodes" in workflow_data:
                nodes_count = len(workflow_data["nodes"])
                analysis_result.append(f"🔢 节点数量: {nodes_count}")
                
                if check_nodes and nodes_count > 0:
                    node_analysis = self._analyze_nodes(workflow_data["nodes"], check_position)
                    analysis_result.extend(node_analysis)
            
            if "connections" in workflow_data:
                connections = workflow_data["connections"]
                if check_connections:
                    conn_analysis = self._analyze_connections(connections)
                    analysis_result.extend(conn_analysis)
            
            # 检查其他重要字段
            important_fields = ["id", "active", "settings", "triggerCount", "createdAt", "updatedAt"]
            missing_fields = []
            for field in important_fields:
                if field not in workflow_data:
                    missing_fields.append(field)
            
            if missing_fields:
                analysis_result.append(f"⚠️ 缺少重要字段: {', '.join(missing_fields)}")
            
            # 检查是否为"无头工作流"
            is_headless = self._check_headless_workflow(workflow_data)
            if is_headless:
                analysis_result.append("🚨 检测到'无头工作流'特征：缺少节点坐标或projectId字段")
            
            return "\n".join(analysis_result)
            
        except json.JSONDecodeError as e:
            return f"❌ JSON解析错误: {e}"
        except Exception as e:
            return f"❌ 分析过程中出错: {e}"
    
    def _analyze_nodes(self, nodes: List[Dict], check_position: bool) -> List[str]:
        analysis = []
        nodes_without_position = 0
        nodes_without_name = 0
        nodes_without_type = 0
        
        for i, node in enumerate(nodes):
            # 检查节点名称
            if "name" not in node:
                nodes_without_name += 1
                analysis.append(f"  ⚠️ 节点 {i}: 缺少'name'字段")
            
            # 检查节点类型
            if "type" not in node:
                nodes_without_type += 1
                analysis.append(f"  ⚠️ 节点 {i}: 缺少'type'字段")
            
            # 检查坐标字段
            if check_position:
                if "position" not in node:
                    nodes_without_position += 1
                    analysis.append(f"  ⚠️ 节点 {i}: 缺少'position'坐标字段")
                else:
                    position = node["position"]
                    if not isinstance(position, list) or len(position) != 2:
                        analysis.append(f"  ⚠️ 节点 {i}: position格式错误: {position}")
                    elif position[0] == 0 and position[1] == 0:
                        analysis.append(f"  ⚠️ 节点 {i}: position为默认值[0, 0]，可能未正确设置")
        
        summary = []
        if nodes_without_position > 0:
            summary.append(f"缺少坐标的节点: {nodes_without_position}/{len(nodes)}")
        if nodes_without_name > 0:
            summary.append(f"缺少名称的节点: {nodes_without_name}/{len(nodes)}")
        if nodes_without_type > 0:
            summary.append(f"缺少类型的节点: {nodes_without_type}/{len(nodes)}")
        
        if summary:
            analysis.insert(0, f"📋 节点分析总结: {', '.join(summary)}")
        
        return analysis
    
    def _analyze_connections(self, connections: Dict) -> List[str]:
        analysis = []
        
        if not connections:
            analysis.append("🔗 无连接关系定义")
            return analysis
        
        total_connections = 0
        for main_key, connections_dict in connections.items():
            if isinstance(connections_dict, dict):
                for output_key, connections_list in connections_dict.items():
                    if isinstance(connections_list, list):
                        total_connections += len(connections_list)
        
        analysis.append(f"🔗 总连接数: {total_connections}")
        
        # 检查连接完整性
        if total_connections == 0:
            analysis.append("⚠️ 工作流中没有定义任何连接")
        
        return analysis
    
    def _check_headless_workflow(self, workflow_data: Dict) -> bool:
        """检查是否为'无头工作流'（缺少坐标或projectId）"""
        is_headless = False
        
        # 检查projectId字段
        if "projectId" not in workflow_data:
            is_headless = True
        
        # 检查节点坐标
        if "nodes" in workflow_data:
            for node in workflow_data["nodes"]:
                if "position" not in node:
                    is_headless = True
                    break
                elif isinstance(node["position"], list) and len(node["position"]) == 2:
                    if node["position"][0] == 0 and node["position"][1] == 0:
                        is_headless = True
                        break
        
        return is_headless