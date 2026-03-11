import logging
import sqlite3
import json
from typing import Dict, Any, List
from genesis.core.base import Tool
from genesis.v4.manager import NodeVault
import jsonschema

logger = logging.getLogger(__name__)

class SearchKnowledgeNodesTool(Tool):
    """节点管理工具：全局搜索。前后台均有权限使用。"""
    
    def __init__(self):
        self.vault = NodeVault()

    @property
    def name(self) -> str:
        return "search_knowledge_nodes"

    @property
    def description(self) -> str:
        return "在整个认知元信息库中搜索已有经验、工具和概念节点（支持关键词查询）。"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "搜索关键词列表，如 ['n8n', 'jwt']。支持中文。为空将拉取最新活跃节点。"
                },
                "ntype": {
                    "type": "string", 
                    "enum": ["ALL", "CONTEXT", "LESSON", "TOOL"],
                    "description": "要筛选的节点类型，默认为 'ALL'"
                }
            },
            "required": ["keywords"]
        }

    async def execute(self, keywords: List[str], ntype: str = "ALL") -> str:
        try:
            with sqlite3.connect(str(self.vault.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                query = "SELECT node_id, type, title, tags FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV%'"
                params = []

                if ntype != "ALL":
                    query += " AND type = ?"
                    params.append(ntype)

                if keywords:
                    keyword_conditions = []
                    for kw in keywords:
                        keyword_conditions.append("(title LIKE ? OR tags LIKE ? OR node_id LIKE ?)")
                        kw_like = f"%{kw}%"
                        params.extend([kw_like, kw_like, kw_like])
                    if keyword_conditions:
                        query += " AND (" + " OR ".join(keyword_conditions) + ")"

                query += " ORDER BY usage_count DESC LIMIT 15"
                
                rows = conn.execute(query, tuple(params)).fetchall()

                if not rows:
                    return f"❌ 知识库中未找到与 {keywords} 相关的 {ntype} 节点。请尝试其他关键词或直接凭借直觉回答/创建新节点。"

                lines = [f"🔍 [知识库搜索结果] 匹配关键词: {keywords}"]
                for r in rows:
                    lines.append(f"<{r['type']}> [{r['node_id']}] {r['title']} | tags:{r['tags']}")
                
                lines.append("\n(如需查看某个节点的完整内容，请在生成蓝图时将其加入 active_nodes，或直接开始执行时阅读它。)")
                return "\n".join(lines)
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return f"Error: {e}"


class RecordContextNodeTool(Tool):
    """节点管理工具：记录环境与状态变量节点。专属后台 C 进程权限。"""
    
    def __init__(self):
        self.vault = NodeVault()

    @property
    def name(self) -> str:
        return "record_context_node"

    @property
    def description(self) -> str:
        return "沉淀静态参数类节点 (CONTEXT)，用于记录纯粹的 Key-Value 状态变量或环境信息。(仅超级管理员 C 进程 有权限使用)"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "必须以 CTX_ 开头，大写字母和下划线组成，如 CTX_N8N_API"},
                "title": {"type": "string", "description": "一句话标题，如 'n8n API认证方式'"},
                "state_description": {"type": "string", "description": "纯文本的状态说明或变量值"}
            },
            "required": ["node_id", "title", "state_description"]
        }

    async def execute(self, node_id: str, title: str, state_description: str) -> str:
        try:
            self.vault.create_node(
                node_id=node_id,
                ntype="CONTEXT",
                title=title,
                human_translation=title,
                tags="auto_managed",
                full_content=state_description,
                source="reflection"
            )
            return f"✅ CONTEXT节点 [{node_id}] '{title}' 写入/覆盖成功。"
        except Exception as e:
            logger.error(f"Context node creation failed: {e}")
            return f"Error: {e}"


class RecordLessonNodeTool(Tool):
    """节点管理工具：记录经验与执行流节点。专属后台 C 进程权限。"""
    
    def __init__(self):
        self.vault = NodeVault()

    @property
    def name(self) -> str:
        return "record_lesson_node"

    @property
    def description(self) -> str:
        return "沉淀经验流程类节点 (LESSON)，用于记录具体的排错手段或操作流。(仅超级管理员 C 进程 有权限使用)"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "必须以 LESSON_ 开头，大写字母和下划线组成，如 LESSON_DEPLOY"},
                "title": {"type": "string", "description": "一句话标题，如 'Nginx 端口占用解决流'"},
                "trigger_verb": {"type": "string", "description": "触发此动作的动词，如 debug, install"},
                "trigger_noun": {"type": "string", "description": "针对的目标名词，如 nginx, docker"},
                "trigger_context": {"type": "string", "description": "问题触发的环境或上下文，如 startup_failed"},
                "action_steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "具体的执行步骤数组，也就是破局点操作"
                },
                "because_reason": {"type": "string", "description": "底层原因说明，解释为何这么做，防止Op幻觉猜忌"}
            },
            "required": ["node_id", "title", "trigger_verb", "trigger_noun", "trigger_context", "action_steps", "because_reason"]
        }

    async def execute(self, node_id: str, title: str, trigger_verb: str, trigger_noun: str, trigger_context: str, action_steps: List[str], because_reason: str) -> str:
        try:
            # 在 Python 层优雅地组装为 JSON 存储给 Op 读取
            lesson_struct = {
                "IF_trigger": {
                    "verb": trigger_verb,
                    "noun": trigger_noun,
                    "context": trigger_context
                },
                "THEN_action": action_steps,
                "BECAUSE_reason": because_reason
            }
            content = json.dumps(lesson_struct, ensure_ascii=False, indent=2)

            self.vault.create_node(
                node_id=node_id,
                ntype="LESSON",
                title=title,
                human_translation=title,
                tags="auto_managed",
                full_content=content,
                source="reflection"
            )
            return f"✅ LESSON节点 [{node_id}] '{title}' 写入/覆盖成功。"
        except Exception as e:
            logger.error(f"Lesson node creation failed: {e}")
            return f"Error: {e}"


class DeleteNodeTool(Tool):
    """节点管理工具：删除知识节点。专属后台 C 进程权限。"""
    
    def __init__(self):
        self.vault = NodeVault()

    @property
    def name(self) -> str:
        return "delete_node"

    @property
    def description(self) -> str:
        return "删除错误或过时的节点。(仅超级管理员 C 进程 有权限使用此工具)"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "目标节点的 node_id"}
            },
            "required": ["node_id"]
        }

    async def execute(self, node_id: str) -> str:
        try:
            with sqlite3.connect(str(self.vault.db_path)) as conn:
                conn.execute("DELETE FROM knowledge_nodes WHERE node_id = ?", (node_id,))
                conn.execute("DELETE FROM node_contents WHERE node_id = ?", (node_id,))
                conn.commit()
            logger.info(f"NodeVault: Deleted node [{node_id}]")
            return f"✅ 节点 [{node_id}] 删除成功。"
        except Exception as e:
            logger.error(f"Node deletion failed: {e}")
            return f"Error: {e}"
