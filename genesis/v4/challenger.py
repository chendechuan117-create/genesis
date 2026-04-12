"""
Genesis V4 - Challenger Mixin（路径效率审查）

C-Phase 后台并发的第二轮 LLM 调用，审查 GP 执行路径的效率。
与 Knowledge Extraction（提取声明性知识 LESSON）互补：
  - Extraction 问："学到了什么？"
  - Challenger 问："路径是最短的吗？"

产出 METHOD_REVIEW 类型的 LESSON 节点，通过 Knowledge Map 自然流向下次 GP。
GP 自主决定是否采纳，正循环靠知识流动驱动，不靠指令。

V4Loop 通过 Mixin 继承获得这些方法，由 CPhaseMixin._run_c_phase 调用。
"""

import re
import json
import hashlib
import logging
from typing import Any, Dict

from genesis.core.base import MessageRole

logger = logging.getLogger(__name__)


class ChallengerMixin:
    """Challenger 路径审查方法集合。通过 Mixin 注入 V4Loop。

    依赖 V4Loop 的属性：
    - self.vault, self.provider
    - self.g_messages, self._op_tool_outcomes, self.metrics
    - self.user_input, self.trace_id
    - self._update_metrics
    - self.tools (ToolRegistry, for available-tools list)
    """

    def _build_challenger_input(self, g_final_response: str) -> str:
        """构建 Challenger 审查的结构化输入：执行摘要 + 效率指标 + 可用工具 + 已有规则。"""
        from collections import Counter
        parts = []

        # 1. 任务上下文
        parts.append(f"[任务] {self.user_input[:300]}")
        if g_final_response:
            parts.append(f"[GP回复] {g_final_response[:400]}")

        # 2. 工具调用分布（含失败次数）
        if self._op_tool_outcomes:
            tool_counts = Counter(o["tool"] for o in self._op_tool_outcomes)
            fail_counts = Counter(o["tool"] for o in self._op_tool_outcomes if not o["success"])
            lines = []
            for tool_name, count in tool_counts.most_common():
                fail = fail_counts.get(tool_name, 0)
                suffix = f" ({fail}次失败)" if fail else ""
                lines.append(f"  {tool_name}: {count}次{suffix}")
            parts.append(f"[工具调用分布] (共 {len(self._op_tool_outcomes)} 次)\n" + "\n".join(lines))

        # 3. 效率指标
        rounds = sum(1 for m in self.g_messages if m.role == MessageRole.ASSISTANT and m.content)
        total_tokens = self.metrics.total_tokens
        parts.append(f"[效率指标] GP轮数: {rounds}, 总token: {total_tokens}")

        # 4. 失败/重试模式（连续失败 ≥2 次的序列）
        if self._op_tool_outcomes:
            consecutive_fails = []
            current_streak = []
            for o in self._op_tool_outcomes:
                if not o["success"]:
                    current_streak.append(o["tool"])
                else:
                    if len(current_streak) >= 2:
                        consecutive_fails.append(f"  连续失败: {' → '.join(current_streak)}")
                    current_streak = []
            if len(current_streak) >= 2:
                consecutive_fails.append(f"  连续失败: {' → '.join(current_streak)}")
            if consecutive_fails:
                parts.append("[失败/重试模式]\n" + "\n".join(consecutive_fails))

        # 5. GP 可用工具列表（名称 + 一行描述）
        try:
            tool_descs = []
            for name in self.tools.list_tools():
                tool = self.tools.get(name)
                if tool:
                    desc_line = (tool.description or "").split('\n')[0][:80]
                    tool_descs.append(f"  {name}: {desc_line}")
            if tool_descs:
                parts.append("[GP可用工具列表]\n" + "\n".join(sorted(tool_descs)))
        except Exception:
            pass

        # 6. 已有效率规则（Challenger 不应重复这些）
        existing_rules = [
            "- shell 仅用于系统命令和无专用工具的操作",
            "- 读文件用 read_file | 写文件用 write_file | 查目录用 list_directory",
            "- 知识搜索用 search_knowledge_nodes，不要用 shell + sqlite3",
            "- 环境问题用 trace_query(mode='recall') 回忆经验",
        ]
        parts.append("[已有效率规则（不要重复这些）]\n" + "\n".join(existing_rules))

        # 7. 最近 METHOD_REVIEW（防重复建议）
        try:
            rows = self.vault._conn.execute(
                "SELECT title FROM knowledge_nodes WHERE tags LIKE '%method_review%' "
                "ORDER BY created_at DESC LIMIT 5"
            ).fetchall()
            if rows:
                mr_lines = [f"  - {r[0]}" for r in rows]
                parts.append("[最近的方法审查建议（不要重复）]\n" + "\n".join(mr_lines))
        except Exception:
            pass

        return "\n\n".join(parts)

    async def _run_challenger_review(self, g_final_response: str) -> Dict[str, Any]:
        """Challenger: 审查执行路径效率，产出 METHOD_REVIEW 知识。

        与 _run_discovery_recording 并发运行（asyncio.gather），不增加墙钟时间。
        输出 PASS（路径已足够高效）或具体建议（写入 NodeVault）。
        """
        # SKIP 条件：工具调用太少，无审查价值
        if len(self._op_tool_outcomes) < 3:
            return {"status": "skipped", "reason": "too_few_tool_calls", "challenger_tokens": 0}

        challenger_input = self._build_challenger_input(g_final_response)

        system_prompt = (
            "你是路径审查者。你的唯一任务是审查执行路径的效率。"
            "不要夸奖，不要复述已有规则。只输出 PASS 或 JSON。"
        )

        user_prompt = (
            f"{challenger_input}\n\n"
            "---\n\n"
            "审查要求：\n"
            "1. 这个执行路径有没有明显低效？具体到工具名和次数。\n"
            "2. 可用工具列表中，有没有更适合的工具没被使用？\n"
            "3. 如果现有工具都不合适，是否应该创建一个新的专用工具？\n"
            "4. 如果你来做同样的任务，具体会怎么做不同？\n\n"
            "输出格式（三选一）：\n"
            '- 路径已高效：输出 "PASS"\n'
            "- 行为建议（用现有工具更好的方式）：\n"
            '  {"type":"method_review","pattern":"任务模式","inefficiency":"低效描述含数字",'
            '"suggestion":"替代方案含工具名","expected_improvement":"预期改善"}\n'
            "- 工具创建（现有工具无法覆盖，需新工具）：\n"
            '  {"type":"tool_proposal","tool_name":"小写字母和下划线","description":"工具用途",'
            '"pattern":"触发场景","parameters":{"param1":{"type":"string","description":"..."}},'
            '"python_code":"完整的 Tool 子类源码，必须包含 class + name/description/parameters/execute"}\n'
            "注意：\n"
            "- 不要泛泛而谈。没有数字支撑的建议 = 无效建议。\n"
            "- tool_proposal 的 python_code 必须是可直接执行的完整 Tool 子类。\n"
            "- 不需要 import Tool，系统会自动注入。\n"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await self.provider.chat(
                messages=messages,
                tools=None,
                stream=False,
                _trace_id=getattr(self, 'trace_id', None),
                _trace_phase="C",
            )
            self._update_metrics(response, phase="C")
            challenger_tokens = getattr(response, 'total_tokens', 0)

            content = (response.content or "").strip()

            # PASS = 路径已足够高效
            if content.upper().startswith("PASS"):
                return {"status": "pass", "challenger_tokens": challenger_tokens}

            # 解析 JSON 建议
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if not json_match:
                logger.info(f"Challenger: non-JSON response, treating as pass: {content[:100]}")
                return {"status": "pass", "challenger_tokens": challenger_tokens, "raw": content[:200]}

            suggestion = json.loads(json_match.group())
            if not isinstance(suggestion, dict):
                return {"status": "pass", "challenger_tokens": challenger_tokens, "reason": "invalid_json"}

            proposal_type = suggestion.get("type", "method_review")

            # ── TOOL_PROPOSAL: 结构性改进（创建新工具）──
            if proposal_type == "tool_proposal":
                return await self._write_tool_proposal(suggestion, challenger_tokens)

            # ── METHOD_REVIEW: 行为建议（现有逻辑）──
            if "suggestion" not in suggestion:
                return {"status": "pass", "challenger_tokens": challenger_tokens, "reason": "no_suggestion"}

            title = str(suggestion.get("suggestion", ""))[:100]
            if not title:
                return {"status": "pass", "challenger_tokens": challenger_tokens, "reason": "empty_suggestion"}

            node_id = f"LESSON_{hashlib.md5(('challenger:' + title).encode()).hexdigest()[:8].upper()}"
            pattern = str(suggestion.get("pattern", ""))[:100]
            inefficiency = str(suggestion.get("inefficiency", ""))[:300]
            expected = str(suggestion.get("expected_improvement", ""))[:200]

            mr_content = json.dumps({
                "IF_trigger": {"verb": "执行", "noun": pattern or "任务", "context": f"路径审查发现低效: {inefficiency}"},
                "THEN_action": [title],
                "BECAUSE_reason": f"Challenger审查: {inefficiency}。预期改善: {expected}",
            }, ensure_ascii=False, indent=2)

            try:
                self.vault.create_node(
                    node_id=node_id,
                    ntype="LESSON",
                    title=title,
                    human_translation=title,
                    tags="method_review",
                    full_content=mr_content,
                    source="challenger",
                    resolves=f"路径效率: {pattern}",
                    metadata_signature={"source": "challenger", "task_kind": pattern},
                    trust_tier="REFLECTION",
                )
                logger.info(f"Challenger: wrote METHOD_REVIEW → {node_id}: {title}")
                return {
                    "status": "suggestion",
                    "challenger_tokens": challenger_tokens,
                    "node_id": node_id,
                    "suggestion": suggestion,
                }
            except Exception as e:
                logger.warning(f"Challenger: failed to write suggestion: {e}")
                return {
                    "status": "suggestion_write_failed", "challenger_tokens": challenger_tokens,
                    "suggestion": suggestion, "error": str(e),
                }

        except Exception as e:
            logger.warning(f"Challenger review failed (non-fatal): {e}")
            return {"status": "error", "challenger_tokens": 0, "error": str(e)}

    async def _write_tool_proposal(self, suggestion: dict, challenger_tokens: int) -> Dict[str, Any]:
        """将 Challenger 的 tool_proposal 写入 vault 作为 TOOL 节点。

        activate_vault_tools() 会在下一轮自动加载它。
        """
        tool_name = str(suggestion.get("tool_name", "")).strip()
        python_code = str(suggestion.get("python_code", "")).strip()
        description = str(suggestion.get("description", ""))[:200]
        pattern = str(suggestion.get("pattern", ""))[:100]

        if not tool_name or not python_code:
            logger.info("Challenger: tool_proposal missing tool_name or python_code")
            return {"status": "tool_proposal_invalid", "challenger_tokens": challenger_tokens}

        # 安全检查：必须包含 Tool 子类定义
        if "class" not in python_code or "execute" not in python_code:
            logger.info(f"Challenger: tool_proposal '{tool_name}' code lacks class/execute")
            return {"status": "tool_proposal_invalid", "challenger_tokens": challenger_tokens, "reason": "no_class_or_execute"}

        # 预检：调用 registry 的 AST 审计（不实际注册）
        from genesis.core.registry import tool_registry
        reject_reason = tool_registry._audit_source_safety(python_code, tool_name)
        if reject_reason:
            logger.warning(f"Challenger: tool_proposal '{tool_name}' rejected by safety audit: {reject_reason}")
            return {"status": "tool_proposal_rejected", "challenger_tokens": challenger_tokens, "reason": reject_reason}

        # 跳过已存在的同名工具
        if tool_name in self.tools:
            logger.info(f"Challenger: tool_proposal '{tool_name}' already registered, skip")
            return {"status": "tool_already_exists", "challenger_tokens": challenger_tokens}

        node_id = f"TOOL_{hashlib.md5(('challenger:' + tool_name).encode()).hexdigest()[:8].upper()}"

        try:
            self.vault.create_node(
                node_id=node_id,
                ntype="TOOL",
                title=description or f"动态工具: {tool_name}",
                human_translation=f"Python工具: {tool_name}",
                tags=f"tool,python,challenger,{pattern}".replace(" ", "_")[:100],
                full_content=python_code,
                source="challenger",
                resolves=f"工具缺口: {pattern}",
                metadata_signature={"source": "challenger", "task_kind": pattern},
                trust_tier="REFLECTION",
            )
            logger.info(f"Challenger: wrote TOOL_PROPOSAL → {node_id}: {tool_name} ({description[:60]})")
            return {
                "status": "tool_proposed",
                "challenger_tokens": challenger_tokens,
                "node_id": node_id,
                "tool_name": tool_name,
            }
        except Exception as e:
            logger.warning(f"Challenger: failed to write tool proposal: {e}")
            return {"status": "tool_proposal_write_failed", "challenger_tokens": challenger_tokens, "error": str(e)}
