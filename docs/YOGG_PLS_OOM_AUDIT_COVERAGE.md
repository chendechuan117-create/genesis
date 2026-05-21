# Yogg PLS OOM Audit Coverage Notes

Date: 2026-05-14

## Purpose

This note preserves the current read-only audit model for the Yogg PLS self-observation feedback loop that caused OOM/token/report bloat. It is intentionally a causal coverage record, not a patch plan or implementation diff.

## Core Finding

The failure is not a single `auto_report` replay problem. It is a multi-surface feedback loop where runtime message history, report serialization, short-term conversation memory, PLS terrain signals, and cross-round active-node cursoring reinforce each other.

The minimum complete causal model has five feedback surfaces:

1. Runtime message surface: `g_messages` keeps full tool results inside the same GP round.
2. Report surface: `phase_trace.inferred_signature` expands through nested/list/stringified signature fields.
3. Short-term memory surface: `MEM_CONV_*` stores full auto prompts and final responses, then `get_recent_memory()` injects recent full memories into GP system prompts.
4. PLS terrain surface: `potential_samples`, terrain scout, saturation/co-presence/frontier samples repeatedly expose self-generated possibilities.
5. Graph cursor surface: `GenesisV4._knowledge_cursor` carries active nodes into the next round and reuses them as knowledge-routing seeds.

## Verified Non-Cause

Whole `auto_report` JSON files do not appear to be automatically replayed into the next round.

`auto_mode` writes round JSON reports, but session restoration uses lightweight fields such as `last_frontier`, `last_knowledge_state`, planner state, and shown-node/void sets. Large `phase_trace` objects are persisted in reports but are not directly restored by the auto session memory mechanism.

However, reports can still become a manual/tool-level pollution source if Yogg explicitly reads `runtime/auto_reports` with tools.

## Report Bloat Path

Large reports are primarily caused by `phase_trace.inferred_signature`, not by GP message trace arrays.

Observed remote report sizes showed cases where:

- `phase_trace` was nearly the whole report.
- `phase_trace.inferred_signature` was nearly the whole `phase_trace`.
- `phase_trace.gp` stayed small because `get_phase_trace()` truncates message/tool content.

The likely mechanism is repeated merge/normalization of signature fields, especially `environment_scope` and `applies_to_environment_scope`, where list-like values are repeatedly converted to strings and then merged back as values, producing nested stringified lists.

Relevant code paths:

- `V4Loop._merge_signature_from_texts()` merges inferred signatures from tool result text.
- `V4Loop._merge_signature_from_nodes()` merges signatures expanded from active nodes.
- `V4Loop.get_phase_trace()` serializes `self.inferred_signature` without field-level budget.
- environment scope binding writes resolved scope values back to both `applies_to_environment_scope` and `environment_scope`.

Required coverage if fixed later:

- Hard type normalization for signature fields.
- Defensive parsing/rejection of stringified lists for scope fields.
- Field-level budget before `phase_trace` serialization.
- Regression check for nested `environment_scope`/`applies_to_environment_scope` values.

## Single-Round Token/OOM Path

The strongest single-round token amplifier is `g_messages`.

Current behavior:

1. GP sends `messages_to_send = [m.to_dict() for m in self.g_messages] + [jailbreak]`.
2. Tool results are appended as `MessageRole.TOOL(content=res_text)` with full result text.
3. The next GP LLM call receives all previous full tool results in the same round.
4. The evaporation/digestion mechanism is removed, so context growth relies on provider context limits instead of explicit memory metabolism.

This explains million-token-scale rounds independently of `auto_report` replay.

Required coverage if fixed later:

- Tool-result digestion before appending to `g_messages`.
- Preserve full raw result outside prompt-visible history if needed for audit.
- Keep structured handles/previews in GP context, not full bulk data.
- Add prompt-visible budget accounting before each LLM call.

## Cross-Round Memory Feedback

A previously under-covered path is `MEM_CONV_*` short-term memory.

Current behavior:

1. At the end of a V4 loop, `_save_memory(final_response)` is called.
2. `NodeManagementTools.store_conversation()` stores `user_msg` and `agent_response` as `MEM_CONV_*` full content.
3. In auto mode, `user_msg` is the full `[GENESIS_USER_REQUEST_START]` prompt, including auto instructions, `knowledge_state`, `frontier_state`, signals, PLS terrain, and history snippets.
4. The next GP system prompt calls `get_recent_memory(limit=5)`.
5. `get_recent_memory()` injects recent memory full contents without compression.

Remote DB verification showed recent `MEM_CONV_*` entries around 8.5KB-11.3KB each, containing full auto prompts such as "继续自主概念探索" and previous working-memory content. The sliding window keeps the table small, but the prompt injection can still add tens of KB every round.

Required coverage if fixed later:

- Auto mode must not store full auto prompts as conversation memory.
- Store a compact digest instead: directive summary, durable outcome, confirmed nodes/lines, unresolved issue.
- Strip boilerplate, signals, PLS terrain, raw frontier text, raw knowledge_state text, and history blocks.
- `get_recent_memory()` should inject digests or bounded summaries, not full `full_content`.

## Knowledge Cursor Feedback

Another under-covered path is cross-round `knowledge_cursor`.

Current behavior:

1. `GenesisV4` stores `_knowledge_cursor` as an instance field.
2. Each `process()` passes the previous cursor into `V4Loop.run()`.
3. The loop exports `active_node_ids` through `export_knowledge_cursor()`.
4. The next round can route from the cursor with `_route_from_cursor()`.
5. Cursor-routed nodes are expanded by `SurfaceExpander`, rendered into context, added to `execution_active_nodes`, and can receive usage increments in C-phase.

Feedback loop:

```text
execution_active_nodes
→ export_knowledge_cursor
→ GenesisV4._knowledge_cursor
→ next-round _route_from_cursor
→ SurfaceExpander
→ execution_active_nodes
→ C-phase increment_usage
→ more apparent relevance
```

Required coverage if fixed later:

- Cursor TTL and topic-drift reset.
- Do not export cursor after timeout/error/high-token rounds.
- Export only explicitly cited/basis-used nodes, not all preloaded nodes.
- Distinguish preloaded, searched, cited, and basis-used active node roles.
- Cursor-routed nodes should not automatically count as successful usage.

## Frontier and Knowledge-State Feedback

`frontier_state` and `knowledge_state` create a language-level continuation loop.

Current behavior:

- `_extract_candidate_issue()` extracts an issue from the prior final response.
- `_build_frontier_state()` creates observations, warnings, and next checks.
- `_build_auto_knowledge_state()` prioritizes frontier issue/candidate issue.
- `AUTO_PROMPT_CONTINUE` injects formatted working memory and frontier state into the next round.

Remote memory preview confirmed closure-like statements such as "本轮已到位，收束" and "本轮核心发现已锚定，收束" appearing as subsequent `issue` material.

Required coverage if fixed later:

- Treat closure statements as closed topics, not next-round issue seeds.
- Only unresolved questions or explicit next checks should become `knowledge_state.issue`.
- Track `closed_topics` separately from `failed_attempts`.
- Avoid converting "no durable outcome" warnings into an instruction to keep analyzing the same object.

## PLS Terrain and Potential Feedback

Remote aggregate observations showed:

- `potential_samples` is the thick table and main PLS attention fuel.
- `void_tasks` exists but is not the dominant self-attractor.
- `pls_proposals` was empty in the observed remote database.

`SurfaceExpander` generates potential samples from co-presence, saturation, missing basis, and frontier pressure. Knowledge routing and searches record these samples. Auto signals and PLS scout can expose potential/frontier/saturation content back to GP as candidate attention objects.

Required coverage if fixed later:

- Separate actionable/exit potentials from structural/co-presence/saturation samples.
- Add lifecycle states and decay for recurring non-actionable potentials.
- Do not inject raw recurring structural potential into prompt every round.
- Mark cursor-routed potential separately to prevent self-reinforcing recurring samples.

## Usage Attribution Feedback

`usage_count` is exposure-biased rather than proof of semantic utility.

Current behavior:

- `execution_active_nodes` includes preloaded/rendered nodes, not only nodes actually used as reasoning basis.
- C-phase increments usage for unique active nodes.
- Success/failure outcome is assigned at the round level from tool outcomes, not per-node causal contribution.

This can turn being shown into being counted as used, and being present in a successful round into apparent practical value.

Required coverage if fixed later:

- Split node activity roles: preloaded, searched, opened, cited, basis-used, written-against.
- Only explicit citation/basis use should influence success/fail attribution.
- Preloaded-only nodes may receive exposure telemetry but not utility credit.

## C-Gardener Feedback

C-Gardener is not the main OOM source, but it is a self-observation-to-graph channel.

Its reflection input includes:

- Full user input, which in auto mode is the full auto prompt.
- Full GP final response.
- Recent assistant reasoning snippets.
- Knowledge writes.
- Tool interaction previews.
- Related vault knowledge.
- Active nodes.
- Inferred signature.
- Cross-round observations.

Tool results are summarized for C, so this is less dangerous than `g_messages`, but it can still convert auto self-observation into graph edges.

Required coverage if fixed later:

- Do not pass full auto prompt as C task text.
- Use a compact auto-task digest.
- Audit C-created edges for self-observation loops.

## Minimum Complete Treatment Set

A complete treatment must cover all of the following, not just report size or rate limiting:

1. Tool result context digestion.
2. Hard signature normalization and phase-trace field budgets.
3. Auto conversation-memory sanitization.
4. Knowledge cursor lifecycle and active-node attribution split.
5. Closure semantics for `frontier_state`/`knowledge_state`.
6. Potential sample lifecycle and prompt filtering.
7. Usage attribution split between exposure and actual reasoning use.

## Confidence

High confidence:

- Report bloat is dominated by `phase_trace.inferred_signature`.
- Single-round token bloat is dominated by full tool results in `g_messages`.
- Whole `auto_report` is not automatically restored by session memory.
- `MEM_CONV_*` creates a real cross-round full-prompt feedback path.
- `knowledge_cursor` creates a real active-node continuity path.
- `potential_samples` is the dominant PLS attention-fuel table.

Medium confidence:

- C-Gardener materially amplifies the loop through edges. The input path is clear, but the actual edge distribution still needs a separate quantitative audit.

## Current Status

No production code changes have been made for this audit note. This file only preserves the causal model and coverage checklist for future work.
