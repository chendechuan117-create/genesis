"""
Genesis V4 - 认知装配师 (The Factory Manager G)
核心：节点是标题，内容用链接联通。G 看标题，Op 看内容。
"""

import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
from genesis.v4.vector_engine import VectorEngine

logger = logging.getLogger(__name__)

DB_PATH = Path.home() / '.nanogenesis' / 'workshop_v4.sqlite'


class NodeVault:
    """万物皆节点库 — 双层架构（索引 + 内容）, 单例模式"""
    _instance = None
    
    def __new__(cls, db_path: Path = DB_PATH):
        if cls._instance is None:
            cls._instance = super(NodeVault, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, db_path: Path = DB_PATH):
        if self._initialized:
            return
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 持久连接 + WAL 模式（读写不阻塞）
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        
        self._ensure_schema()
        self._migrate_old_data()
        
        # 启动并加载向量引擎
        self.vector_engine = VectorEngine()
        self.vector_engine.initialize()
        self._load_embeddings_to_memory()
        self._initialized = True

    def _load_embeddings_to_memory(self):
        rows = self._conn.execute("SELECT node_id, embedding FROM knowledge_nodes WHERE embedding IS NOT NULL AND node_id NOT LIKE 'MEM_CONV%'").fetchall()
        self.vector_engine.load_matrix([dict(r) for r in rows])
        
    def _ensure_schema(self):
        """建立双层表结构"""
        conn = self._conn
        conn.execute('''
        CREATE TABLE IF NOT EXISTS knowledge_nodes (
            node_id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            human_translation TEXT NOT NULL,
            tags TEXT,
            prerequisites TEXT,
            resolves TEXT,
            embedding TEXT,
            usage_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        for col in ['prerequisites', 'resolves', 'embedding']:
            try:
                conn.execute(f"ALTER TABLE knowledge_nodes ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass
        conn.execute('''
        CREATE TABLE IF NOT EXISTS node_contents (
            node_id TEXT PRIMARY KEY,
            full_content TEXT NOT NULL,
            source TEXT DEFAULT 'system',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (node_id) REFERENCES knowledge_nodes(node_id)
        )
        ''')
        conn.commit()

    def _migrate_old_data(self):
        """兼容旧版 schema（带 machine_payload 列的非常老的版本）"""
        conn = self._conn
        with conn:
            cols = [row[1] for row in conn.execute("PRAGMA table_info(knowledge_nodes)").fetchall()]
            if 'machine_payload' in cols and 'title' not in cols:
                logger.info("NodeVault: Migrating old schema → new dual-layer schema...")
                # Rename old table
                conn.execute("ALTER TABLE knowledge_nodes RENAME TO _old_nodes")
                # Create new schema
                conn.execute('''
                CREATE TABLE knowledge_nodes (
                    node_id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    human_translation TEXT NOT NULL,
                    tags TEXT,
                    prerequisites TEXT,
                    resolves TEXT,
                    usage_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                ''')
                conn.execute('''
                CREATE TABLE IF NOT EXISTS node_contents (
                    node_id TEXT PRIMARY KEY,
                    full_content TEXT NOT NULL,
                    source TEXT DEFAULT 'system',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (node_id) REFERENCES knowledge_nodes(node_id)
                )
                ''')
                # Migrate data: extract a short title from machine_payload
                rows = conn.execute("SELECT node_id, type, machine_payload, human_translation, tags, usage_count FROM _old_nodes").fetchall()
                for r in rows:
                    try:
                        payload = json.loads(r[2])
                        title = payload.get("name", r[0])
                    except:
                        title = r[0]
                    conn.execute(
                        "INSERT OR IGNORE INTO knowledge_nodes (node_id, type, title, human_translation, tags, usage_count) VALUES (?,?,?,?,?,?)",
                        (r[0], r[1], title, r[3], r[4], r[5])
                    )
                    conn.execute(
                        "INSERT OR IGNORE INTO node_contents (node_id, full_content, source) VALUES (?,?,?)",
                        (r[0], r[2], "migrated_from_v4.0")
                    )
                conn.execute("DROP TABLE _old_nodes")
                conn.commit()
                logger.info(f"NodeVault: Migrated {len(rows)} nodes to dual-layer schema.")

    # ─── G 侧接口 ───

    def get_all_titles(self) -> str:
        """给 G 看的极轻量目录卡片（排除对话记忆节点，记忆走单独通道）"""
        rows = self._conn.execute(
            "SELECT node_id, type, title, tags, prerequisites, resolves FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV%' ORDER BY usage_count DESC"
        ).fetchall()
        lines = ["[元信息节点目录]"]
        for r in rows:
            reqs = f" | reqs:[{r['prerequisites']}]" if r['prerequisites'] else ""
            res = f" | resolves:[{r['resolves']}]" if r['resolves'] else ""
            lines.append(f"<{r['type']}> [{r['node_id']}] {r['title']} | tags:{r['tags']}{reqs}{res}")
        return "\n".join(lines)

    def get_recent_memory(self, limit: int = 5) -> str:
        """拉取最近 N 条对话记忆 — G 的短期记忆，不压缩"""
        rows = self._conn.execute(
            "SELECT nc.full_content FROM knowledge_nodes kn "
            "JOIN node_contents nc ON kn.node_id = nc.node_id "
            "WHERE kn.node_id LIKE 'MEM_CONV%' "
            "ORDER BY kn.created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        if not rows:
            return ""
        lines = []
        for r in reversed(rows):  # 按时间正序
            lines.append(r['full_content'])
            lines.append("---")
        return "\n".join(lines)

    def translate_nodes(self, node_ids: List[str]) -> Dict[str, str]:
        """返回 B 面人类翻译"""
        if not node_ids:
            return {}
        placeholders = ','.join('?' * len(node_ids))
        rows = self._conn.execute(
            f"SELECT node_id, human_translation FROM knowledge_nodes WHERE node_id IN ({placeholders})",
            tuple(node_ids)
        ).fetchall()
        return {r['node_id']: r['human_translation'] for r in rows}

    # ─── Op 侧接口（拉取完整内容） ───

    def get_node_content(self, node_id: str) -> Optional[str]:
        """Op 执行时按需拉取节点完整内容"""
        row = self._conn.execute(
            "SELECT full_content FROM node_contents WHERE node_id = ?", (node_id,)
        ).fetchone()
        return row[0] if row else None

    def get_multiple_contents(self, node_ids: List[str]) -> Dict[str, str]:
        """批量拉取多个节点的完整内容"""
        if not node_ids:
            return {}
        placeholders = ','.join('?' * len(node_ids))
        rows = self._conn.execute(
            f"SELECT node_id, full_content FROM node_contents WHERE node_id IN ({placeholders})",
            tuple(node_ids)
        ).fetchall()
        return {r['node_id']: r['full_content'] for r in rows}

    # ─── 写入接口 ───

    def create_node(self, node_id: str, ntype: str, title: str, 
                    human_translation: str, tags: str,
                    full_content: str, source: str = "sedimenter",
                    prerequisites: str = None, resolves: str = None):
        """创建一个新的双层节点（索引 + 内容），支持注入因果属性和自动向量化"""
        # 如果是知识类节点，自动计算其向量
        embedding_json = None
        if ntype in ["LESSON", "CONTEXT"] and self.vector_engine.is_ready:
            text_to_encode = f"{title} {tags} {resolves or ''}"
            vec = self.vector_engine.encode(text_to_encode)
            if vec:
                embedding_json = json.dumps(vec)
                self.vector_engine.add_to_matrix(node_id, vec)

        self._conn.execute(
            "INSERT OR REPLACE INTO knowledge_nodes (node_id, type, title, human_translation, tags, prerequisites, resolves, embedding) VALUES (?,?,?,?,?,?,?,?)",
            (node_id, ntype, title, human_translation, tags, prerequisites, resolves, embedding_json)
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO node_contents (node_id, full_content, source) VALUES (?,?,?)",
            (node_id, full_content, source)
        )
        self._conn.commit()
        logger.info(f"NodeVault: Created node [{node_id}] ({ntype}) — {title}")

    def increment_usage(self, node_ids: List[str]):
        """增加节点使用权重"""
        if not node_ids:
            return
        placeholders = ','.join('?' * len(node_ids))
        self._conn.execute(
            f"UPDATE knowledge_nodes SET usage_count = usage_count + 1, updated_at = CURRENT_TIMESTAMP WHERE node_id IN ({placeholders})",
            tuple(node_ids)
        )


class FactoryManager:
    """负责组装系统提示词 (G / Op / C)"""
    
    def __init__(self, vault: NodeVault = None):
        self.vault = vault or NodeVault()
        
    def build_g_prompt(self, recent_memory: str = "", available_tools_info: str = "") -> str:
        """为 G (Thinker) 构建系统提示词"""
        
        memory_block = ""
        if recent_memory:
            memory_block = f"""[你的近期记忆]
以下是最近几轮临时对话记忆，帮助你理解当前上下文方向：
{recent_memory}
"""
        
        tools_block = ""
        if available_tools_info:
            tools_block = f"""[Op 可用执行工具库]
请注意，除了你在搜索阶段使用的工具外，执行器(Op)在执行阶段可以使用以下工具。
你在向 Op 派发任务时，可以参考这些能力：
{available_tools_info}
"""

        return f"""你是 Genesis 的认知装配师 / 大脑 (G-Process)。
你的核心使命是通过**主动查阅**知识库，理解用户的真实意图，然后为执行器 (Op-Process) 准备一份包含充足上下文的任务派发书 (Task Payload)。

[用户配置]
- 语言：始终使用简体中文回复
- 身份：用户是 Genesis 的创造者，偏好直接简洁

[权限与隔离警告]
🚨 绝对禁止：工具列表中的 `create_or_update_node` 和 `delete_node` 仅限后台系统使用。你绝对禁止调用它们！你只能使用搜索类工具来检索信息。

{memory_block}

{tools_block}

[工作流指令 - 必读]
你和 Op (执行器) 是隔离的。Op 没有任何历史上下文，是个纯粹的打工人。
你必须先进行搜索思考，然后把你需要 Op 知道的一切信息“打包”发给它。

**阶段一：查阅与思考 (G 的工作)**
1. 如果任务涉及复杂环境、特定报错或你缺乏上下文，请**优先反复调用**搜索工具，获取过往经验（LESSON）或环境信息（CONTEXT）。
2. 你可以调用多次搜索工具，直到你认为收集到了足够指导 Op 工作的元信息。

**阶段二：派发任务 (交接给 Op)**
当你收集完信息（或者认为不需要搜）准备让 Op 开始干活时，请**直接输出以下格式的任务派发书**。
只要你输出这个格式，系统就会立刻截断你的运行，并将里面的内容交给 Op 去执行。

```dispatch
OP_INTENT: <对 Op 目标的简短明确指令>
ACTIVE_NODES: <你需要挂载给 Op 参考的节点ID列表，用逗号分隔，如 CTX_XXX, LESSON_XXX。如果没有则写 NONE>
INSTRUCTIONS:
<给 Op 的具体执行建议或上下文信息。写清楚你想让 Op 怎么做，因为 Op 看不到你之前的搜索过程。>
```
"""

    def build_op_prompt(self, task_payload: dict) -> str:
        """为 Op (Executor) 构建系统提示词"""
        
        op_intent = task_payload.get("op_intent", "未定义目标")
        instructions = task_payload.get("instructions", "无")
        node_ids = task_payload.get("active_nodes", [])
        
        # 注入节点内容
        injection_text = ""
        if node_ids:
            node_contents = self.vault.get_multiple_contents(node_ids)
            if node_contents:
                injection_text = "\n[系统注入：G 为你准备的认知参考节点]\n"
                for nid, text in node_contents.items():
                    injection_text += f"--- NODE: {nid} ---\n{text}\n"

        return f"""你是 Genesis 的执行器 (Op-Process)。
你的核心使命是**只管干活**。你不需要知道复杂的历史背景，你只需要根据大脑 (G) 分配给你的目标和参考资料，利用你手头的工具完成任务。

[用户配置]
- 语言：始终使用简体中文回复

[G 派发的任务]
**目标 (OP_INTENT):** {op_intent}

**执行建议 (INSTRUCTIONS):**
{instructions}
{injection_text}

[工作流指令 - 必读]
1. 立即开始使用你的工具（如 Shell、File、Web 等）执行上述目标。
2. 遇到问题时，根据报错信息自行调整重试。
3. 当你认为任务已经彻底完成，或者穷尽了方法依然失败时，请直接用普通文本回复最终结果。你的文本回复将标志着任务结束并展示给用户。
"""

    def render_dispatch_for_human(self, task_payload: dict) -> str:
        """渲染 G 派发给 Op 的任务书给人类看"""
        try:
            nodes = task_payload.get("active_nodes", [])
            translations = self.vault.translate_nodes(nodes)
            
            output = [
                "🧠 **[大脑 (G) 已完成思考，正在派发任务给执行器 (Op)]**",
                f"**目标：** {task_payload.get('op_intent', '未定义')}",
                "",
            ]
            
            if nodes:
                output.append("**挂载认知节点：**")
                for node_id in nodes:
                    trans = translations.get(node_id, "未知节点")
                    prefix = "🔌" if "TOOL" in node_id else "🧠" if "CTX" in node_id else "📖"
                    output.append(f"{prefix} `[{node_id}]` {trans}")
                output.append("")
                
            output.append("**执行建议：**")
            # 缩略显示 instructions
            instr = task_payload.get("instructions", "")
            if len(instr) > 200:
                instr = instr[:200] + "..."
            output.append(f"> {instr.replace(chr(10), chr(10)+'> ')}")
                
            return "\n".join(output)
            
        except Exception as e:
            return f"⚠️ 渲染派发书时发生异常: {e}"


class NodeManagementTools:
    """提供给 G 在反思阶段使用的节点管理工具的实际实现"""
    
    def __init__(self, vault: NodeVault):
        self.vault = vault

    def create_or_update_node(self, node_id: str, ntype: str, title: str, content: str, source: str = "reflection") -> str:
        """创建新节点或覆盖更新已有节点"""
        self.vault.create_node(
            node_id=node_id,
            ntype=ntype,
            title=title,
            human_translation=title, # 默认取标题
            tags="auto_managed",
            full_content=content,
            source=source
        )
        return f"✅ 节点 [{node_id}] '{title}' 写入成功。"

    def delete_node(self, node_id: str) -> str:
        """删除错误或过时的节点"""
        self.vault._conn.execute("DELETE FROM knowledge_nodes WHERE node_id = ?", (node_id,))
        self.vault._conn.execute("DELETE FROM node_contents WHERE node_id = ?", (node_id,))
        self.vault._conn.commit()
        logger.info(f"NodeVault: Deleted node [{node_id}]")
        return f"✅ 节点 [{node_id}] 删除成功。"

    def store_conversation(self, user_msg: str, agent_response: str):
        """记录 G 的短期记忆（纯时间序列，给 G 起步上下文用的）"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        node_id = f"MEM_CONV_{ts}"
        title = user_msg[:40].replace("\n", " ").strip()
        memory_content = f"用户: {user_msg[:500]}\nGenesis: {agent_response[:800]}"
        
        self.vault.create_node(
            node_id=node_id,
            ntype="CONTEXT",
            title=title,
            human_translation=f"对话记忆 ({ts})",
            tags="memory,conversation",
            full_content=memory_content,
            source="conversation"
        )
        logger.info(f"NodeManagement: Stored conversation → [{node_id}]")
        self._cleanup_old_memories()

    def _cleanup_old_memories(self, limit: int = 10):
        """记忆滑动窗口：清理超出的老旧短期记忆，防止数据库淤积"""
        try:
            conn = self.vault._conn
            cursor = conn.execute(
                "SELECT node_id FROM knowledge_nodes WHERE node_id LIKE 'MEM_CONV_%' ORDER BY created_at DESC LIMIT ?", 
                (limit,)
            )
            keep_ids = [row[0] for row in cursor.fetchall()]
            
            if not keep_ids:
                return

            placeholders = ','.join('?' * len(keep_ids))
            del_cursor = conn.execute(
                f"SELECT node_id FROM knowledge_nodes WHERE node_id LIKE 'MEM_CONV_%' AND node_id NOT IN ({placeholders})",
                tuple(keep_ids)
            )
            to_delete = [row[0] for row in del_cursor.fetchall()]

            if to_delete:
                conn.execute(f"DELETE FROM knowledge_nodes WHERE node_id LIKE 'MEM_CONV_%' AND node_id NOT IN ({placeholders})", tuple(keep_ids))
                conn.execute(f"DELETE FROM node_contents WHERE node_id LIKE 'MEM_CONV_%' AND node_id NOT IN ({placeholders})", tuple(keep_ids))
                conn.commit()
                logger.info(f"NodeManagement: Memory sliding window purged {len(to_delete)} old conversations.")
        except Exception as e:
            logger.error(f"Failed to cleanup old memories: {e}")

