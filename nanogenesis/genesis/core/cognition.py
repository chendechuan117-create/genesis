
import logging
import json
import time
from typing import Dict, Any, List, Optional, Callable

logger = logging.getLogger(__name__)

class CognitiveProcessor:
    """
    Handles the high-level cognitive phases:
    1. Awareness (Oracle) - Intent Recognition
    2. Strategy (Strategist) - Planning
    3. Consolidation (Learner) - Memory Synthesis
    """
    
    def __init__(
        self, 
        chat_func: Callable, 
        memory: Any,
        intent_prompt: Optional[str] = None,
        meta_protocol: Optional[str] = None,
        tools_registry: Any = None
    ):
        self.chat = chat_func
        self.memory = memory
        self.intent_prompt = intent_prompt
        self.meta_protocol = meta_protocol
        self.tools = tools_registry

    async def awareness_phase(
        self,
        user_input: str,
        recent_context: list = None,   # 最近 N 条对话记录 [{"role": ..., "content": ...}]
    ) -> Dict[str, Any]:
        """第一人格：洞察者 (The Oracle) - 意图识别与资源扫描"""
        if not self.intent_prompt:
            return {"core_intent": "General Request", "problem_type": "general", "resource_map": {}}
            
        # 填充模板
        prompt = self.intent_prompt.replace("{{user_input}}", user_input)
        
        # 构建消息列表：先注入近期对话历史作为锚点，再发出意图解析请求
        messages = []
        if recent_context:
            # 把最近几条对话放在前面，作为 Oracle 的上下文锚点
            for msg in recent_context:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if content and role in ("user", "assistant"):
                    messages.append({"role": role, "content": str(content)[:600]})
        messages.append({"role": "user", "content": prompt})
        
        try:
            # 这是一个轻量级调用
            response = await self.chat(
                messages=messages,
                response_format={"type": "json_object"} if "json" in prompt.lower() else None
            )

            
            # 解析 JSON 输出
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                result = {"core_intent": "Parsing Error", "raw": content}
            
            # --- QMD Memory Enrichment ---
            memory_hits = []
            if result.get("memory_keywords") and self.memory:
                keywords = result["memory_keywords"]
                # 执行记忆拉取
                queries = keywords if isinstance(keywords, list) else [keywords]
                for q in queries:
                    hits = await self.memory.search(q, limit=3)
                    memory_hits.extend(hits)
            
            # 去重并排序
            # SQLiteMemoryStore returns 'content' and 'metadata', not always 'path'
            unique_hits = {h.get('content_hash', h.get('content')): h for h in memory_hits}.values()
            result["memory_pull"] = sorted(unique_hits, key=lambda x: x['score'], reverse=True)[:5]
            
            # --- Decision Cache Enrichment ---
            decision_hits = []
            queries_for_decision = (queries if 'queries' in locals() else [user_input])
            
            if self.memory:
                for q in queries_for_decision:
                     d_hits = await self.memory.search(q, limit=2, collection="_decisions")
                     decision_hits.extend(d_hits)
            
            unique_decisions = {h.get('content_hash', h.get('content')): h for h in decision_hits}.values()
            formatted_decisions = []
            for d in unique_decisions:
                meta = d.get('metadata', {})
                if isinstance(meta, str):
                    try: meta = json.loads(meta)
                    except: meta = {}
                    
                formatted_decisions.append({
                    "insight": meta.get("insight", ""),
                    "outcome": meta.get("outcome", ""),
                    "action": meta.get("action", "")
                })
            result["decision_history"] = formatted_decisions[:3]
            
            return result
        except Exception as e:
            logger.warning(f"洞察阶段失败: {e}")
            return {"core_intent": user_input[:30], "problem_type": "general", "resource_map": {}}

    async def strategy_phase(
        self, 
        user_input: str, 
        oracle_output: Dict[str, Any], 
        user_context: str = None,
        adaptive_stats: Dict = None,
        active_mission: Any = None, # Mission object
        mission_lineage: List[Any] = None, # List[Mission]
        world_model: Dict[str, Any] = None, # World Model Snapshot
        active_jobs: List[Any] = None, # List[Job Dict]
        entropy_analysis: Dict[str, Any] = None # New: Entropy Report
    ) -> str:
        """第二人格：裁决者 (The Strategist) - 元认知战略制定"""
        if not self.meta_protocol:
            return ""
            
        # 1. 填充工具描述
        tools_desc = []
        if self.tools:
            for tool in self.tools.get_definitions():
                tools_desc.append(f"- {tool['function']['name']}: {tool['function']['description']}")
        tools_str = "\n".join(tools_desc)
        
        # 2. 填充决策经验
        decisions = oracle_output.get("decision_history", [])
        dec_str = ""
        if decisions:
            dec_str = "历史相似决策参考：\n"
            for d in decisions:
                dec_str += f"- [经验] {d.get('insight')} (结果: {d.get('outcome')})\n"
        else:
            dec_str = "暂无相关历史决策经验。"

        # 3. 填充 Mission Context Tree (MCT)
        mission_ctx_str = ""
        if mission_lineage:
            mission_ctx_str = "\n[MISSION CONTEXT TREE]\n"
            for i, m in enumerate(mission_lineage):
                prefix = "  " * i + "└─ " if i > 0 else "ROOT: "
                status_icon = "🟢" if m.status == 'active' else "🔴"
                mission_ctx_str += f"{prefix}{status_icon} [{m.id[:4]}] {m.objective}\n"
            
        if active_mission:
                mission_ctx_str += f"\nCURRENT FOCUS (Depth {active_mission.depth}): {active_mission.objective}"
        
        world_model_str = ""
        if world_model:
            world_model_str = "\n[WORLD MODEL SCAN]\n"
            world_model_str += f"- OS: {world_model.get('os')}\n"
            world_model_str += f"- Network: {world_model.get('network')}\n"
            world_model_str += f"- Permissions: {world_model.get('permissions')}\n"
            
            adb = world_model.get('adb', {})
            adb_status = "Installed" if adb.get('installed') else "Missing"
            devices = ", ".join(adb.get('devices', [])) if adb.get('devices') else "None"
            world_model_str += f"- ADB Status: {adb_status} | Devices: [{devices}]\n"
            
            tools_map = world_model.get('tools', {})
            pkg_mgr = tools_map.get('package_manager')
            if pkg_mgr:
                world_model_str += f"- Package Manager: {pkg_mgr}\n"
                
            missing_tools = [k for k, v in tools_map.items() if v == 'Missing' and k != 'package_manager']
            if missing_tools:
                world_model_str += f"- Missing Tools: {', '.join(missing_tools)}\n"
            else:
                world_model_str += "- Critical Tools: All Check OK\n"

        # 4. Physiological Signal (Entropy Integration)
        physio_signal = ""
        if entropy_analysis:
            status = entropy_analysis.get("status", "unknown")
            rep_count = entropy_analysis.get("repetition_count", 0)
            window = entropy_analysis.get("window_size", 0)
            
            if status == "stagnant":
                physio_signal = f"\n[PHYSIOLOGICAL SIGNAL - CRITICAL]\n⚠️ High Entropy Stagnation Detected (Repetitions: {rep_count}/{window}).\n- You are repeating the EXACT SAME state/output.\n- If you are POLLING, this is acceptable (verify condition changes).\n- If you are LOOPING/STUCK, you MUST change strategy or STOP immediately.\n"
            elif status == "stable":
                physio_signal = f"\n[PHYSIOLOGICAL SIGNAL - WARNING]\n⚠️ Stable Entropy Detected (Repetitions: {rep_count}/{window}).\n- Be aware of potential looping behavior.\n"

        # 5. Populate Active Jobs (Async System)
        active_jobs_str = ""
        if active_jobs:
             active_jobs_str = "\n[ACTIVE BACKGROUND JOBS]\n"
             for j in active_jobs:
                 active_jobs_str += f"- ID: {j['id']} | Cmd: {j['command']} | Status: {j['status']}\n"

        full_context = user_context or ""
        context_parts = []
        if physio_signal: context_parts.append(physio_signal) # Top Priority Signal
        if world_model_str: context_parts.append(world_model_str)
        if active_jobs_str: context_parts.append(active_jobs_str) # Add Jobs
        if mission_ctx_str: context_parts.append(mission_ctx_str)
        if full_context: context_parts.append(full_context)
        
        final_context = "\n\n".join(context_parts)

        protocol_filled = self.meta_protocol.replace("{{oracle_output}}", str(oracle_output))\
                                          .replace("{{problem}}", user_input)\
                                          .replace("{{context}}", final_context)\
                                          .replace("{{user_profile}}", str(adaptive_stats or {}))\
                                          .replace("{{decision_experience}}", dec_str)\
                                          .replace("{{tools}}", tools_str)
        
        try:
            # 战略制定调用
            response = await self.chat(
                messages=[{"role": "user", "content": protocol_filled}]
            )
            return response.content
        except Exception as e:
            logger.warning(f"战略阶段失败: {e}")
            return "Proceed with caution and follow standard ReAct instructions."

    async def consolidate_memory(self, user_input: str, response: str, metrics: Any = None):
        """记忆整合协议 (Memory Consolidation Protocol)"""
        if not self.memory:
            return

        # 1. 快速过滤 (Heuristic)
        if len(user_input) < 5 or len(response) < 10:
            return
            
        # 2. 元评价与决策提取
        eval_prompt = f"""
Analyze the following interaction to extract a "Decision Event" (AX-Pair).

User Query: {user_input}
Assistant Response: {response}

Tasks:
1. Rate Significance (0-10) based on complexity and novelty.
2. If Score >= 7, define the Decision Event:
   - Situation (S): The core problem and system context.
   - Action (A): The specific solution path or tool sequence chosen.
   - Outcome (R): 'success', 'fail', or 'partial'.
   - Insight: The key pattern or rule learned for future similar situations.

Output JSON only:
{{
    "score": int,
    "reason": "short explanation",
    "decision": {{
        "situation": "S",
        "action": "A",
        "outcome": "success/fail/partial",
        "insight": "key learned pattern"
    }}
}}
"""
        try:
            eval_response = await self.chat(messages=[{"role": "user", "content": eval_prompt}])
            
            content = eval_response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            try:
                result = json.loads(content)
            except:
                return
            
            if result.get("score", 0) >= 7:
                dec = result.get("decision", {})
                if dec:
                    if hasattr(self.memory, 'add_decision'):
                        # Support for legacy QmdMemory method directly if using qmd_memory.py
                         await self.memory.add_decision(
                            situation=dec.get("situation", user_input),
                            action=dec.get("action", ""),
                            outcome=dec.get("outcome", "success"),
                            insight=dec.get("insight", ""),
                            cost={"tokens": getattr(metrics, 'total_tokens', 0) if metrics else 0}
                        )
                    else:
                        # Fallback for generic MemoryStore
                         await self.memory.add(
                            content=f"Decision: {dec.get('insight')}",
                            metadata={
                                "type": "decision",
                                "situation": dec.get("situation"),
                                "action": dec.get("action"),
                                "outcome": dec.get("outcome"),
                                "insight": dec.get("insight"),
                                "collection": "_decisions"
                            }
                        )
                    logger.info(f"🧠 决策流形已更新: {dec.get('insight', 'New Pattern')}")
        except Exception as e:
            logger.warning(f"记忆整合失败: {e}")
