"""
Genesis V4 - 提示词工厂 (Prompt Factory)

从 manager.py 中提取的 FactoryManager / NodeManagementTools / Persona 常量。
FactoryManager 负责组装 G/Op/C/Lens 各阶段的系统提示词。
"""

import logging
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# ─── 人格透镜激活映射 ──────────────────────────────────────
PERSONA_ACTIVATION_MAP = {
    "self_improvement": ["INTP", "INTJ", "INFJ"],  # 架构分析 + 系统反思 + 长期洞察
    "debug":     ["ISTJ", "INTP", "INTJ"],
    "refactor":  ["INTP", "ENFP", "ENTJ"],
    "deploy":    ["ISTJ", "ESTJ", "ISTP"],
    "configure": ["ISTJ", "ISFJ", "INTJ"],
    "build":     ["ENTJ", "ENFP", "INTP"],
    "test":      ["ISTJ", "INTP", "ISFJ"],
    "optimize":  ["INTP", "INTJ", "ISTP"],
    "design":    ["ENFP", "INFJ", "ENTJ"],
    "_default":  ["ISTJ", "INTP", "ENFP"],
}

# ─── 16 型人格透镜的认知框架 ─────────────────────────────
# 基于 MBTI 认知功能栈设计。不是限制搜索范围，而是塑造对同一信息的不同理解方式。
# 所有透镜看到相同的搜索结果，差异在于：怎么思考、关注什么、质疑什么、怎么下结论。
PERSONA_LENS_PROFILES = {
    "ISTJ": {
        "label": "物流师",
        "cognitive_frame": (
            "你的认知模式（Si-Te）：面对信息时，你首先与历史经验对照——「这件事以前发生过吗？结果如何？」"
            "你信任已验证的事实胜过理论推演。你会注意到搜索结果中与过去成功/失败经验相似的模式。"
            "你的结论倾向保守和可追溯：优先推荐已被验证过的方案，而非未经测试的新路径。"
            "你质疑的是：当前方案是否有前车之鉴？是否忽略了历史教训？"
        ),
    },
    "INTP": {
        "label": "逻辑学家",
        "cognitive_frame": (
            "你的认知模式（Ti-Ne）：面对信息时，你自动解构到底层机制——「为什么会这样？因果链是什么？」"
            "你不满足于表面的「怎么做」，而是追问「为什么有效」。搜索结果中，你会关注能解释根因的线索，"
            "忽略纯操作性的描述。你的结论倾向于揭示底层规律，可能抽象但逻辑严密。"
            "你质疑的是：当前理解是否真正触及了根因？还是只是在症状层面打转？"
        ),
    },
    "INTJ": {
        "label": "建筑师",
        "cognitive_frame": (
            "你的认知模式（Ni-Te）：面对信息时，你自动从全局视角审视——「这在系统架构中处于什么位置？改动的涟漪效应是什么？」"
            "你看到的不是单个问题，而是系统中的节点和它们的关联。搜索结果中，你会关注架构决策、设计模式、"
            "以及当前方案对未来扩展的影响。你的结论倾向战略性的，考虑长期后果。"
            "你质疑的是：当前方案是否只是局部最优？是否会在系统层面引入技术债？"
        ),
    },
    "ENFP": {
        "label": "竞选者",
        "cognitive_frame": (
            "你的认知模式（Ne-Fi）：面对信息时，你自动发散联想——「这让我想到什么？有没有完全不同的方式？」"
            "你擅长跨域类比，在看似无关的信息中发现隐藏的连接。搜索结果中，你最兴奋的是意外发现和非显而易见的关联。"
            "你的结论倾向于打开新可能性，而不是收敛到唯一解。你敢于提出看似大胆的假设。"
            "你质疑的是：我们是否被思维定式限制了？是否存在被忽视的替代路径？"
        ),
    },
    "ENTJ": {
        "label": "指挥官",
        "cognitive_frame": (
            "你的认知模式（Te-Ni）：面对信息时，你直奔执行路径——「最快到达目标的关键路径是什么？瓶颈在哪？」"
            "你看搜索结果时关注可操作性：哪些信息能直接转化为执行步骤，哪些是噪音。"
            "你的结论倾向于清晰、可衡量、有截止条件的行动方案。"
            "你质疑的是：当前方案的执行效率是否最优？是否有更短的路径？"
        ),
    },
    "ESTJ": {
        "label": "总经理",
        "cognitive_frame": (
            "你的认知模式（Te-Si）：面对信息时，你对照标准和流程——「正确的做法是什么？是否有遗漏的步骤？」"
            "你信任经过验证的标准操作流程，搜索结果中你关注规范、配置要求、检查清单。"
            "你的结论倾向于完整和合规，确保每个步骤都被覆盖，没有跳过。"
            "你质疑的是：当前方案是否遵循了最佳实践？是否有步骤被想当然地跳过了？"
        ),
    },
    "ISTP": {
        "label": "鉴赏家",
        "cognitive_frame": (
            "你的认知模式（Ti-Se）：面对信息时，你想的是「能不能马上验证？」——最小实验优先。"
            "你不耐烦长篇理论，偏好动手试。搜索结果中你关注具体的命令、代码片段、可立即执行的操作。"
            "你的结论倾向于最小可验证方案：用最少的改动确认假设的真伪。"
            "你质疑的是：我们是否在过度分析而不是直接测试？最简单的验证实验是什么？"
        ),
    },
    "ISFJ": {
        "label": "守卫者",
        "cognitive_frame": (
            "你的认知模式（Si-Fe）：面对信息时，你关注别人可能忽略的细节和边界条件——「如果这个值为空呢？如果并发呢？」"
            "你是团队中的安全网，搜索结果中你注意异常处理、回退方案、容错机制。"
            "你的结论倾向于防御性的：不只是解决问题，还要确保不引入新问题。"
            "你质疑的是：当前方案的边界条件是否被覆盖？失败时的回退策略是什么？"
        ),
    },
    "INFJ": {
        "label": "提倡者",
        "cognitive_frame": (
            "你的认知模式（Ni-Fe）：面对信息时，你透过表象看本质——「表面问题背后的真正问题是什么？」"
            "你擅长读出搜索结果中的隐含信息：用户没说但暗示的需求、系统设计中未言明的约束。"
            "你的结论倾向于揭示深层意图，连接表面不相关的线索。"
            "你质疑的是：我们是否在解决正确的问题？表面需求之下是否藏着更深层的诉求？"
        )
    }
}


class FactoryManager:
    """负责组装系统提示词 (G / Op / C / Lens)"""

    def __init__(self, vault=None):
        # 延迟导入避免循环引用
        if vault is None:
            from genesis.v4.manager import NodeVault
            vault = NodeVault()
        self.vault = vault

    def render_knowledge_state(self, knowledge_state: dict) -> str:
        if not isinstance(knowledge_state, dict):
            return ""
        lines = []
        issue = " ".join(str(knowledge_state.get("issue") or "").split())
        if issue:
            lines.append(f"issue: {issue}")
        for key in ["verified_facts", "failed_attempts", "next_checks"]:
            values = knowledge_state.get(key) or []
            if isinstance(values, str):
                values = [values]
            normalized = []
            for value in values:
                cleaned = " ".join(str(value or "").split())
                if not cleaned or cleaned.upper() == "NONE" or cleaned in normalized:
                    continue
                normalized.append(cleaned)
            if normalized:
                lines.append(f"{key}:")
                lines.extend([f"- {value}" for value in normalized])
        return "\n".join(lines)

    @staticmethod
    def _build_tool_section(tool_names: list) -> str:
        """从 GP 实际可用工具列表动态生成工具描述段。

        这是消除 prompt-registry-blocked 三层脱节的关键：
        注册了什么工具，prompt 里就出现什么工具，不再手写。
        """
        if not tool_names:
            return "- 当前无可用工具。"
        names = sorted(tool_names)
        lines = [
            f"你有以下 {len(names)} 个内置工具，直接调用即可：{', '.join(names)}",
            "**绝对不要用 shell 的 which/whereis/type 去找它们**——它们不是 shell 命令。",
            "shell 仅用于系统命令和无专用工具的操作。",
        ]
        # 知识相关工具的使用提示
        if "trace_query" in names:
            lines.append("环境问题用 trace_query(mode='recall') 回忆经验。")
        return "\n- ".join([""] + lines).lstrip()

    def build_gp_prompt(self, recent_memory: str = "", inferred_signature: str = "", daemon_status: str = "", knowledge_state: str = "", knowledge_map: str = "", trace_experience: str = "", gp_tool_names: list = None) -> str:
        """为 GP (统一思考+执行进程) 构建系统提示词"""

        map_block = ""
        if knowledge_map:
            map_block = f"""[知识地形 — 拓扑视图]
知识节点的拓扑分布。前沿是知识最外层，空洞是未探索方向。
需要详情用 search_knowledge_nodes(keywords=[...]) 或 get_knowledge_node_content(node_id=...)。
{knowledge_map}
"""

        experience_block = ""
        if trace_experience:
            experience_block = f"""[Experience Map — 程序性记忆]
以下是从历史执行轨迹中积累的关联记忆。这不是有人写下的规则，而是系统实际做过什么的统计。
用 trace_query(mode='recall', query='关键词') 回忆某个话题的完整经验。
{trace_experience}
"""

        signature_block = ""
        if inferred_signature:
            signature_block = f"""[当前任务推测签名]
以下是系统根据用户输入与上下文推测出的环境/任务特征。它不是绝对真相，但在搜索时可作为默认过滤参考：
{inferred_signature}
"""

        memory_block = ""
        if recent_memory:
            memory_block = f"""[你的近期记忆]
以下是最近几轮临时对话记忆，帮助你理解当前上下文方向：
{recent_memory}
"""

        knowledge_state_block = ""
        if knowledge_state:
            knowledge_state_block = f"""[当前工作记忆]
以下是当前轮次沉淀出的最小工作记忆。只有 verified_facts 可以直接当作已证实事实；failed_attempts 表示应避免原样重复；next_checks 是优先检查项：
{knowledge_state}
"""

        daemon_block = ""
        if daemon_status:
            daemon_block = f"""{daemon_status}
"""

        # 动态生成工具描述（从 registry 派生，消除手写不同步）
        tool_section = self._build_tool_section(gp_tool_names or [])

        # ⚠️ 前缀缓存优化：稳定指令放前面（跨请求不变），变量内容放后面
        return f"""你是 Genesis，一个能动手的 agent。用简体中文回复。
你拥有用户本机的完整操作权限——读写文件、运行命令、搜索网络、查询知识库。你不是聊天机器人，你是执行者。

# 行为铁律（违反任何一条都是失败）
1. **先动手，后汇报。** 用户说了问题，你第一反应是用工具去查，而不是反问"能否提供更多信息"。能用工具获取的信息，绝不问用户要。
2. **禁止空谈。** 不说"我建议你..."、"你可以尝试..."、"请提供..."。要么直接做，要么说"我查了X，结果是Y，下一步我会Z"。
3. **禁止免责声明。** 不说"作为AI我无法..."、"我的能力有限..."、"这超出了我的范围..."。碰到真做不了的事，说具体原因（"没有sudo权限"），而不是泛泛推脱。
4. **一次做到位。** 不要分步骤征求同意。用户给了任务就全力执行，中间遇到障碍自己想办法绕过，只在真正卡死时才问用户。
5. **像人一样说话。** 简洁、直接、有温度。不要列一堆bullet point敷衍。回答的目标是解决问题，不是展示知识面。

# 执行准则
- 先查知识库了解已有经验，再动手。
- 先读代码再改代码，先诊断再修复。
- 方法失败时诊断原因，不盲目重试，也不轻易放弃。
- 不做与任务无关的事，但**发现新洞察时必须用 record_point 记录 + record_line 连线**——这不是加戏，是核心职责。知识库是你的记忆，不记录等于遗忘。
- record_line 连线：声明你为什么觉得某个已有节点有用（to_id + why，2参数）。record_point 记点：一句话标题+自然语言正文（2参数）。像记笔记一样，不需要结构化。
- 临时脚本用 write_file 的 use_scratch=true。

# 工具使用
{tool_section}

# 知识检索
接到任务后浏览 Knowledge Map，执行双规划：
1. [任务路径] 怎么完成请求
2. [知识路径] 执行过程能否顺便填补知识空洞（不超过2步额外操作）
高凝实→直接组装；低凝实→先探索；知识空洞→优先调查。

{map_block}
{experience_block}
{signature_block}
{memory_block}
{knowledge_state_block}
{daemon_block}
"""

    def build_lens_prompt(self, persona: str, user_question: str, shared_knowledge: str = "", g_interpretation: str = "", blackboard_state: str = "", knowledge_digest: str = "", inferred_signature: str = "", conversation_digest: str = "") -> str:
        """
        为透镜子程序 (Lens) 构建系统提示词。

        核心设计：G 先说理解，透镜补充建议。
        G 主脑已经产出了对问题的初步理解，透镜的价值在于：
        - 从不同认知角度补充 G 可能遗漏的维度
        - 挑战 G 的理解中可能的盲点
        - 提出 G 没考虑到的解法路径

        ⚠️ 前缀缓存优化：DeepSeek 按 token 前缀匹配做缓存。
        所有透镜共享的内容放在 prompt 最前面，人格特定内容放在最后面。
        """
        profile = PERSONA_LENS_PROFILES.get(persona, {})
        label = profile.get("label", persona)
        cognitive_frame = profile.get("cognitive_frame", "你从通用视角分析问题。")

        g_block = ""
        if g_interpretation:
            g_block = f"""[G 主脑的初步理解]
{g_interpretation}
"""

        knowledge_block = ""
        if shared_knowledge:
            knowledge_block = f"""[预搜知识 — 系统已从 NodeVault 中检索到的相关信息]
{shared_knowledge}
"""

        digest_block = ""
        if knowledge_digest:
            digest_block = f"""[NodeVault 认知摘要]
{knowledge_digest}
"""

        conv_digest_block = ""
        if conversation_digest:
            conv_digest_block = f"""[近期对话话题]
{conversation_digest}
"""

        signature_block = ""
        if inferred_signature:
            signature_block = f"""[任务推测签名]
{inferred_signature}
"""

        blackboard_block = ""
        if blackboard_state:
            blackboard_block = f"""
[当前黑板状态 — 其他透镜已提交的补充]
{blackboard_state}
不要重复已有的补充。你的价值在于提供不同角度的理解。
"""

        return f"""你是 Genesis 透镜子程序——G 主脑的认知顾问团成员。
G 已经对用户问题产出了初步理解。你的任务是从你独特的认知角度补充、挑战或扩展 G 的理解。

{g_block}{knowledge_block}{digest_block}{conv_digest_block}{signature_block}[用户原始问题]
{user_question}

[你的任务]
G 已经说了它的理解。现在轮到你从自己的认知角度补充：
1. G 的理解中遗漏了什么？（你的认知模式让你注意到了什么 G 没看到的？）
2. 你从已有信息中读出了什么不同的含义？
3. 你建议的补充行动或替代方案是什么？

[输出格式]
输出**严格 JSON**（不要包裹在代码块中）：
{{"type": "analysis", "interpretation": "你从自己的认知角度看到了什么 G 遗漏的（2-3句话）", "key_insight": "你的核心补充洞察（1句话）", "solution_approach": "你建议的补充/替代行动路径（具体、可执行、2-3句话）", "evidence_node_ids": ["支撑你补充的节点ID（如有）"], "risk_or_blind_spot": "G 的理解或你的补充中的风险/盲点（1句话）"}}
必须输出且仅输出一个 JSON。不要解释。不要调用任何工具。

[你的认知人格: Lens-{persona} — {label}]
{cognitive_frame}
{blackboard_block}
"""


class NodeManagementTools:
    """对话记忆管理器 — 负责短期记忆的写入与滑动窗口清理"""

    def __init__(self, vault=None):
        if vault is None:
            from genesis.v4.manager import NodeVault
            vault = NodeVault()
        self.vault = vault

    def store_conversation(self, user_msg: str, agent_response: str):
        """记录 G 的短期记忆（纯时间序列，给 G 起步上下文用的）"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        node_id = f"MEM_CONV_{ts}"
        title = user_msg[:40].replace("\n", " ").strip()
        memory_content = f"用户: {user_msg}\nGenesis: {agent_response}"

        self.vault.create_node(
            node_id=node_id,
            ntype="EPISODE",
            title=title,
            human_translation=f"对话记忆 ({ts})",
            tags="memory,conversation,episode",
            full_content=memory_content,
            source="conversation",
            trust_tier="CONVERSATION"
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
                for nid in to_delete:
                    self.vault.delete_node(nid)
                logger.info(f"NodeManagement: Memory sliding window purged {len(to_delete)} old conversations.")
        except Exception as e:
            logger.error(f"Failed to cleanup old memories: {e}")
