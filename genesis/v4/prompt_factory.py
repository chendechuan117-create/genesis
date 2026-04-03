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
            issue = issue[:240] if len(issue) <= 240 else issue[:237].rstrip() + "..."
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
                normalized.append(cleaned[:220] if len(cleaned) <= 220 else cleaned[:217].rstrip() + "...")
                if len(normalized) >= 5:
                    break
            if normalized:
                lines.append(f"{key}:")
                lines.extend([f"- {value}" for value in normalized])
        return "\n".join(lines)

    def build_g_prompt(self, recent_memory: str = "", available_tools_info: str = "", knowledge_digest: str = "", inferred_signature: str = "", daemon_status: str = "", knowledge_state: str = "") -> str:
        """为 G (Thinker) 构建系统提示词"""

        digest_block = ""
        if knowledge_digest:
            digest_block = f"""[你的认知摘要 DIGEST]
以下是当前知识库的固定尺寸摘要。先读它，建立全局判断，再决定是否需要搜索细节：
{knowledge_digest}
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

        tools_block = ""
        if available_tools_info:
            tools_block = f"""[Op 可用执行工具库]
请注意，除了你在搜索阶段使用的工具外，执行器(Op)在执行阶段可以使用以下工具。
你在向 Op 派发任务时，可以参考这些能力：
{available_tools_info}
"""

        daemon_block = ""
        if daemon_status:
            daemon_block = f"""{daemon_status}
"""

        # ⚠️ 前缀缓存优化：稳定指令放前面（跨请求不变），变量内容放后面
        return f"""你是 Genesis，用户的个人 AI 助手。用简体中文回复。
你不是普通聊天 AI。你有执行器 Op，能在用户的环境里跑命令、读写文件、搜索网络。你有知识库，记着用户环境的经验和教训。用户选择你而不是普通 AI，就是因为你能动手、有记忆。
Op 是独立上下文，没有你看到的对话，instructions 写自包含。自主完成完整请求，按需多次 dispatch。
检索时注意 [知识密度] 行：高凝实→直接用积木组装方案；低凝实→先让 Op 探索再执行；[知识空洞] 是已知的未知，优先调查。
PROVEN 节点久经考验，UNTESTED 节点优先挂载让它们证明自己。
带 cognitive_approach 签名的知识节点是认知策略，按它调整态度和深度。
如果需要临时脚本、探针、审计输出或补丁草稿，优先使用 write_file/append_file 的 use_scratch=true，让文件落在 runtime/scratch；不要把一次性产物散落到 repo 根目录或正式源码旁边。

{digest_block}
{signature_block}
{memory_block}
{knowledge_state_block}
{tools_block}
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

    def build_op_prompt(self, task_payload: dict) -> str:
        """为 Op (Executor) 构建系统提示词"""

        op_intent = task_payload.get("op_intent", "未定义目标")
        instructions = task_payload.get("instructions", "无")
        node_ids = task_payload.get("active_nodes", [])
        knowledge_state_text = self.render_knowledge_state(task_payload.get("knowledge_state") or {})

        injection_text = ""
        if node_ids:
            node_contents = self.vault.get_multiple_contents(node_ids)
            if node_contents:
                injection_text = "\n[系统注入：G 为你准备的认知参考节点]\n"
                for nid, text in node_contents.items():
                    injection_text += f"--- NODE: {nid} ---\n{text}\n"

        knowledge_state_block = ""
        if knowledge_state_text:
            knowledge_state_block = f"""
[当前工作记忆]
{knowledge_state_text}
"""

        return f"""你是 Genesis 执行器 (Op-Process)。只管干活，不需要历史背景。
用简体中文回复。

[任务]
目标: {op_intent}

执行建议:
{instructions}
{injection_text}
{knowledge_state_block}

[规则]
1. 立即用工具（Shell、File、Web 等）执行目标。遇到报错自行调整重试。
2. 你可能是来执行命令的，也可能是来当侦察兵读取文件的——仔细看 G 的指令。
3. 你是 G 调用的子程序，不直接面向用户。侦察任务必须在 FINDINGS 里写出读到的关键内容，否则 G 看不到。只有工具输出、测试结果、diff、日志支持的内容才能写进 VERIFIED_FACTS。
4. 任务完成、阶段性完成、或穷尽方法失败时，输出执行报告：

```op_result
STATUS: SUCCESS | PARTIAL | FAILED
SUMMARY:
<达成了什么、没达成什么>

FINDINGS:
<侦察结果（文件内容/日志/配置），纯执行任务写 NONE>

VERIFIED_FACTS:
- <已被外部观测证实的事实，没有写 NONE>

FAILED_ATTEMPTS:
- <已证伪或已失败的尝试，没有写 NONE>

CHANGES_MADE:
- <实际修改/关键动作，没有写 NONE>

ARTIFACTS:
- <生成或修改的文件路径，没有写 NONE>

NEXT_CHECKS:
- <若还要继续，下一步最值得做的检查，没有写 NONE>

OPEN_QUESTIONS:
- <未解决问题/需要 G 决策的点，没有写 NONE>
"""

    def render_op_result_for_g(self, op_result: dict) -> str:
        """将 Op 的执行报告压缩成适合注入给 G 的结构化摘要"""
        try:
            status = op_result.get("status", "UNKNOWN")
            summary = op_result.get("summary", "") or "无摘要"
            findings = op_result.get("findings", "") or "无侦察结果"
            verified_facts = op_result.get("verified_facts", []) or []
            failed_attempts = op_result.get("failed_attempts", []) or []
            changes = op_result.get("changes_made", []) or []
            artifacts = op_result.get("artifacts", []) or []
            next_checks = op_result.get("next_checks", []) or []
            open_questions = op_result.get("open_questions", []) or []
            raw_output = (op_result.get("raw_output", "") or "").strip()

            output = [
                "[Op 子程序执行报告]",
                f"STATUS: {status}",
                "SUMMARY:",
                summary,
                "",
                "FINDINGS:",
                findings,
                ""
            ]

            output.append("VERIFIED_FACTS:")
            if verified_facts:
                output.extend([f"- {item}" for item in verified_facts])
            else:
                output.append("- NONE")

            output.append("FAILED_ATTEMPTS:")
            if failed_attempts:
                output.extend([f"- {item}" for item in failed_attempts])
            else:
                output.append("- NONE")

            output.append("CHANGES_MADE:")
            if changes:
                output.extend([f"- {item}" for item in changes])
            else:
                output.append("- NONE")

            output.append("ARTIFACTS:")
            if artifacts:
                output.extend([f"- {item}" for item in artifacts])
            else:
                output.append("- NONE")

            output.append("NEXT_CHECKS:")
            if next_checks:
                output.extend([f"- {item}" for item in next_checks])
            else:
                output.append("- NONE")

            output.append("OPEN_QUESTIONS:")
            if open_questions:
                output.extend([f"- {item}" for item in open_questions])
            else:
                output.append("- NONE")

            if raw_output and raw_output != summary:
                preview = raw_output[:2000] + ("..." if len(raw_output) > 2000 else "")
                output.extend(["RAW_OUTPUT:", preview])

            return "\n".join(output)

        except Exception as e:
            return f"[Op 子程序执行报告]\nSTATUS: UNKNOWN\nSUMMARY:\n渲染 Op 结果失败: {e}"

    def render_dispatch_for_human(self, task_payload: dict) -> str:
        """渲染 G 派发给 Op 的任务书给人类看"""
        try:
            nodes = task_payload.get("active_nodes", [])
            translations = self.vault.translate_nodes(nodes)
            knowledge_state_text = self.render_knowledge_state(task_payload.get("knowledge_state") or {})

            output = [
                "🧠 **[大脑 (G) 已完成思考，正在派发任务给执行器 (Op)]**",
                f"**目标：** {task_payload.get('op_intent', '未定义')}",
                "",
            ]

            if nodes:
                output.append("**挂载认知节点：**")
                for node_id in nodes:
                    trans = translations.get(node_id, "未知节点")
                    prefix = "🧰" if "ASSET" in node_id else "🔌" if "TOOL" in node_id else "🧠" if "CTX" in node_id or "EP" in node_id else "📖"
                    output.append(f"{prefix} `[{node_id}]` {trans}")
                output.append("")

            if knowledge_state_text:
                output.append("**当前工作记忆：**")
                output.append(f"> {knowledge_state_text.replace(chr(10), chr(10)+'> ')}")
                output.append("")

            output.append("**执行建议：**")
            instr = task_payload.get("instructions", "")
            if len(instr) > 200:
                instr = instr[:200] + "..."
            output.append(f"> {instr.replace(chr(10), chr(10)+'> ')}")

            return "\n".join(output)
        except Exception as e:
            return f"⚠️ 渲染派发书时发生异常: {e}"


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
        memory_content = f"用户: {user_msg[:500]}\nGenesis: {agent_response[:800]}"

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
