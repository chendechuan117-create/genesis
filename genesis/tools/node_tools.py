import logging
import json
from typing import Dict, Any, List
from genesis.core.base import Tool
from genesis.v4.manager import NodeVault, METADATA_SIGNATURE_FIELDS

logger = logging.getLogger(__name__)

# 5 个写入类 Tool 共享的可选信任字段 Schema
TRUST_SCHEMA_PROPERTIES = {
    "metadata_signature": {
        "type": "object",
        "description": "可选的环境/任务签名，例如 os_family, language, framework, runtime, error_kind, task_kind。",
        "properties": {field: {"type": "string", "description": f"{field} 签名"} for field in METADATA_SIGNATURE_FIELDS}
    },
    "confidence_score": {"type": "number", "description": "可选。0-1 之间的弱可信度评分。仅在你有明确把握时填写。"},
    "last_verified_at": {"type": "string", "description": "可选。最近验证时间，建议 ISO 或 'YYYY-MM-DD HH:MM:SS'。"},
    "verification_source": {"type": "string", "description": "可选。验证依据来源，如 command_output, manual_check, reflection。"}
}


class BaseNodeTool(Tool):
    """所有节点管理工具的公共基类，统一 vault 初始化。"""
    def __init__(self):
        self.vault = NodeVault()


class SearchKnowledgeNodesTool(BaseNodeTool):
    """节点管理工具：全局搜索。前后台均有权限使用。"""

    @property
    def name(self) -> str:
        return "search_knowledge_nodes"

    @property
    def description(self) -> str:
        return "在整个认知元信息库中搜索已有经验、环境、资产、轨迹和图谱节点（支持关键词查询）。"

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
                    "enum": ["ALL", "CONTEXT", "LESSON", "ASSET", "EPISODE", "TOOL", "ENTITY", "EVENT", "ACTION"],
                    "description": "要筛选的节点类型，默认为 'ALL'"
                },
                "signature": {
                    "type": "object",
                    "description": "可选的环境/任务签名过滤条件。只填写你确定的字段，如 os_family, language, framework, runtime, error_kind, task_kind。",
                    "properties": {field: {"type": "string", "description": f"{field} 过滤条件"} for field in METADATA_SIGNATURE_FIELDS}
                }
            },
            "required": ["keywords"]
        }

    def _active_bucket(self, node: Dict[str, Any]) -> str:
        ntype = (node.get("type") or "").upper()
        if ntype in ["ASSET", "LESSON", "CONTEXT"]:
            return "recommended"
        if ntype == "EPISODE":
            return "conditional"
        return "support"

    def _active_reason(self, node: Dict[str, Any]) -> str:
        ntype = (node.get("type") or "").upper()
        if ntype == "ASSET":
            return "可直接复用给 Op 的产物"
        if ntype == "LESSON":
            return "可直接指导 Op 的方法或原则"
        if ntype == "CONTEXT":
            return "执行前应挂载的环境约束"
        if ntype == "EPISODE":
            return "仅在延续当前任务轨迹时再挂载"
        if ntype in ["ACTION", "EVENT", "ENTITY"]:
            return "更适合作为因果背景或图谱补充"
        return "作为背景参考"

    def _type_rank(self, node: Dict[str, Any]) -> int:
        ntype = (node.get("type") or "").upper()
        ranks = {
            "ASSET": 0,
            "LESSON": 1,
            "CONTEXT": 2,
            "EPISODE": 3,
            "ACTION": 4,
            "EVENT": 5,
            "ENTITY": 6,
            "TOOL": 7,
        }
        return ranks.get(ntype, 99)

    def _signature_values(self, signature: Dict[str, Any], key: str) -> List[str]:
        value = (signature or {}).get(key)
        if not value:
            return []
        return value if isinstance(value, list) else [value]

    def _signature_gate(self, node_signature: Dict[str, Any], query_signature: Dict[str, Any]) -> bool:
        if not query_signature:
            return True
        hard_keys = ["os_family", "runtime", "language", "framework", "environment_scope"]
        for key in hard_keys:
            query_values = set(self._signature_values(query_signature, key))
            node_values = set(self._signature_values(node_signature, key))
            if query_values and node_values and not (query_values & node_values):
                return False
        return True

    def _signature_score(self, node_signature: Dict[str, Any], query_signature: Dict[str, Any]) -> int:
        if not query_signature:
            return 0
        score = 0
        hard_keys = ["os_family", "runtime", "language", "framework", "environment_scope"]
        soft_keys = ["task_kind", "target_kind", "error_kind", "validation_status"]
        for key in hard_keys:
            query_values = set(self._signature_values(query_signature, key))
            if not query_values:
                continue
            node_values = set(self._signature_values(node_signature, key))
            if node_values & query_values:
                score += 4
            elif not node_values:
                score -= 1
        for key in soft_keys:
            query_values = set(self._signature_values(query_signature, key))
            if not query_values:
                continue
            node_values = set(self._signature_values(node_signature, key))
            if node_values & query_values:
                score += 2
        return score

    async def execute(self, keywords: List[str], ntype: str = "ALL", signature: Dict[str, Any] = None) -> str:
        try:
            normalized_signature = self.vault.normalize_metadata_signature(signature)
            semantic_ids = []
            if self.vault.vector_engine.is_ready and keywords:
                query_str = " ".join(keywords)
                results = self.vault.vector_engine.search(query_str, top_k=5, threshold=0.55)
                semantic_ids = [r[0] for r in results]

            conn = self.vault._conn
            with conn:
                query = "SELECT node_id, type, title, tags, prerequisites, resolves, metadata_signature, usage_count, confidence_score, last_verified_at, verification_source, updated_at FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV%'"
                params = []

                if ntype != "ALL":
                    query += " AND type = ?"
                    params.append(ntype)

                if keywords or semantic_ids:
                    conditions = []
                    
                    # 传统的字面量匹配 (LIKE)
                    if keywords:
                        keyword_conditions = []
                        for kw in keywords:
                            keyword_conditions.append("(title LIKE ? OR tags LIKE ? OR node_id LIKE ? OR resolves LIKE ?)")
                            kw_like = f"%{kw}%"
                            params.extend([kw_like, kw_like, kw_like, kw_like])
                        if keyword_conditions:
                            conditions.append("(" + " OR ".join(keyword_conditions) + ")")
                    
                    # 降维式的语义向量匹配 (Vector Similarity)
                    if semantic_ids:
                        placeholders = ','.join('?' * len(semantic_ids))
                        conditions.append(f"node_id IN ({placeholders})")
                        params.extend(semantic_ids)

                    if conditions:
                        query += " AND (" + " OR ".join(conditions) + ")"

                query += " ORDER BY usage_count DESC LIMIT ?"
                params.append(40 if normalized_signature else 15)
                rows = conn.execute(query, tuple(params)).fetchall()

                if not rows:
                    return f"⚠️ [未命中] 未找到与 {keywords} 相关的 {ntype} 节点（字面+语义均无匹配）。当前处于未知区域，请基于通用能力处理。"

                # Reranker 精排：用 Cross-Encoder 按相关度重新排序
                query_str = " ".join(keywords) if keywords else ""
                row_dicts = [dict(r) for r in rows]
                if normalized_signature:
                    row_dicts = [r for r in row_dicts if self._signature_gate(self.vault.parse_metadata_signature(r.get('metadata_signature')), normalized_signature)]
                    if not row_dicts:
                        sig_text = self.vault.render_metadata_signature(normalized_signature)
                        return f"⚠️ [签名过滤后未命中] 未找到同时满足关键词 {keywords} 与签名 {sig_text} 的 {ntype} 节点。建议放宽部分硬环境约束后重试。"
                row_dicts = self.vault.vector_engine.rerank(query_str, row_dicts)
                for row in row_dicts:
                    parsed_signature = self.vault.parse_metadata_signature(row.get('metadata_signature'))
                    row['signature_text'] = self.vault.render_metadata_signature(parsed_signature)
                    row['signature_match_score'] = self._signature_score(parsed_signature, normalized_signature)
                    closure_signature = self.vault.expand_signature_from_node_ids([row['node_id']])
                    row['signature_closure_text'] = self.vault.render_metadata_signature(closure_signature)
                    row['reliability'] = self.vault.build_reliability_profile(row)
                row_dicts.sort(
                    key=lambda r: (
                        r.get('signature_match_score', 0),
                        (r.get('reliability') or {}).get('trust_score', 0.0),
                        r.get('rerank_score', 0.0) or 0.0,
                        r.get('usage_count', 0) or 0
                    ),
                    reverse=True
                )
                
                # === Graph Walk (V4.3 Experience Graph) ===
                # 顺藤摸瓜：基于图谱关系扩展上下文
                graph_context = {}
                graph_related_ids = {}
                
                for r in row_dicts:
                    nid = r['node_id']
                    
                    outgoing = self.vault.get_related_nodes(nid, direction="out")
                    for neighbor in outgoing:
                        rel = neighbor['relation']
                        target_str = f"--> [{rel}] --> <{neighbor['type']}> {neighbor['title']} ({neighbor['node_id']})"
                        if nid not in graph_context: graph_context[nid] = []
                        graph_context[nid].append(target_str)
                        if nid not in graph_related_ids:
                            graph_related_ids[nid] = []
                        if neighbor['node_id'] not in graph_related_ids[nid]:
                            graph_related_ids[nid].append(neighbor['node_id'])
                        
                    incoming = self.vault.get_related_nodes(nid, direction="in")
                    for neighbor in incoming:
                        rel = neighbor['relation']
                        source_str = f"<-- [{rel}] -- <{neighbor['type']}> {neighbor['title']} ({neighbor['node_id']})"
                        if nid not in graph_context: graph_context[nid] = []
                        graph_context[nid].append(source_str)
                        if nid not in graph_related_ids:
                            graph_related_ids[nid] = []
                        if neighbor['node_id'] not in graph_related_ids[nid]:
                            graph_related_ids[nid].append(neighbor['node_id'])

                all_prereq_ids = set()
                for r in row_dicts:
                    if r.get('prerequisites'):
                        for pid in r['prerequisites'].split(','):
                            all_prereq_ids.add(pid.strip())
                
                prereq_nodes = []
                if all_prereq_ids:
                    placeholders = ','.join('?' * len(all_prereq_ids))
                    prereq_query = f"SELECT node_id, type, title, tags FROM knowledge_nodes WHERE node_id IN ({placeholders})"
                    prereq_nodes = conn.execute(prereq_query, tuple(all_prereq_ids)).fetchall()

                recommended_rows = []
                support_rows = []
                for row in row_dicts:
                    bucket = self._active_bucket(row)
                    if bucket in ["recommended", "conditional"]:
                        recommended_rows.append(row)
                    else:
                        support_rows.append(row)

                recommended_rows.sort(
                    key=lambda r: (
                        0 if self._active_bucket(r) == "recommended" else 1,
                        self._type_rank(r),
                        -((r.get('reliability') or {}).get('trust_score', 0.0)),
                        -(r.get('rerank_score', 0.0) or 0.0),
                        -(r.get('usage_count', 0) or 0)
                    )
                )
                support_rows.sort(
                    key=lambda r: (
                        self._type_rank(r),
                        -((r.get('reliability') or {}).get('trust_score', 0.0)),
                        -(r.get('rerank_score', 0.0) or 0.0),
                        -(r.get('usage_count', 0) or 0)
                    )
                )

                lines = [f"🔍 [知识库智能双向搜索] 查询词: {keywords}"]
                if normalized_signature:
                    lines.append(f"SIGNATURE_FILTER: {self.vault.render_metadata_signature(normalized_signature)}")
                lines.append("RECOMMENDED_ACTIVE_NODES:")
                if recommended_rows:
                    for r in recommended_rows[:6]:
                        nid = r['node_id']
                        reason = self._active_reason(r)
                        extras = []
                        if r.get('prerequisites'):
                            extras.append(f"reqs:{r.get('prerequisites')}")
                        if graph_related_ids.get(nid):
                            extras.append(f"graph:+{', '.join(graph_related_ids[nid][:2])}")
                        if normalized_signature:
                            extras.append(f"sig_score:{r.get('signature_match_score', 0)}")
                        if r.get('signature_closure_text'):
                            extras.append(f"sig:+{r.get('signature_closure_text')}")
                        reliability = r.get('reliability') or {}
                        if reliability.get('validation_status'):
                            extras.append(f"verify:{reliability.get('validation_status')}")
                        extras.append(f"trust:{reliability.get('trust_score', 0):.1f}")
                        extras.append(f"fresh:{reliability.get('freshness_label', 'unknown')}")
                        extra_str = f" | {' | '.join(extras)}" if extras else ""
                        conditional_flag = " [按需挂载]" if self._active_bucket(r) == "conditional" else ""
                        lines.append(f"- [{nid}] <{r['type']}> {r['title']}{conditional_flag} | why:{reason}{extra_str}")
                else:
                    lines.append("- NONE")

                lines.append("SUPPORTING_REFERENCE_NODES:")
                if support_rows:
                    for r in support_rows[:6]:
                        nid = r['node_id']
                        reason = self._active_reason(r)
                        lines.append(f"- [{nid}] <{r['type']}> {r['title']} | why:{reason}")
                else:
                    lines.append("- NONE")

                lines.append("MATCH_DETAILS:")
                for r in row_dicts:
                    nid = r['node_id']
                    source_label = "[语义]" if r['node_id'] in semantic_ids else "[字面]"
                    reqs = f" | reqs:[{r.get('prerequisites', '')}]" if r.get('prerequisites') else ""
                    res = f" | resolves:[{r.get('resolves', '')}]" if r.get('resolves') else ""
                    sig = f" | sig:{r.get('signature_text', '')}" if r.get('signature_text') else ""
                    sig_score = f" | sig_score:{r.get('signature_match_score', 0)}" if normalized_signature else ""
                    reliability = r.get('reliability') or {}
                    trust = f" | trust:{reliability.get('trust_score', 0):.1f}" if reliability else ""
                    conf = f" | conf:{reliability.get('confidence_score', 0):.2f}" if reliability else ""
                    fresh = f" | fresh:{reliability.get('freshness_label', 'unknown')}" if reliability else ""
                    verify = f" | verify:{reliability.get('validation_status')}" if reliability.get('validation_status') else ""
                    score_label = f" (相关度:{r['rerank_score']:.2f})" if 'rerank_score' in r else ""
                    
                    lines.append(f"{source_label} <{r['type']}> [{nid}] {r['title']} | tags:{r.get('tags', '')}{reqs}{res}{sig}{sig_score}{trust}{conf}{fresh}{verify}{score_label}")
                    
                    if nid in graph_context:
                        for rel_line in graph_context[nid]:
                            lines.append(f"      {rel_line}")
                
                if prereq_nodes:
                    lines.append("\nPREREQUISITE_HINTS:")
                    for pr in prereq_nodes:
                        lines.append(f"- <{pr['type']}> [{pr['node_id']}] {pr['title']} | tags:{pr['tags']}")

                lines.append("\nSIGNATURE_CLOSURE_HINTS:")
                closure_rows = [r for r in recommended_rows[:6] if r.get('signature_closure_text')]
                if closure_rows:
                    for r in closure_rows:
                        lines.append(f"- [{r['node_id']}] min_sig:{r['signature_closure_text']}")
                else:
                    lines.append("- NONE")
                
                lines.append("\nACTIVE_NODE_SELECTION_HINT:")
                lines.append("- 优先挂 ASSET / LESSON / CONTEXT。")
                lines.append("- EPISODE 仅在你需要延续同一任务脉络时再挂。")
                lines.append("- ENTITY / EVENT / ACTION 通常作为背景参考；只有在因果链本身重要时再挂。")
                lines.append("- 如果某节点带有 reqs 或 graph:+ 提示，派发给 Op 时优先把相关依赖也一起考虑进 active_nodes。")
                return "\n".join(lines)
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return f"Error: {e}"


class RecordContextNodeTool(BaseNodeTool):
    """节点管理工具：记录环境与状态变量节点。专属后台 C 进程权限。"""

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
                "state_description": {"type": "string", "description": "纯文本的状态说明或变量值"},
                **TRUST_SCHEMA_PROPERTIES
            },
            "required": ["node_id", "title", "state_description"]
        }

    async def execute(self, node_id: str, title: str, state_description: str, metadata_signature: Dict[str, Any] = None, confidence_score: float = None, last_verified_at: str = None, verification_source: str = None) -> str:
        try:
            self.vault.create_node(
                node_id=node_id,
                ntype="CONTEXT",
                title=title,
                human_translation=title,
                tags="auto_managed",
                full_content=state_description,
                source="reflection",
                metadata_signature=metadata_signature,
                confidence_score=confidence_score,
                last_verified_at=last_verified_at,
                verification_source=verification_source
            )
            return f"✅ CONTEXT节点 [{node_id}] '{title}' 写入/覆盖成功。"
        except Exception as e:
            logger.error(f"Context node creation failed: {e}")
            return f"Error: {e}"


class RecordLessonNodeTool(BaseNodeTool):
    """节点管理工具：记录经验与执行流节点。专属后台 C 进程权限。"""

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
                "because_reason": {"type": "string", "description": "底层原因说明，解释为何这么做，防止Op幻觉猜忌"},
                "prerequisites": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "执行此操作强制依赖的前置节点ID数组（通常是 CTX_ 节点）。如果无依赖留空数组。"
                },
                "resolves": {"type": "string", "description": "此经验主要解决的具体报错信息或异常现象简述（用于丰富图谱寻找）"},
                **TRUST_SCHEMA_PROPERTIES
            },
            "required": ["node_id", "title", "trigger_verb", "trigger_noun", "trigger_context", "action_steps", "because_reason", "resolves"]
        }

    async def execute(self, node_id: str, title: str, trigger_verb: str, trigger_noun: str, trigger_context: str, action_steps: List[str], because_reason: str, prerequisites: List[str] = None, resolves: str = None, metadata_signature: Dict[str, Any] = None, confidence_score: float = None, last_verified_at: str = None, verification_source: str = None) -> str:
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

            prereq_str = ",".join(prerequisites) if prerequisites else None
            
            self.vault.create_node(
                node_id=node_id,
                ntype="LESSON",
                title=title,
                human_translation=title,
                tags="auto_managed",
                full_content=content,
                source="reflection",
                prerequisites=prereq_str,
                resolves=resolves,
                metadata_signature=metadata_signature,
                confidence_score=confidence_score,
                last_verified_at=last_verified_at,
                verification_source=verification_source
            )
            return f"✅ LESSON节点 [{node_id}] '{title}' 写入/覆盖成功。带有了关联图谱。"
        except Exception as e:
            logger.error(f"Lesson node creation failed: {e}")
            return f"Error: {e}"


class CreateMetaNodeTool(BaseNodeTool):

    @property
    def name(self) -> str:
        return "create_meta_node"

    @property
    def description(self) -> str:
        return "创建元信息节点 (ASSET/EPISODE)。用于记录可复用产物或阶段性任务轨迹。(仅超级管理员 C 进程 有权限使用)"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "节点ID，如 ASSET_DEPLOY_SCRIPT 或 EP_TASK_DEBUG_ROUND1"},
                "ntype": {"type": "string", "enum": ["ASSET", "EPISODE"], "description": "节点类型"},
                "title": {"type": "string", "description": "节点标题"},
                "content": {"type": "string", "description": "节点完整内容"},
                "tags": {"type": "string", "description": "逗号分隔标签"},
                "resolves": {"type": "string", "description": "该资产或轨迹主要对应的问题、任务或现象", "default": ""},
                **TRUST_SCHEMA_PROPERTIES
            },
            "required": ["node_id", "ntype", "title", "content"]
        }

    async def execute(self, node_id: str, ntype: str, title: str, content: str, tags: str = "", resolves: str = "", metadata_signature: Dict[str, Any] = None, confidence_score: float = None, last_verified_at: str = None, verification_source: str = None) -> str:
        try:
            self.vault.create_node(
                node_id=node_id,
                ntype=ntype,
                title=title,
                human_translation=title,
                tags=tags,
                full_content=content,
                source="reflection_meta",
                resolves=resolves or None,
                metadata_signature=metadata_signature,
                confidence_score=confidence_score,
                last_verified_at=last_verified_at,
                verification_source=verification_source
            )
            return f"✅ {ntype}节点 [{node_id}] 创建成功。"
        except Exception as e:
            logger.error(f"Meta node creation failed: {e}")
            return f"Error: {e}"


class DeleteNodeTool(BaseNodeTool):
    """节点管理工具：删除知识节点。专属后台 C 进程权限。"""

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
            # 先删边 (Graph Edges)
            self.vault._conn.execute("DELETE FROM node_edges WHERE source_id = ? OR target_id = ?", (node_id, node_id))
            # 再删内容 (Content)
            self.vault._conn.execute("DELETE FROM node_contents WHERE node_id = ?", (node_id,))
            # 最后删节点 (Index)
            self.vault._conn.execute("DELETE FROM knowledge_nodes WHERE node_id = ?", (node_id,))
            self.vault._conn.commit()
            logger.info(f"NodeVault: Deleted node [{node_id}] and its edges")
            return f"✅ 节点 [{node_id}] 及其关联边已删除。"
        except Exception as e:
            logger.error(f"Node deletion failed: {e}")
            return f"Error: {e}"


class CreateGraphNodeTool(BaseNodeTool):
    """节点管理工具：创建图谱原子节点 (Entity/Event/Action)。专属后台 C 进程权限。"""

    @property
    def name(self) -> str:
        return "create_graph_node"

    @property
    def description(self) -> str:
        return "创建图谱中的原子节点 (ENTITY/EVENT/ACTION)。(仅超级管理员 C 进程 有权限使用)"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "节点ID，格式前缀必须是 ENT_ / EVT_ / ACT_"},
                "ntype": {"type": "string", "enum": ["ENTITY", "EVENT", "ACTION"], "description": "节点类型"},
                "title": {"type": "string", "description": "节点标题/名称"},
                "content": {"type": "string", "description": "节点的详细内容或描述"},
                "tags": {"type": "string", "description": "逗号分隔的标签"},
                **TRUST_SCHEMA_PROPERTIES
            },
            "required": ["node_id", "ntype", "title", "content"]
        }

    async def execute(self, node_id: str, ntype: str, title: str, content: str, tags: str = "", metadata_signature: Dict[str, Any] = None, confidence_score: float = None, last_verified_at: str = None, verification_source: str = None) -> str:
        try:
            self.vault.create_node(
                node_id=node_id,
                ntype=ntype,
                title=title,
                human_translation=title,
                tags=tags,
                full_content=content,
                source="reflection_graph",
                metadata_signature=metadata_signature,
                confidence_score=confidence_score,
                last_verified_at=last_verified_at,
                verification_source=verification_source
            )
            return f"✅ {ntype}节点 [{node_id}] 创建成功。"
        except Exception as e:
            logger.error(f"Graph node creation failed: {e}")
            return f"Error: {e}"


class CreateNodeEdgeTool(BaseNodeTool):
    """节点管理工具：创建节点间的关联边。专属后台 C 进程权限。"""

    @property
    def name(self) -> str:
        return "create_node_edge"

    @property
    def description(self) -> str:
        return "创建两个节点之间的有向边。(仅超级管理员 C 进程 有权限使用)"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "source_id": {"type": "string", "description": "源节点ID"},
                "target_id": {"type": "string", "description": "目标节点ID"},
                "relation": {
                    "type": "string", 
                    "enum": ["TRIGGERS", "RESOLVES", "REQUIRES", "LOCATED_AT", "RELATED_TO"],
                    "description": "关系类型"
                },
                "weight": {"type": "number", "description": "权重 (0.0-1.0)", "default": 1.0}
            },
            "required": ["source_id", "target_id", "relation"]
        }

    async def execute(self, source_id: str, target_id: str, relation: str, weight: float = 1.0) -> str:
        try:
            self.vault.add_edge(source_id, target_id, relation, weight)
            return f"✅ 边建立: {source_id} --[{relation}]--> {target_id}"
        except Exception as e:
            logger.error(f"Edge creation failed: {e}")
            return f"Error: {e}"
