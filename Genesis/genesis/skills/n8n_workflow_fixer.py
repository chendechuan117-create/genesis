import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from genesis.core.base import Tool

import json
import os
from typing import Dict, List, Any
import uuid
from datetime import datetime

class N8nWorkflowFixer(Tool):
    @property
    def name(self) -> str:
        return "n8n_workflow_fixer"
        
    @property
    def description(self) -> str:
        return "修复n8n'无头工作流'问题：自动添加缺失的坐标字段和必要字段"
        
    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "input_file": {"type": "string", "description": "输入的工作流JSON文件路径"},
                "output_file": {"type": "string", "description": "输出的修复后文件路径"},
                "add_positions": {"type": "boolean", "description": "是否添加缺失的坐标字段", "default": True},
                "add_missing_fields": {"type": "boolean", "description": "是否添加缺失的必要字段", "default": True},
                "base_x": {"type": "number", "description": "起始X坐标", "default": 100},
                "base_y": {"type": "number", "description": "起始Y坐标", "default": 200},
                "x_spacing": {"type": "number", "description": "节点水平间距", "default": 300},
                "y_spacing": {"type": "number", "description": "节点垂直间距", "default": 150}
            },
            "required": ["input_file", "output_file"]
        }
        
    async def execute(self, input_file: str, output_file: str, add_positions: bool = True,
                     add_missing_fields: bool = True, base_x: float = 100, base_y: float = 200,
                     x_spacing: float = 300, y_spacing: float = 150) -> str:
        try:
            if not os.path.exists(input_file):
                return f"❌ 输入文件不存在: {input_file}"
            
            # 读取工作流数据
            with open(input_file, 'r', encoding='utf-8') as f:
                workflow_data = json.load(f)
            
            original_size = os.path.getsize(input_file)
            changes_made = []
            
            # 修复工作流数据
            if add_positions:
                position_changes = self._fix_positions(workflow_data, base_x, base_y, x_spacing, y_spacing)
                if position_changes:
                    changes_made.append(position_changes)
            
            if add_missing_fields:
                field_changes = self._add_missing_fields(workflow_data)
                if field_changes:
                    changes_made.append(field_changes)
            
            # 保存修复后的文件
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(workflow_data, f, indent=2, ensure_ascii=False)
            
            new_size = os.path.getsize(output_file)
            
            # 生成报告
            report = [
                f"🔧 工作流修复完成",
                f"📥 输入文件: {input_file} ({original_size} 字节)",
                f"📤 输出文件: {output_file} ({new_size} 字节)",
                f"📈 大小变化: {new_size - original_size} 字节"
            ]
            
            if changes_made:
                report.append("\n✅ 完成的修复:")
                for change in changes_made:
                    report.append(f"  • {change}")
            else:
                report.append("\nℹ️ 未发现需要修复的问题")
            
            # 验证修复结果
            validation = self._validate_fix(workflow_data)
            if validation:
                report.append(f"\n📋 验证结果: {validation}")
            
            return "\n".join(report)
            
        except json.JSONDecodeError as e:
            return f"❌ JSON解析错误: {e}"
        except Exception as e:
            return f"❌ 修复过程中出错: {e}"
    
    def _fix_positions(self, workflow_data: Dict, base_x: float, base_y: float, 
                      x_spacing: float, y_spacing: float) -> str:
        """修复节点坐标"""
        if "nodes" not in workflow_data:
            return "无节点数据"
        
        nodes = workflow_data["nodes"]
        nodes_fixed = 0
        nodes_repositioned = 0
        
        for i, node in enumerate(nodes):
            # 检查是否缺少position字段
            if "position" not in node:
                # 计算新坐标
                row = i // 3  # 每行最多3个节点
                col = i % 3
                
                x = base_x + col * x_spacing
                y = base_y + row * y_spacing
                
                node["position"] = [x, y]
                nodes_fixed += 1
            
            # 检查position是否为默认值[0, 0]
            elif isinstance(node.get("position"), list) and len(node["position"]) == 2:
                if node["position"][0] == 0 and node["position"][1] == 0:
                    # 重新计算坐标
                    row = i // 3
                    col = i % 3
                    
                    x = base_x + col * x_spacing
                    y = base_y + row * y_spacing
                    
                    node["position"] = [x, y]
                    nodes_repositioned += 1
        
        if nodes_fixed > 0 or nodes_repositioned > 0:
            changes = []
            if nodes_fixed > 0:
                changes.append(f"添加坐标: {nodes_fixed}个节点")
            if nodes_repositioned > 0:
                changes.append(f"重新定位: {nodes_repositioned}个节点")
            return "坐标修复 - " + ", ".join(changes)
        
        return ""
    
    def _add_missing_fields(self, workflow_data: Dict) -> str:
        """添加缺失的必要字段"""
        changes = []
        
        # 添加ID字段
        if "id" not in workflow_data:
            workflow_data["id"] = f"workflow-{uuid.uuid4().hex[:8]}"
            changes.append("添加id")
        
        # 添加active字段
        if "active" not in workflow_data:
            workflow_data["active"] = False
            changes.append("添加active")
        
        # 添加时间戳字段
        now = datetime.utcnow().isoformat() + "Z"
        if "createdAt" not in workflow_data:
            workflow_data["createdAt"] = now
            changes.append("添加createdAt")
        
        if "updatedAt" not in workflow_data:
            workflow_data["updatedAt"] = now
            changes.append("添加updatedAt")
        
        # 添加projectId字段（如果缺失）
        if "projectId" not in workflow_data:
            workflow_data["projectId"] = "default-project"
            changes.append("添加projectId")
        
        # 确保settings字段存在
        if "settings" not in workflow_data:
            workflow_data["settings"] = {}
            changes.append("添加settings")
        
        # 确保staticData字段存在
        if "staticData" not in workflow_data:
            workflow_data["staticData"] = None
            changes.append("添加staticData")
        
        if changes:
            return "字段补充 - " + ", ".join(changes)
        
        return ""
    
    def _validate_fix(self, workflow_data: Dict) -> str:
        """验证修复结果"""
        validation_checks = []
        
        # 检查基本字段
        required_fields = ["id", "name", "active", "createdAt", "updatedAt", "settings", "staticData"]
        for field in required_fields:
            if field in workflow_data:
                validation_checks.append(f"✅ {field}")
            else:
                validation_checks.append(f"❌ {field}")
        
        # 检查节点坐标
        if "nodes" in workflow_data:
            nodes_with_position = 0
            for node in workflow_data["nodes"]:
                if "position" in node and isinstance(node["position"], list) and len(node["position"]) == 2:
                    nodes_with_position += 1
            
            total_nodes = len(workflow_data["nodes"])
            validation_checks.append(f"📊 节点坐标: {nodes_with_position}/{total_nodes}")
        
        return " | ".join(validation_checks)