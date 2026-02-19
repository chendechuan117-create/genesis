from core.base import Tool
from typing import Dict, List, Any, Optional
import json
from datetime import datetime

class PersonalExecutionPolicySystem(Tool):
    """个人执行方针系统 - 创建、跟踪、调整执行方针"""
    
    name = "personal_execution_policy_system"
    description = "创建结构化的个人执行方针，支持执行跟踪和动态调整"
    
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "record", "adjust", "view"],
                "description": "操作类型：create(创建方针)、record(记录执行)、adjust(调整方针)、view(查看)"
            },
            "policy_data": {
                "type": "object",
                "description": "方针数据（create时使用）",
                "properties": {
                    "title": {"type": "string", "description": "方针标题"},
                    "goal": {"type": "string", "description": "核心目标"},
                    "principles": {"type": "array", "items": {"type": "string"}, "description": "执行原则"},
                    "actions": {"type": "array", "items": {"type": "string"}, "description": "具体行动清单"},
                    "checkpoints": {"type": "array", "items": {"type": "string"}, "description": "检查点"},
                    "success_metrics": {"type": "object", "description": "成功指标"}
                }
            },
            "execution_record": {
                "type": "object",
                "description": "执行记录（record时使用）",
                "properties": {
                    "policy_id": {"type": "string", "description": "方针ID"},
                    "action_completed": {"type": "string", "description": "完成的行动"},
                    "result": {"type": "string", "description": "执行结果"},
                    "observations": {"type": "string", "description": "观察发现"},
                    "difficulties": {"type": "string", "description": "遇到的困难"}
                }
            },
            "adjustment_data": {
                "type": "object",
                "description": "调整数据（adjust时使用）",
                "properties": {
                    "policy_id": {"type": "string", "description": "方针ID"},
                    "adjustment_type": {"type": "string", "enum": ["add", "remove", "modify"], "description": "调整类型"},
                    "target": {"type": "string", "description": "调整目标（如principles/actions/checkpoints）"},
                    "content": {"type": "string", "description": "调整内容"}
                }
            },
            "policy_id": {
                "type": "string",
                "description": "方针ID（record/adjust/view时使用）"
            }
        },
        "required": ["action"]
    }
    
    def execute(self, **kwargs):
        action = kwargs.get("action")
        
        if action == "create":
            return self._create_policy(kwargs.get("policy_data"))
        elif action == "record":
            return self._record_execution(kwargs.get("execution_record"))
        elif action == "adjust":
            return self._adjust_policy(kwargs.get("adjustment_data"))
        elif action == "view":
            return self._view_policy(kwargs.get("policy_id"))
        else:
            return {"error": f"未知操作: {action}"}
    
    def _create_policy(self, policy_data: Dict[str, Any]) -> Dict[str, Any]:
        """创建新的执行方针"""
        if not policy_data:
            return {"error": "缺少方针数据"}
        
        # 生成唯一ID
        policy_id = f"policy_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 构建完整方针
        policy = {
            "id": policy_id,
            "created_at": datetime.now().isoformat(),
            "title": policy_data.get("title", "未命名方针"),
            "goal": policy_data.get("goal", ""),
            "principles": policy_data.get("principles", []),
            "actions": policy_data.get("actions", []),
            "checkpoints": policy_data.get("checkpoints", []),
            "success_metrics": policy_data.get("success_metrics", {}),
            "execution_history": [],
            "adjustment_history": [],
            "status": "active"
        }
        
        # 保存到文件
        file_path = f"/tmp/{policy_id}.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(policy, f, ensure_ascii=False, indent=2)
        
        return {
            "success": True,
            "policy_id": policy_id,
            "message": f"方针创建成功: {policy['title']}",
            "file_path": file_path,
            "policy_summary": {
                "title": policy["title"],
                "goal": policy["goal"],
                "principles_count": len(policy["principles"]),
                "actions_count": len(policy["actions"]),
                "checkpoints_count": len(policy["checkpoints"])
            }
        }
    
    def _record_execution(self, record_data: Dict[str, Any]) -> Dict[str, Any]:
        """记录执行情况"""
        if not record_data:
            return {"error": "缺少执行记录数据"}
        
        policy_id = record_data.get("policy_id")
        if not policy_id:
            return {"error": "缺少方针ID"}
        
        file_path = f"/tmp/{policy_id}.json"
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                policy = json.load(f)
        except FileNotFoundError:
            return {"error": f"方针文件不存在: {policy_id}"}
        
        # 创建执行记录
        execution_record = {
            "timestamp": datetime.now().isoformat(),
            "action_completed": record_data.get("action_completed", ""),
            "result": record_data.get("result", ""),
            "observations": record_data.get("observations", ""),
            "difficulties": record_data.get("difficulties", "")
        }
        
        # 添加到历史
        policy["execution_history"].append(execution_record)
        
        # 更新文件
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(policy, f, ensure_ascii=False, indent=2)
        
        return {
            "success": True,
            "message": "执行记录已保存",
            "record": execution_record,
            "total_records": len(policy["execution_history"])
        }
    
    def _adjust_policy(self, adjustment_data: Dict[str, Any]) -> Dict[str, Any]:
        """调整执行方针"""
        if not adjustment_data:
            return {"error": "缺少调整数据"}
        
        policy_id = adjustment_data.get("policy_id")
        if not policy_id:
            return {"error": "缺少方针ID"}
        
        file_path = f"/tmp/{policy_id}.json"
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                policy = json.load(f)
        except FileNotFoundError:
            return {"error": f"方针文件不存在: {policy_id}"}
        
        adjustment_type = adjustment_data.get("adjustment_type")
        target = adjustment_data.get("target")
        content = adjustment_data.get("content")
        
        # 执行调整
        adjustment_record = {
            "timestamp": datetime.now().isoformat(),
            "type": adjustment_type,
            "target": target,
            "content": content,
            "before": None
        }
        
        if target in ["principles", "actions", "checkpoints"]:
            # 记录调整前状态
            adjustment_record["before"] = policy[target].copy()
            
            if adjustment_type == "add":
                policy[target].append(content)
            elif adjustment_type == "remove":
                if content in policy[target]:
                    policy[target].remove(content)
            elif adjustment_type == "modify":
                # 这里简化处理，实际可能需要更复杂的逻辑
                pass
        
        # 添加到调整历史
        policy["adjustment_history"].append(adjustment_record)
        
        # 更新文件
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(policy, f, ensure_ascii=False, indent=2)
        
        return {
            "success": True,
            "message": f"方针已调整: {adjustment_type} {target}",
            "adjustment": adjustment_record
        }
    
    def _view_policy(self, policy_id: str) -> Dict[str, Any]:
        """查看方针详情"""
        if not policy_id:
            return {"error": "缺少方针ID"}
        
        file_path = f"/tmp/{policy_id}.json"
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                policy = json.load(f)
        except FileNotFoundError:
            return {"error": f"方针文件不存在: {policy_id}"}
        
        # 计算执行统计
        total_executions = len(policy.get("execution_history", []))
        total_adjustments = len(policy.get("adjustment_history", []))
        
        return {
            "policy": policy,
            "statistics": {
                "total_executions": total_executions,
                "total_adjustments": total_adjustments,
                "last_execution": policy["execution_history"][-1]["timestamp"] if policy["execution_history"] else None,
                "last_adjustment": policy["adjustment_history"][-1]["timestamp"] if policy["adjustment_history"] else None
            }
        }