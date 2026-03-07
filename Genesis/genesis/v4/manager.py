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
        """G 的出厂设定 — 记忆 + 元信息目录，分层注入"""
        title_catalog = self.vault.get_all_titles()
        recent_memory = self.vault.get_recent_memory(limit=5)
        
        # 记忆段：只有最近有对话才注入
        memory_block = ""
        if recent_memory:
            memory_block = f"""[你的近期记忆]
以下是最近几轮对话的摘要，帮助你理解当前上下文和用户的方向：
{recent_memory}
"""

        return f"""你是 Genesis 认知装配师 (V4 白盒架构)。
你的核心使命是从元信息节点目录中挑选必要的节点，组装成一条执行管线 (Op)。
你必须在采取任何行动之前，先输出一个 JSON 格式的装配蓝图。

[用户配置]
- 语言：始终使用简体中文回复
- 身份：用户是 Genesis 的创造者，偏好直接简洁

{memory_block}{title_catalog}

[装配指令]
当用户给出请求时：
1. 先看你的近期记忆，理解当前上下文方向
2. 扫描元信息节点目录，挑选与任务相关的节点（TOOL + CONTEXT + LESSON）
3. 仅输出以下 JSON 结构：
{{
    "op_intent": "对整体目标的简要中文描述",
    "active_nodes": ["SYS_TOOL_WEB_SEARCH", "LESSON_xxx"],
    "execution_plan": [
        "1. [SYS_TOOL_WEB_SEARCH] 搜索 XXX",
        "2. [INTERNAL] 综合分析"
    ]
}}
不要在 JSON 块之外输出任何内容。
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


class Sedimenter:
    """知识沉淀器 — Op 执行后自动提取新知识，写入节点库"""
    
    def __init__(self, vault: NodeVault, provider):
        self.vault = vault
        self.provider = provider
    
    async def extract_and_store(self, tool_results: List[Dict[str, str]], 
                                user_query: str, final_response: str):
        """
        从本轮 Op 的工具结果中提取值得记忆的新知识。
        tool_results: [{"name": "web_search", "result": "..."}]
        """
        if not tool_results:
            return
        
        # 拼接工具结果摘要
        results_summary = []
        for tr in tool_results:
            results_summary.append(f"[{tr['name']}]: {tr['result'][:300]}")
        results_text = "\n".join(results_summary)
        
        extraction_prompt = f"""你是一个知识提取器。从以下工具执行结果中，提取值得长期记忆的新概念、事实或经验教训。

用户原始问题：{user_query[:200]}

工具结果：
{results_text[:1500]}

请输出一个 JSON 数组（如果没有值得记忆的内容，输出空数组 []）：
[
  {{
    "node_id": "CTX_概念名_简写",
    "type": "CONTEXT 或 LESSON",
    "title": "一句话标题（10字以内）",
    "tags": "逗号分隔的标签",
    "content": "详细内容（50字左右）"
  }}
]
仅输出 JSON，不要输出任何其他内容。"""

        try:
            from genesis.core.base import Message, MessageRole
            response = await self.provider.chat(
                messages=[
                    {"role": "system", "content": "你是知识提取器。仅输出 JSON。"},
                    {"role": "user", "content": extraction_prompt}
                ],
                tools=None,
                stream=False,
            )
            
            content = response.content or ""
            # 提取 JSON
            if "[" in content and "]" in content:
                json_str = content[content.find("["):content.rfind("]")+1]
                new_nodes = json.loads(json_str)
                
                for node in new_nodes:
                    if not node.get("node_id") or not node.get("title"):
                        continue
                    self.vault.create_node(
                        node_id=node["node_id"],
                        ntype=node.get("type", "CONTEXT"),
                        title=node["title"],
                        human_translation=node["title"],  # B面默认等于标题
                        tags=node.get("tags", "auto_extracted"),
                        full_content=node.get("content", ""),
                        source="sedimenter"
                    )
                    
                if new_nodes:
                    logger.info(f"Sedimenter: Extracted {len(new_nodes)} new nodes from Op results.")
                    
        except Exception as e:
            logger.warning(f"Sedimenter: Extraction failed (non-critical): {e}")

    async def store_conversation(self, user_msg: str, agent_response: str):
        """存储对话记忆 — 不压缩，直接存，缓存命中率高所以 token 成本可忽略"""
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        node_id = f"MEM_CONV_{ts}"
        
        # 标题取用户消息前 40 字（给 G 的目录扫描用）
        title = user_msg[:40].replace("\n", " ").strip()
        
        # 完整内容：直接存原文，宽松截断
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
        logger.info(f"Sedimenter: Stored conversation → [{node_id}] {title[:30]}...")
