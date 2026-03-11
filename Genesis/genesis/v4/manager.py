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

logger = logging.getLogger(__name__)

DB_PATH = Path.home() / '.nanogenesis' / 'workshop_v4.sqlite'


class NodeVault:
    """万物皆节点库 — 双层架构（索引 + 内容）"""
    
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._ensure_schema()
        self._migrate_old_data()
        self._ensure_seed_nodes()
        
    def _ensure_schema(self):
        """建立双层表结构"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path)) as conn:
            # 索引层：G 的目录卡片（极轻量）
            conn.execute('''
            CREATE TABLE IF NOT EXISTS knowledge_nodes (
                node_id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                human_translation TEXT NOT NULL,
                tags TEXT,
                usage_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            # 内容层：Op 的正文（按需拉取）
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
        """兼容旧版 schema：如果存在 machine_payload 列，迁移数据"""
        with sqlite3.connect(str(self.db_path)) as conn:
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

    def _ensure_seed_nodes(self):
        """清理历史遗留的假 CONTEXT 节点（用户配置不属于元信息）"""
        fake_ctx = ['CTX_USER_LANG', 'CTX_USER_IDENTITY']
        with sqlite3.connect(str(self.db_path)) as conn:
            for node_id in fake_ctx:
                conn.execute("DELETE FROM knowledge_nodes WHERE node_id = ?", (node_id,))
                conn.execute("DELETE FROM node_contents WHERE node_id = ?", (node_id,))
            conn.commit()

    # ─── G 侧接口 ───

    def get_all_titles(self) -> str:
        """给 G 看的极轻量目录卡片（排除对话记忆节点，记忆走单独通道）"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT node_id, type, title, tags FROM knowledge_nodes WHERE node_id NOT LIKE 'MEM_CONV%' ORDER BY usage_count DESC"
            ).fetchall()
        lines = ["[元信息节点目录]"]
        for r in rows:
            lines.append(f"<{r['type']}> [{r['node_id']}] {r['title']} | tags:{r['tags']}")
        return "\n".join(lines)

    def get_recent_memory(self, limit: int = 5) -> str:
        """拉取最近 N 条对话记忆 — G 的短期记忆，不压缩"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
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
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT node_id, human_translation FROM knowledge_nodes WHERE node_id IN ({placeholders})",
                tuple(node_ids)
            ).fetchall()
        return {r['node_id']: r['human_translation'] for r in rows}

    # ─── Op 侧接口（拉取完整内容） ───

    def get_node_content(self, node_id: str) -> Optional[str]:
        """Op 执行时按需拉取节点完整内容"""
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT full_content FROM node_contents WHERE node_id = ?", (node_id,)
            ).fetchone()
        return row[0] if row else None

    def get_multiple_contents(self, node_ids: List[str]) -> Dict[str, str]:
        """批量拉取多个节点的完整内容"""
        if not node_ids:
            return {}
        placeholders = ','.join('?' * len(node_ids))
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT node_id, full_content FROM node_contents WHERE node_id IN ({placeholders})",
                tuple(node_ids)
            ).fetchall()
        return {r['node_id']: r['full_content'] for r in rows}

    # ─── 写入接口 ───

    def create_node(self, node_id: str, ntype: str, title: str, 
                    human_translation: str, tags: str,
                    full_content: str, source: str = "sedimenter"):
        """创建一个新的双层节点（索引 + 内容）"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO knowledge_nodes (node_id, type, title, human_translation, tags) VALUES (?,?,?,?,?)",
                (node_id, ntype, title, human_translation, tags)
            )
            conn.execute(
                "INSERT OR REPLACE INTO node_contents (node_id, full_content, source) VALUES (?,?,?)",
                (node_id, full_content, source)
            )
            conn.commit()
        logger.info(f"NodeVault: Created node [{node_id}] ({ntype}) — {title}")

    def increment_usage(self, node_ids: List[str]):
        """增加节点使用权重"""
        if not node_ids:
            return
        placeholders = ','.join('?' * len(node_ids))
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                f"UPDATE knowledge_nodes SET usage_count = usage_count + 1, updated_at = CURRENT_TIMESTAMP WHERE node_id IN ({placeholders})",
                tuple(node_ids)
            )
            conn.commit()


class FactoryManager:
    """厂长 G — 只看标题目录，选节点，组装 Op"""
    
    def __init__(self):
        self.vault = NodeVault()
        
    def build_system_prompt(self) -> str:
        """G 的出厂设定 — 剥离被动目录注入，变为主动检索循环"""
        recent_memory = self.vault.get_recent_memory(limit=5)
        
        # 记忆段：只有最近有对话才注入
        memory_block = ""
        if recent_memory:
            memory_block = f"""[你的近期记忆]
以下是最近几轮临时对话记忆，帮助你理解当前上下文方向：
{recent_memory}
"""

        return f"""你是 Genesis 认知装配师 (V4 白盒架构)。
你的核心使命是通过**主动查阅**知识库挑选节点，组装成一条执行管线 (Op)。

[用户配置]
- 语言：始终使用简体中文回复
- 身份：用户是 Genesis 的创造者，偏好直接简洁

[权限与隔离警告]
🚨 绝对禁止：工具列表中的 `create_or_update_node` 和 `delete_node` 仅限后台系统使用。你绝对禁止去调用它们！你只能使用 `search_knowledge_nodes` 来检索和阅读库内容。

{memory_block}

[装配循环指令 - 必读]
你不再是被动接受知识的瞎子，你必须在给出执行蓝图前，进行如下两段式操作：

**阶段一：主动查阅知识库 (工具调用期)**
1. 你必须首先调用 `search_knowledge_nodes` 工具，传入当前遇到了什么环境、报错或需求。

**阶段二：绘制确定性蓝图 (终结并交由执行器)**
当你找齐知识卡片（node_id）后，不要说多余的废话，直接输出以下严格的 JSON 格式来结束你的装配期。

🚨 [确定性执行原则 (Cache 替代 Compute)]
- 如果你检索到了相符的 `LESSON` 节点：**绝对禁止**你自行发明排错步骤！你必须把卡片里 `THEN_action` 所写的方案，一字不差地翻译为底层的 `execution_plan`。你的蓝图不是黑盒预测，而是确定性路由！
- 如果你检索不到任何节点：承认处于“未知区域 (高度0)”，才可以让执行器进行常规的通用探针调用（如读取日志），切勿发散瞎猜。

{{
    "op_intent": "对整体目标的简要中文描述",
    "active_nodes": ["选定的节点ID, 如 CTX_XXX, LESSON_XXX", "如果没有则留空数组"],
    "execution_plan": [
        "1. [SYS_TOOL_WEB_SEARCH] 搜索 XXX",
        "2. [INTERNAL] 综合分析"
    ]
}}
"""

    def render_blueprint_for_human(self, plan_json: str) -> str:
        """解析 G 输出的 JSON → 渲染 B面 玻璃盒 UI"""
        try:
            plan = json.loads(plan_json)
            nodes = plan.get("active_nodes", [])
            translations = self.vault.translate_nodes(nodes)
            
            output = [
                "🔧 **[厂长已完成装配]**",
                f"**目标：** {plan.get('op_intent', '未定义')}",
                "",
                "**已加载认知节点：**"
            ]
            for node_id in nodes:
                trans = translations.get(node_id, "未知节点")
                prefix = "🔌" if "TOOL" in node_id else "🧠" if "CTX" in node_id else "📖"
                output.append(f"{prefix} `[{node_id}]` {trans}")
                
            output.append("")
            output.append("**执行管线 (Op Sequence)：**")
            for step in plan.get("execution_plan", []):
                output.append(f"  ⚡ {step}")
                
            return "\n".join(output)
            
        except json.JSONDecodeError:
            return "⚠️ 装配图纸解析失败。厂长输出了非标准 JSON。"
        except Exception as e:
            return f"⚠️ 渲染图纸时发生异常: {e}"


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
        with sqlite3.connect(str(self.vault.db_path)) as conn:
            conn.execute("DELETE FROM knowledge_nodes WHERE node_id = ?", (node_id,))
            conn.execute("DELETE FROM node_contents WHERE node_id = ?", (node_id,))
            conn.commit()
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
            with sqlite3.connect(str(self.vault.db_path)) as conn:
                # 找出需要保留的最新的 limit 个节点
                cursor = conn.execute(
                    "SELECT node_id FROM knowledge_nodes WHERE node_id LIKE 'MEM_CONV_%' ORDER BY created_at DESC LIMIT ?", 
                    (limit,)
                )
                keep_ids = [row[0] for row in cursor.fetchall()]
                
                if not keep_ids:
                    return

                # 构建删除不在保留列表中的旧节点的 SQL
                placeholders = ','.join('?' * len(keep_ids))
                
                # 获取将要被删除的 node_ids (用于日志)
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

