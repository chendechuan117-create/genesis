import logging
import json
from typing import Dict, Any, List
from genesis.v4.manager import NodeVault, TRUST_TIERS
from genesis.tools._base import BaseNodeTool, TRUST_SCHEMA_PROPERTIES  # noqa: F401

logger = logging.getLogger(__name__)



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

    async def execute(self, node_id: str, title: str, state_description: str, metadata_signature: Dict[str, Any] = None, last_verified_at: str = None, verification_source: str = None) -> str:
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
                last_verified_at=last_verified_at,
                verification_source=verification_source,
                trust_tier="REFLECTION"
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
                "contradicts": {"type": "string", "description": "可选。如果这条新知识反驳/替代了某个旧节点，填写被反驳的节点 ID。旧节点将被标记为已过时，不再出现在搜索结果中。"},
                "reasoning_basis": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "basis_node_id": {"type": "string", "description": "基于哪个已有节点产生此经验"},
                            "reasoning": {"type": "string", "description": "这条线回答一个具体的因果问题：为什么基于这个特定节点？不同basis的reasoning必须不同。例如：CONTEXT→'什么环境条件使此经验成立'，PATTERN→'这属于什么已知重复模式'，LESSON→'什么先验经验指导了这个做法'"}
                        },
                        "required": ["basis_node_id", "reasoning"]
                    },
                    "description": "推理线（必填）：每条线回答一个不同的因果问题——为什么此经验基于那个特定节点？不要写总理由复制到每条线，每条线的reasoning必须针对该basis节点回答不同的因果角度。至少2条线。"
                },
                **TRUST_SCHEMA_PROPERTIES
            },
            "required": ["node_id", "title", "trigger_verb", "trigger_noun", "trigger_context", "action_steps", "because_reason", "resolves", "reasoning_basis"]
        }

    async def execute(self, node_id: str, title: str, trigger_verb: str, trigger_noun: str, trigger_context: str, action_steps: List[str], because_reason: str, prerequisites: List[str] = None, resolves: str = None, contradicts: str = None, reasoning_basis: List[Dict[str, str]] = None, metadata_signature: Dict[str, Any] = None, last_verified_at: str = None, verification_source: str = None) -> str:
        # ── validateInput: reasoning_basis 必填校验 ──
        if not reasoning_basis:
            return "Error: reasoning_basis 不能为空。记录 LESSON 必须声明基于哪些已有节点产生此经验，且每条线的reasoning必须针对该basis节点回答不同的因果角度。请先搜索知识库，找到相关节点后填写 reasoning_basis。没有线的创新 = 无法判断价值 = 无法去重 = 噪音。"

        # ── 预处理 basis：解析对象数组，清洗去重去自引用 ──
        basis_entries = []
        seen_ids = set()
        for rb in reasoning_basis:
            if isinstance(rb, str):
                # 兼容旧格式：纯节点ID字符串
                bid = rb.strip()
                br = because_reason  # fallback
            elif isinstance(rb, dict):
                bid = (rb.get("basis_node_id") or "").strip()
                br = (rb.get("reasoning") or because_reason).strip()
            else:
                continue
            if bid and bid != node_id and bid not in seen_ids:
                seen_ids.add(bid)
                basis_entries.append({"id": bid, "reasoning": br})
        valid_basis = [e["id"] for e in basis_entries]

        # ── 同轮检测：basis 中哪些是本轮刚创建的（不贡献入线数，防自刷） ──
        same_round_ids = self.vault.get_same_round_ids(valid_basis) if valid_basis else set()

        # ── 碰撞检测（写前去重）：basis 集合与已有节点重叠 ──
        collision_candidates = self.vault.find_collision_candidates(valid_basis, min_overlap=2) if valid_basis else []
        collision_hint = ""
        if collision_candidates:
            candidate_hints = [f"[{cid}] '{ctitle}' (重叠{overlap}个basis)" for cid, overlap, ctitle in collision_candidates[:3]]
            collision_hint = f" ⚠️ 碰撞检测：你引用的节点已被以下节点引用：{', '.join(candidate_hints)}。确认是否重复？"
            logger.info(f"Collision detected for [{node_id}]: {candidate_hints}")

        try:
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

            # === 语义去重：写入前搜索相似 LESSON ===
            dedup_action = None
            merged_node_id = None
            if self.vault.vector_engine.is_ready:
                query_text = f"{title} {trigger_noun} {trigger_context} {resolves or ''}"
                similar = self.vault.vector_engine.search(query_text, top_k=3, threshold=0.75)
                # 批量获取候选节点的类型信息（公共 API，不直接访问 _conn）
                candidate_ids = [sid for sid, _ in similar if sid != node_id]
                candidate_briefs = self.vault.get_node_briefs(candidate_ids) if candidate_ids else {}
                for sim_id, sim_score in similar:
                    if sim_id == node_id:
                        continue
                    brief = candidate_briefs.get(sim_id)
                    if not brief or brief.get('type') != 'LESSON':
                        continue
                    if sim_score >= 0.85:
                        # 高度相似：合并到已有节点（含版本快照 + 向量重嵌入）
                        dedup_action = "merge"
                        merged_node_id = sim_id
                        self.vault.update_node_content(sim_id, content, source="reflection_merged")
                        self.vault.touch_node(sim_id)
                        logger.info(f"LESSON dedup: merged [{node_id}] into [{sim_id}] (sim={sim_score:.2f})")
                        break
                    elif sim_score >= 0.65:
                        # 中等相似：创建新节点但建立关联边
                        dedup_action = "relate"
                        merged_node_id = sim_id
                        break

            if dedup_action == "merge":
                return f"♻️ LESSON [{node_id}] 与已有 [{merged_node_id}] 高度相似(>0.85)，已合并更新内容并提升置信度。"

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
                last_verified_at=last_verified_at,
                verification_source=verification_source,
                trust_tier="REFLECTION"
            )

            if dedup_action == "relate" and merged_node_id:
                self.vault.add_edge(node_id, merged_node_id, "RELATED_TO", weight=0.7)

            # RESOLVES 边：此经验解决了某个问题/异常 → 强边（2-hop 深度遍历）
            resolves_msg = ""
            if resolves:
                # resolves 是文本描述，尝试匹配已有节点 ID
                resolved_ids = self._resolve_text_to_node_ids(resolves)
                for rid in resolved_ids:
                    if rid != node_id:
                        self.vault.add_edge(node_id, rid, "RESOLVES", weight=0.8)
                if resolved_ids:
                    resolves_msg = f" 🔗 RESOLVES→{resolved_ids}"

            # PREREQUISITE 边：此经验依赖的前置知识 → 强边（2-hop 深度遍历）
            prereq_msg = ""
            if prerequisites:
                for pid in prerequisites:
                    pid = pid.strip()
                    if pid and pid != node_id:
                        self.vault.add_edge(node_id, pid, "PREREQUISITE", weight=0.7)
                prereq_msg = f" 🔗 PREREQUISITE←{prerequisites}"

            # CONTRADICTS 边：标记旧节点已被新知识反驳
            contradicts_msg = ""
            if contradicts:
                target_id = contradicts.strip()
                self.vault.add_edge(node_id, target_id, "CONTRADICTS", weight=1.0)
                contradicts_msg = f" ⚠️ 已标记 [{target_id}] 为被反驳，该节点将不再出现在搜索结果中。"
                logger.info(f"CONTRADICTS: [{node_id}] --[CONTRADICTS]--> [{target_id}]")

            # ── 推理线（点线面架构）：新点连线到 basis 节点，每条线用独立的因果推理 ──
            line_msg = ""
            if basis_entries:
                for entry in basis_entries:
                    bid = entry["id"]
                    line_reasoning = entry["reasoning"]
                    sr = 1 if bid in same_round_ids else 0
                    self.vault.create_reasoning_line(node_id, bid, reasoning=line_reasoning, source="GP", same_round=sr)
                line_msg = f" 🔗 {len(basis_entries)}条推理线→{valid_basis}"

            if dedup_action == "relate" and merged_node_id:
                return f"✅ LESSON节点 [{node_id}] '{title}' 写入成功。检测到相似节点 [{merged_node_id}]，已建立 RELATED_TO 边。{resolves_msg}{prereq_msg}{contradicts_msg}{line_msg}{collision_hint}"

            return f"✅ LESSON节点 [{node_id}] '{title}' 写入成功。{resolves_msg}{prereq_msg}{contradicts_msg}{line_msg}{collision_hint}"
        except Exception as e:
            logger.error(f"Lesson node creation failed: {e}")
            return f"Error: {e}"

    def _resolve_text_to_node_ids(self, text: str, top_k: int = 3, threshold: float = 0.75) -> List[str]:
        """将 resolves 文本描述匹配到已有节点 ID（向量搜索）。
        resolves 字段是自然语言描述（如 "file not found 探测"），
        需要通过语义搜索找到对应的节点 ID 来创建边。
        """
        if not text or not self.vault.vector_engine.is_ready:
            return []
        try:
            results = self.vault.vector_engine.search(text, top_k=top_k, threshold=threshold)
            return [rid for rid, score in results if rid]
        except Exception as e:
            logger.debug(f"resolve_text_to_node_ids failed: {e}")
            return []


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

    async def execute(self, node_id: str, ntype: str, title: str, content: str, tags: str = "", resolves: str = "", metadata_signature: Dict[str, Any] = None, last_verified_at: str = None, verification_source: str = None) -> str:
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
                last_verified_at=last_verified_at,
                verification_source=verification_source,
                trust_tier="REFLECTION"
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
            success = self.vault.delete_node(node_id)
            if success:
                logger.info(f"NodeVault: Deleted node [{node_id}] and its edges")
                return f"✅ 节点 [{node_id}] 及其关联边已删除。"
            return f"Error: delete_node returned False for [{node_id}]"
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

    async def execute(self, node_id: str, ntype: str, title: str, content: str, tags: str = "", metadata_signature: Dict[str, Any] = None, last_verified_at: str = None, verification_source: str = None) -> str:
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
                last_verified_at=last_verified_at,
                verification_source=verification_source,
                trust_tier="REFLECTION"
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
                    "enum": ["TRIGGERS", "RESOLVES", "REQUIRES", "LOCATED_AT", "RELATED_TO", "CONTRADICTS"],
                    "description": "关系类型。CONTRADICTS: 矛盾（C-Gardener标记，GP搜索可见）"
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
class RecordToolNodeTool(BaseNodeTool):
    """节点管理工具：记录工具节点 (TOOL_NODE)。专属后台 C 进程权限。"""

    @property
    def name(self) -> str:
        return "record_tool_node"

    @property
    def description(self) -> str:
        return "将 Python 工具源码作为 TOOL 节点记录到认知库中。(仅超级管理员 C 进程 有权限使用)"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "节点ID，格式前缀必须是 TOOL_"},
                "tool_name": {"type": "string", "description": "工具名称（小写字母和下划线）"},
                "title": {"type": "string", "description": "工具功能描述"},
                "source_code": {"type": "string", "description": "Python 源码文本，必须包含一个继承自 Tool 的类定义"},
                "tags": {"type": "string", "description": "逗号分隔的标签，如 tool,python,skill", "default": "tool,python,skill"},
                **TRUST_SCHEMA_PROPERTIES
            },
            "required": ["node_id", "tool_name", "title", "source_code"]
        }

    async def execute(self, node_id: str, tool_name: str, title: str, source_code: str, tags: str = "tool,python,skill", metadata_signature: Dict[str, Any] = None, last_verified_at: str = None, verification_source: str = None) -> str:
        try:
            # 验证源码是否包含 Tool 类
            if "class" not in source_code or "Tool" not in source_code:
                return "Error: 源码必须包含一个继承自 Tool 的类定义"
            
            # 创建工具节点
            self.vault.create_node(
                node_id=node_id,
                ntype="TOOL",
                title=title,
                human_translation=f"Python工具: {tool_name}",
                tags=tags,
                full_content=source_code,
                source="skill_creation",
                metadata_signature=metadata_signature,
                last_verified_at=last_verified_at,
                verification_source=verification_source,
                trust_tier="REFLECTION"
            )
            
            logger.info(f"NodeVault: Recorded tool node [{node_id}] - {tool_name}")
            return f"✅ 工具节点 [{node_id}] 记录成功。工具名称: {tool_name}"
            
        except Exception as e:
            logger.error(f"Tool node recording failed: {e}")
            return f"Error: {e}"


class RecordDiscoveryTool(BaseNodeTool):
    """记录单次执行观察 (DISCOVERY)。约束极窄的录入工具，抑制 LLM 训练噪音。

    DISCOVERY 是原子级客观观察，不做因果推理。
    多次同 subject 的 DISCOVERY 由代码自动提升为 PATTERN。
    """

    @property
    def name(self) -> str:
        return "record_discovery"

    @property
    def description(self) -> str:
        return (
            "Record a single atomic observation from execution. "
            "Only record genuinely new observations — skip if trivial or already known. "
            "Use dot notation for subject (max 3 levels). Keep description under 30 tokens."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["TOOL_BEHAVIOR", "ENV_FACT", "APPROACH", "ERROR_PATTERN"],
                    "description": "TOOL_BEHAVIOR=工具行为观察, ENV_FACT=环境事实, APPROACH=方法路径, ERROR_PATTERN=错误模式"
                },
                "subject": {
                    "type": "string",
                    "description": "Dot notation topic, max 3 levels. e.g. nginx.port.conflict, python.venv.path"
                },
                "description": {
                    "type": "string",
                    "description": "Compressed observation, max 30 tokens. Use symbols: → (sequence), | (alternative), + (conjunction)"
                },
                "evidence_tool": {
                    "type": "string",
                    "description": "Which tool produced the evidence. e.g. shell, read_file"
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 5,
                    "description": "Keywords for retrieval, max 5"
                },
            },
            "required": ["category", "subject", "description", "evidence_tool"]
        }

    async def execute(self, category: str, subject: str, description: str,
                      evidence_tool: str, tags: List[str] = None) -> str:
        import hashlib
        from datetime import datetime
        try:
            # Validate category
            valid_cats = {"TOOL_BEHAVIOR", "ENV_FACT", "APPROACH", "ERROR_PATTERN"}
            if category not in valid_cats:
                return f"Error: category must be one of {valid_cats}"

            # Validate subject: dot notation, max 3 levels
            parts = subject.split(".")
            if len(parts) > 3 or not all(p.strip() for p in parts):
                return f"Error: subject must be dot notation with max 3 levels"

            # Truncate description to ~30 tokens (~150 chars)
            description = description[:150]

            # Generate node_id
            hash_input = f"{subject}:{description}"
            node_id = f"DISC_{hashlib.md5(hash_input.encode()).hexdigest()[:8].upper()}"

            # Semantic dedup: check for highly similar existing DISCOVERY
            if self.vault.vector_engine.is_ready:
                query_text = f"{subject} {description}"
                similar = self.vault.vector_engine.search(query_text, top_k=3, threshold=0.75)
                candidate_ids = [sid for sid, _ in similar if sid != node_id]
                candidate_briefs = self.vault.get_node_briefs(candidate_ids) if candidate_ids else {}
                for sim_id, sim_score in similar:
                    if sim_id == node_id:
                        continue
                    brief = candidate_briefs.get(sim_id)
                    if not brief or brief.get('type') != 'DISCOVERY':
                        continue
                    if sim_score >= 0.85:
                        self.vault.touch_node(sim_id)
                        logger.info(f"DISCOVERY dedup: [{node_id}] merged into [{sim_id}] (sim={sim_score:.2f})")
                        return f"♻️ DISCOVERY [{subject}] already known as [{sim_id}] (sim={sim_score:.2f}), marked active."

            tags_str = ",".join((tags or [])[:5])
            full_content = json.dumps({
                "category": category,
                "subject": subject,
                "description": description,
                "evidence_tool": evidence_tool,
            }, ensure_ascii=False)

            self.vault.create_node(
                node_id=node_id,
                ntype="DISCOVERY",
                title=f"[{category}] {subject}: {description[:60]}",
                human_translation=f"{subject}: {description[:60]}",
                tags=f"discovery,{category.lower()},{tags_str}" if tags_str else f"discovery,{category.lower()}",
                full_content=full_content,
                source="c_phase_discovery",
                resolves=subject,
                metadata_signature={
                    "category": category,
                    "subject": subject,
                    "evidence_tool": evidence_tool,
                    "observed_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
                },
                trust_tier="REFLECTION",
            )
            logger.info(f"DISCOVERY recorded: [{node_id}] {category}/{subject}")

            # ── Auto-promote DISCOVERY → PATTERN ──
            # If same subject has ≥3 DISCOVERY nodes, create a PATTERN node.
            pattern_id = self._try_promote_to_pattern(subject, category)
            if pattern_id:
                return f"✅ DISCOVERY [{node_id}] {subject}: {description[:60]} → 🎯 auto-promoted to PATTERN [{pattern_id}]"
            return f"✅ DISCOVERY [{node_id}] {subject}: {description[:60]}"
        except Exception as e:
            logger.error(f"Discovery recording failed: {e}")
            return f"Error: {e}"

    def _try_promote_to_pattern(self, subject: str, category: str) -> str:
        """Check if same subject has ≥3 DISCOVERY nodes → auto-promote to PATTERN.

        Returns the new PATTERN node_id if promoted, empty string otherwise.
        Idempotent: if a PATTERN for this subject already exists, skip.
        """
        import hashlib
        try:
            # Check if PATTERN already exists for this subject
            pattern_prefix = f"PAT_{hashlib.md5(subject.encode()).hexdigest()[:8].upper()}"
            existing = self.vault._conn.execute(
                "SELECT node_id FROM knowledge_nodes WHERE node_id = ? AND type = 'PATTERN'",
                (pattern_prefix,)
            ).fetchone()
            if existing:
                return ""

            # Count DISCOVERY nodes with same subject (from metadata_signature)
            rows = self.vault._conn.execute(
                "SELECT node_id, title, full_content, metadata_signature FROM knowledge_nodes "
                "WHERE type = 'DISCOVERY' AND metadata_signature LIKE ?",
                (f'%{subject}%',)
            ).fetchall()
            # Precise filter: only count where subject matches exactly in signature
            matching = []
            for r in rows:
                try:
                    sig = json.loads(r["metadata_signature"]) if r["metadata_signature"] else {}
                    if sig.get("subject") == subject:
                        matching.append(r)
                except (json.JSONDecodeError, TypeError):
                    continue

            if len(matching) < 3:
                return ""

            # Build PATTERN from aggregated DISCOVERY descriptions
            descriptions = []
            for r in matching:
                try:
                    content = json.loads(r["full_content"]) if r["full_content"] else {}
                    desc = content.get("description", "")
                    if desc:
                        descriptions.append(desc)
                except (json.JSONDecodeError, TypeError):
                    continue

            # Deduplicate descriptions (keep unique ones)
            unique_descriptions = list(dict.fromkeys(descriptions))[:5]
            pattern_content = f"Recurring observation ({len(matching)}x): " + " | ".join(unique_descriptions)

            self.vault.create_node(
                node_id=pattern_prefix,
                ntype="PATTERN",
                title=f"[PATTERN] {subject}: {pattern_content[:60]}",
                human_translation=f"{subject}: {pattern_content[:60]}",
                tags=f"pattern,{category.lower()},auto_promoted",
                full_content=json.dumps({
                    "subject": subject,
                    "category": category,
                    "discovery_count": len(matching),
                    "descriptions": unique_descriptions,
                    "source_node_ids": [r["node_id"] for r in matching],
                }, ensure_ascii=False),
                source="auto_promotion",
                resolves=subject,
                metadata_signature={
                    "category": category,
                    "subject": subject,
                    "promotion_threshold": 3,
                    "discovery_count": len(matching),
                    "validation_status": "validated",
                    "knowledge_state": "current",
                },
                trust_tier="REFLECTION",
                verification_source="auto_promotion",
            )
            logger.info(f"PATTERN auto-promoted: [{pattern_prefix}] {subject} ({len(matching)} DISCOVERY nodes)")
            return pattern_prefix
        except Exception as e:
            logger.warning(f"PATTERN auto-promotion check failed for {subject}: {e}")
            return ""