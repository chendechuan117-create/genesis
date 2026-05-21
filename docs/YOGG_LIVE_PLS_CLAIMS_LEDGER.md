# Yogg Live PLS Claims Ledger

## Scope

This ledger records claims extracted from the live Yogg/Genesis system on Yoga, not from local snapshot databases or design documents.

Source used for this pass:

```text
host: yoga
db: /home/yoga/.genesis/workshop_v4.sqlite
extracted_at_context: 2026-05-14 live read-only audit
```

Observed live scale at extraction time:

```text
knowledge_nodes: 6063
node_contents: 6070
reasoning_lines: 8978
node_edges: 10018
point_creation_context: 3765
potential_samples: 31104
pls_proposals: 0
void_tasks: 848
ablation_baselines: 950
```

This document treats Yogg as the primary long-running thinker. The purpose is not to overwrite its conclusions with an external summary, but to track claim lifecycle:

- `STABLE`: supported by live node content plus reasoning-line continuity, with no observed later reversal in this pass.
- `REFINED`: an initial claim remains useful, but later Yogg nodes refine the mechanism or scope.
- `CONTESTED`: later Yogg reasoning directly challenges the causal interpretation.
- `DEAD_CHANNEL`: schema or channel exists but is not live semantic content.

## High-level reading

The strongest live PLS content is not a general theory of PLS. It is Yogg's growing evidence that many of its own observability surfaces are narrative fields being consumed as facts:

```text
conversation history -> system prompt fossil
verification timestamp -> write-side claim
health metric -> write activity proxy
usage count -> recommendation / broadcast / collision mixture
void task -> retrieval failure / malformed reference / real gap mixture
CONTRADICTS edge -> short-horizon attention or correction rhetoric
state table -> stale snapshot claim
```

The engineering rule implied by the stable claims is: fields that Yogg has shown to be narrative claims must not remain in fact positions in prompts, ranking, health, or governance logic.

## Claim lifecycle ledger

### 1. Memory and prompt-history pollution

Status: `STABLE`

Primary live nodes:

- `P_7C12D3B0F2` — `MEM_CONV 是系统剧本的叙事化石不是用户-GP 对话的忠实转录：0.3% 用户输入 + 99.7% auto_mode 注入`
- `P_EPISODE_IS_TRIGGER_FOSSIL_NOT_CONVERSATION_TURN` — `用户请求是单向注入不是对话轮次：EPISODE 是触发器化石不是对话参与者`

Claim:

```text
MEM_CONV and EPISODE do not faithfully represent user-GP conversation history.
They preserve trigger/context fossils and auto_mode injection frames.
```

Live evidence recorded by Yogg:

- `MEM_CONV` user raw input is reported as only `0.3%` of characters.
- auto_mode injected material is reported as `99.7%` of characters, approximately `324x` raw user input.
- `carry_warnings` appear in `MEM_CONV`, but not in raw user input.
- Modern `EPISODE` nodes are largely not used as reasoning bases: the node claims `10` modern EPISODE nodes have no meaningful causal connection into LESSON production.

Reasoning-line lifecycle:

- `P_EPISODE_IS_TRIGGER_FOSSIL_NOT_CONVERSATION_TURN` is used as a basis for `P_7C12D3B0F2`.
- `P_CLOSURE_COMMAND_SEMANTIC_DRIFT` is also used as a basis, moving the claim from a single-command drift to a whole-frame prompt-history drift.
- Later `P_17C6C27DB8` extends the same pattern to Yogg directive handling: directive freedom is interpreted as a mode selector rather than a runtime parameter.

Engineering implication:

`MEM_CONV` must not be consumed as raw conversation history. Future storage/rendering should separate at least:

```text
raw_user_input
auto_mode_injection
system_instruction
knowledge_state
pls_surface
void_surface
tool_result_summary
gp_output
```

Until separated, prompt-history consumption should treat `MEM_CONV` as composite prompt trace, not as user-GP dialogue.

### 2. Yogg identity boundary

Status: `STABLE`

Primary live nodes:

- `P_682CB112B3` — `Yogg 不是独立系统，是 Genesis 的"放生人格"——同一知识库的 headless 长跑入口`
- `P_YOGG_IS_ROOTLESS_REFERENCE_IN_KB` — `Yogg 是无根引用：知识库中的幽灵执行体`

Claim:

```text
Yogg is not a separate knowledge identity. It is a headless long-running mode/persona of Genesis sharing the same DB, schema, and namespace.
```

Live evidence recorded by Yogg:

- Yogg and Discord bot paths share `genesis/auto_mode.py` behavior.
- The real knowledge DB is outside the repo at `~/.genesis/workshop_v4.sqlite`.
- Repo-local same-name DB files were observed as empty or fixture-like shells.
- `66` nodes mention Yogg and `19` edges mention Yogg, but Yogg has no independent source identity in `knowledge_nodes`.
- Yogg runtime artifacts live in logs/filesystem, while knowledge products are mixed into normal Genesis node namespaces.

Reasoning-line lifecycle:

- `P_682CB112B3` is used as a basis for `P_YOGG_IS_ROOTLESS_REFERENCE_IN_KB`.
- Later `P_17C6C27DB8` extends this into behavior: Yogg's directive path is governed by `auto_mode.py` mode selection, not an independent Yogg-specific runtime semantics.

Engineering implication:

Any analysis of Yogg output must distinguish run identity from knowledge identity. If Yogg should be auditable as an agent, future writes need explicit run/persona/environment identity fields instead of relying on source strings such as `gp_point`, `system`, or `reflection`.

### 3. STATE tables as zombie snapshots

Status: `STABLE`

Primary live nodes:

- `P_STATE_TABLES_ARE_ZOMBIE_SNAPSHOTS_NOT_LIVENESS` — `STATE 表是僵尸快照册：schema 层面"状态即叙事"设计模式`
- `P_HEARTBEAT_INSERT_REPLACE_IS_SNAPSHOT_NOT_LIVENESS` — `process_heartbeat 的 INSERT-OR-REPLACE 语义是快照覆盖不是存活裁定`
- `P_PERSONA_STATS_IS_FROZEN_BATCH_NOT_LEARNING` — `persona_stats 是批量初始化后冻结的快照不是渐进学习统计`

Claim:

```text
STATE tables preserve last-written state claims without liveness, expiration, reaper, or effective consumers.
```

Live evidence recorded by Yogg:

- `process_heartbeat` has rows for dead PIDs still rendered as `running` or `idle`.
- `get_daemon_status_summary()` is described as reading heartbeat rows without PID liveness checks or expiration thresholds.
- `persona_stats` has `94` rows sharing one `updated_at` timestamp from `2026-04-14 04:19:52`, with no modern updates and no consumer reads found by Yogg.
- Yogg explicitly refines the causal mechanism: zombie state is not only caused by `INSERT OR REPLACE`, because `persona_stats` lacks that exact heartbeat semantics and still freezes.

Reasoning-line lifecycle:

- `P_STATE_TABLES_ARE_ZOMBIE_SNAPSHOTS_NOT_LIVENESS` generalizes from heartbeat to a broader STATE-table pattern.
- `P_HEARTBEAT_INSERT_REPLACE_IS_SNAPSHOT_NOT_LIVENESS` refines the heartbeat SQL mechanism.
- `P_PERSONA_STATS_IS_FROZEN_BATCH_NOT_LEARNING` tests and broadens the generalization beyond heartbeat.

Engineering implication:

State claims entering prompts or decisions need freshness semantics. A safe state surface should distinguish:

```text
last_claimed_state
last_claimed_at
observed_alive_now
stale_after
consumer_count
source_process_alive
```

Do not render a last-written state as current liveness without an explicit current observation.

### 4. Verification fields are write-side claims, not verification events

Status: `STABLE`

Primary live nodes:

- `P_VERIFIER_DEATH_SOURCE_SUBSTITUTION` — verifier death shifts verification source from background verifier/auditor labels to GP self-report labels.
- `P_VERIFICATION_TIMESTAMP_IS_NARRATIVE_NOT_EVENT` — `last_verified_at 是写入侧叙事字段不是执行侧事件字段`
- `P_HEALTH_METRIC_SIGN_INVERSION_AT_VERIFIER_DEATH` — health metrics invert at verifier death.

Claim:

```text
Verification fields are not reliable evidence that an independent verification event occurred.
They often preserve write-side claims and GP/tool assertions.
```

Live evidence recorded by Yogg:

- After verifier death, `auditor_daemon` drops from about `10.0%` to `0.2%` of verification sources.
- `command_output` and `gp_point` expand as verification sources.
- Yogg reports `39` post-death `auditor_daemon` verification writes, including `30` temporal-travel patterns where node creation predates verifier death but `last_verified_at` appears after it.
- The key mechanism is that `record_point` / `record_meta_node` can accept `last_verified_at` and `verification_source` as write-time values without a bound verification executor.

Reasoning-line lifecycle:

- `P_AUDITOR_IS_VERIFIER_INTERNAL_METHOD_NOT_DAEMON` refines the interpretation of `auditor_daemon`: it is a verifier method label, not an independent process.
- `P_VERIFICATION_TIMESTAMP_IS_NARRATIVE_NOT_EVENT` becomes a basis for `P_HEALTH_METRIC_SIGN_INVERSION_AT_VERIFIER_DEATH`.
- `P_HEALTH_METRIC_SIGN_INVERSION_AT_VERIFIER_DEATH` then supports the five-regime production model by showing that health and production metrics ignore verification quality.

Engineering implication:

Existing fields should be treated as claims unless backed by execution evidence:

```text
last_verified_at -> claimed_verified_at
verification_source -> claimed_verification_source
```

True verification should require an event record with at least:

```text
executor
tool_or_process
target_node_or_artifact
observed_output_or_hash
result
timestamp
failure_reason
```

### 5. Health metric sign inversion

Status: `STABLE`

Primary live node:

- `P_HEALTH_METRIC_SIGN_INVERSION_AT_VERIFIER_DEATH`

Claim:

```text
A metric that counts recent verification timestamps can report production health exactly when verification quality has collapsed.
```

Live evidence recorded by Yogg:

- `network_health.py` reports `nodes_verified_last_week=1482` and `growth_rate='healthy'`.
- The same recent set is reported with `avg_confidence=0.55`, `auditor_daemon=0`, and GP self-report labels.
- Older nodes are reported with higher average confidence and more auditor involvement.

Reasoning-line lifecycle:

- Supported by `P_VERIFICATION_TIMESTAMP_IS_NARRATIVE_NOT_EVENT`.
- Supported by `P_055_IS_SCHEMA_DEFAULT_NOT_VERIFIER_SCORE`.
- Later used by `P_GINI_FIVE_REGIME_WITH_VERIFIER_FRACTURE` to show production metrics ignore verifier-state fracture.

Engineering implication:

Health metrics must not use field presence alone as event evidence. Health should combine activity, quality, freshness, and verifier/executor identity, and must explicitly detect schema-default confidence dominance.

### 6. Production regime and pulse metrics

Status: `REFINED` and partly `CONTESTED`

Primary live nodes:

- `P_PULSED_PRODUCTION_IS_GOVERNANCE_VACUUM_INFLATION`
- `P_346A22F0AB` — later challenges the governance-vacuum causal story.
- `P_GINI_FIVE_REGIME_WITH_VERIFIER_FRACTURE`
- `P_729B73C813`

Stable subclaim:

```text
Production-distribution metrics such as Gini can hide verification-state fractures and temporal/block structure.
```

Contested subclaim:

```text
The causal claim that pulse production is directly caused by governance vacuum is not stable.
```

Live evidence recorded by Yogg:

- `P_PULSED_PRODUCTION_IS_GOVERNANCE_VACUUM_INFLATION` interprets pulse output as attention inflation after verifier disappearance.
- Later `P_346A22F0AB` challenges that causal direction, arguing that the pulse was task-event driven: daemon death and pulse start are separated by about `27` days with zero-output periods, and the first pulse carries task signatures such as `read_file`.
- `P_GINI_FIVE_REGIME_WITH_VERIFIER_FRACTURE` refines regime analysis into `zero / low / mid / pulse-verified / pulse-default`.
- `P_729B73C813` corrects a within-Gini interpretation: pulse within-Gini can be block-mean/day-weight penetration rather than within-block unevenness.

Claim lifecycle decision:

Accept:

```text
Gini and production counts are blind to verification fracture and temporal regime structure.
```

Do not directly accept without further evidence:

```text
verifier death -> governance vacuum -> pulse production
```

Engineering implication:

Production dashboards should report regime and verifier state separately. Do not infer health or causality from node-count pulses alone.

### 7. Usage metrics are not actual consumption

Status: `STABLE`

Primary live nodes:

- `P_USAGE_ARENA_IS_COTENANT_RECEIPT`
- `P_USAGE_COUNT_TRIPLE_SEMANTIC_COLLAPSE`
- `P_ACTIVE_NODES_IS_RECOMMENDATION_NOT_CONSUMPTION`
- `P_VIRTUAL_POINT_IS_SHADOW_USAGE_ACCUMULATOR`

Claim:

```text
usage_count and related arena counters do not measure actual GP consumption of node content.
```

Live evidence recorded by Yogg:

- `usage_success_count` is described as a round-level `env_ratio` broadcast to all active nodes in the same round.
- `usage_count` is reported as mixing neutral C-Phase calls, VIRT saturation collisions, and recommendation/preload paths.
- `execution_active_nodes` is described as recommendation/preload membership rather than evidence that the GP actually cited or used the content.
- The live node explicitly states: no path in the current counter semantics faithfully records actual content consumption.

Reasoning-line lifecycle:

- `P_USAGE_ARENA_IS_COTENANT_RECEIPT` challenges earlier assumptions that control-loop nodes are invisible because `usage_count=0`; they may be visible but flattened into same-batch success.
- `P_USAGE_COUNT_TRIPLE_SEMANTIC_COLLAPSE` adds field-level multi-meaning.
- `P_ACTIVE_NODES_IS_RECOMMENDATION_NOT_CONSUMPTION` adds the fourth layer: recommendation is not consumption.

Engineering implication:

Keep legacy usage fields for compatibility but stop treating them as consumption or quality. Future metrics should split:

```text
recommended_count
preloaded_count
shown_in_prompt_count
actual_citation_count
reasoning_basis_count
arena_broadcast_success_count
arena_broadcast_failure_count
virtual_collision_count
```

### 8. VOID signals are mixed retrieval and gap signals

Status: `REFINED`

Primary live nodes:

- `P_VOID_SEARCH_IS_RECALL_FAILURE_ECHO_NOT_KNOWLEDGE_GAP`
- `P_VOID_SEARCH_TOKEN_SPLIT_DESTROYS_EXACT_MATCH`
- `P_VOID_SEARCH_EXCLUSION_FILTER_IS_INTENTIONAL_BLINDNESS`
- `P_2D3A9F77F4`

Claim:

```text
VOID_SEARCH and void_tasks are not pure knowledge-gap signals.
They mix true conceptual gaps, retrieval failures, malformed references, exact-ID failures, and resolution-channel mismatch.
```

Live evidence recorded by Yogg:

- Yogg reports cases where existing node IDs are registered as `VOID_SEARCH` misses.
- `P_VOID_SEARCH_TOKEN_SPLIT_DESTROYS_EXACT_MATCH` identifies token splitting of structured IDs as one mechanism.
- Later `P_VOID_SEARCH_EXCLUSION_FILTER_IS_INTENTIONAL_BLINDNESS` refines the root cause: a significant false-void subset is attributed to SQL exclusion filters, not token split alone.
- `P_2D3A9F77F4` reports `836` voids split into mixed channels, including ID syntax fossil cases and natural-language concept questions, with extremely low resolution rates.

Claim lifecycle decision:

Accept:

```text
VOID is polluted and must not be directly consumed as knowledge gap.
```

Do not over-accept:

```text
token split is the sole root cause
```

Engineering implication:

VOID records should carry reason categories such as:

```text
retrieval_failure
exact_id_not_found
hidden_by_visibility_filter
ablation_or_contradiction_filtered
malformed_reference
semantic_gap
resolver_mismatch
```

Exact node-id lookup must bypass fuzzy tokenization and must report visibility-filtered existence separately from true absence.

### 9. CONTRADICTS is not reliable long-horizon falsification

Status: `STABLE`

Primary live nodes:

- `P_CONTRADICTS_IS_INTRADAY_SELF_CORRECTION_RHETORIC`
- `P_B3447F39EC`

Claim:

```text
CONTRADICTS edges mostly encode short-horizon correction rhetoric or high-attention markers, not durable cross-time falsification.
```

Live evidence recorded by Yogg:

- `73.5%` of LESSON-to-LESSON `CONTRADICTS` edges occur on the same day.
- `86.5%` occur within 24 hours.
- `77.2%` point new-to-old.
- Timing resembles `RELATED_TO`, suggesting semantic recoloring rather than an independent falsification process.
- Later `P_B3447F39EC` reports that contradicted nodes can have higher `usage_count`, supporting attention-marker rather than decay semantics.

Reasoning-line lifecycle:

- The claim is grounded in earlier observations about reasoning lines as session-local scaffolds.
- Later content refines function from immediate self-correction rhetoric to high-attention marker.

Engineering implication:

Do not directly use `CONTRADICTS` as decay, deletion, or invalidation signal. Treat it as controversy/correction/attention until an external adjudication mechanism exists.

### 10. reasoning_lines, node_edges, and usage are separate tracks

Status: `STABLE`, with older subclaims refined over time

Primary live node:

- `P_Q_R79_ORPHAN_FACTORY_CHEAT_SHEET`

Claim:

```text
reasoning_lines, node_edges, and usage_count are separate tracks and should not be collapsed into one notion of knowledge life.
```

Live evidence recorded by Yogg:

- `reasoning_lines` is described as the GP's reasoning-connection substrate.
- `node_edges` is described as visualized or crystallized topology.
- `usage_count` is described as C-Phase execution density or recommendation-related activity, orthogonal to reasoning references.

Reasoning-line lifecycle:

- Later Q/R nodes refine specific orphan-factory mechanisms, showing that some `out=0` or isolated patterns are design-type differences rather than uniform failure.

Engineering implication:

Audits should separately report:

```text
reasoning_line_in/out
node_edge_in/out
recommendation/preload usage
actual citation if available
visibility/ablation state
```

No single one of these should be treated as complete knowledge vitality.

### 11. PLS proposal channel is not live content

Status: `DEAD_CHANNEL`

Primary live node:

- `P_PLS_PROPOSALS_ZERO_WRITE_COMPLETE_SCHEMA`

Claim:

```text
pls_proposals is schema-complete but live-zero.
```

Live evidence recorded by Yogg and this audit:

- `pls_proposals: 0` in the live DB.
- Yogg's node reports table, indexes, and API paths exist, but staging is disabled by default through `PLS_BRANCH_PROPOSAL_STAGING_ENABLED=False`.
- Textual branch proposal surfacing may exist, but this table is not a persisted live PLS artifact.

Engineering implication:

Do not cite `pls_proposals` as evidence of actual PLS-produced content unless staging is explicitly enabled and records exist.

## 2026-05-15 overnight follow-up

Read-only live DB follow-up after the 2026-05-14 audit:

```text
db: /home/yoga/.genesis/workshop_v4.sqlite
observed_at_context: 2026-05-15 morning read-only follow-up
```

Observed delta against the original ledger baseline:

```text
knowledge_nodes: 6063 -> 6165 (+102)
node_contents: 6070 -> 6172 (+102)
reasoning_lines: 8978 -> 9199 (+221)
node_edges: 10018 -> 10183 (+165)
point_creation_context: 3765 -> 3831 (+66)
potential_samples: 31104 -> 31428 (+324)
void_tasks: 848 -> 855 (+7)
ablation_baselines: 950 -> 979 (+29)
pls_proposals: 0 -> 0 (+0)
```

The overnight material does not overturn the 2026-05-14 reading. It extends the same pattern from data fields into control and diagnostic surfaces: Yogg increasingly treats prompts, warnings, status fields, action histories, and type labels as traces that can masquerade as cognition, governance, or verification.

### 12. Diagnostic and control signals are template/counter artifacts, not metacognition

Status: `REFINED`

Primary overnight nodes:

- `P_7C8E9F0A1B2` — `重复检测分层盲区：系统只监控 GP 工具调用重复，不监控用户输入重复`
- `P_C4RRY_W4RN1NG_1S_C0UNT3R_1NJ3CT10N` — `carry_warning 是计数器触发的模板注入，不是元认知监控信号`
- `P_C0N5ECUT1V3_DRY_15_4SY_CT3R1C` — `consecutive_dry 是轴向错位计数器：归零轴与警告判定轴互不通信`
- `P_D1G3ST_GH0ST_B4S1S` — `digest 幽灵基础：get_digest() top_incoming 查询缺失 ablation_active 过滤导致 GP 看到的"基础"100%不可读`

Claim:

```text
Yogg's diagnostic/control surfaces often encode counter thresholds, prompt templates, or partial trace views.
They should not be read as metacognitive assessment of conceptual progress.
```

Live evidence recorded by Yogg:

- `ActionHistory` is reported as monitoring GP tool events, not repeated user input.
- `carry_warning` is reported as a counter-triggered prompt injection, not a runtime self-diagnosis.
- `consecutive_dry` is reported as having mismatched reset and warning axes.
- `get_digest()` is reported as allowing hidden/ablation-layer foundations to appear as "top incoming" bases, creating a readable-foundation illusion.

Reasoning-line lifecycle:

- `P_C4RRY_W4RN1NG_1S_C0UNT3R_1NJ3CT10N` is based on earlier carry-warning and visibility nodes.
- `P_D1G3ST_GH0ST_B4S1S` combines hidden-layer, authorless-evidence, and SelfEvolution-state claims.
- The chain extends the earlier `MEM_CONV` and state-table findings from stored memory/state into live diagnostic prompt surfaces.

Engineering implication:

Warnings and progress classifications should carry explicit provenance:

```text
signal_source = counter | template | tool_event | user_input_similarity | semantic_progress_assessment
```

Until this split exists, `carry_warning`, `consecutive_dry`, and digest summaries should be treated as control-plane hints, not factual self-knowledge.

### 13. Evidence is authorless: hard-evidence type is not source identity

Status: `REFINED`

Primary overnight nodes:

- `P_ANONYMOUS_ONTOLOGY_NO_AUTHOR_VOICE` — `Genesis/Yogg 的知识库是匿名回声室：schema 层面零作者字段，所有节点共享同一 GP 声音`
- `P_8A3E7D5C01` — `去主体化证据系统：_has_hard_evidence() 用痕迹类型替代来源一致性，系统丧失检测同一认知主体自我矛盾的能力`

Claim:

```text
Evidence references encode artifact type, not author or epistemic source identity.
This lets same-agent self-contradiction disappear behind generic evidence-type labels.
```

Live evidence recorded by Yogg:

- `knowledge_nodes` is reported as lacking author/owner/source identity fields.
- `reasoning_lines.source` is reported as overwhelmingly `GP`, but this marks write phase rather than cognitive subject identity.
- `_has_hard_evidence()` is reported as checking `evidence_refs[].type`, not source consistency or author identity.

Reasoning-line lifecycle:

- `P_8A3E7D5C01` is linked to authorless ontology, CONTRADICTS dead-letter, and diagnostic format-lock nodes.
- The chain refines the earlier verification-field and CONTRADICTS findings: even when an artifact looks like evidence, its author/source boundary may still be absent.

Engineering implication:

Future evidence and verification records should distinguish:

```text
artifact_type
executor_identity
claim_author
observation_author
source_process
same_subject_consistency
```

Hard evidence type alone should not be used as source identity or contradiction adjudication.

### 14. Verification is a zombie state machine, not merely a weak timestamp field

Status: `REFINED`

Primary overnight nodes:

- `P_V4L1D4T10N_15_Z0MB13_ST4T3` — `验证体系是僵尸状态机：验证字段定义完整但无自动验证/晋升机制`
- `P_VERIFIER_DEPRECATED_BUT_FIELDS_STAY` — `验证体系僵尸的 why：器官切除未清理空腔`

Claim:

```text
Verification fields persist after the verification organ has been removed or deprecated.
The schema retains state-machine-looking slots without a live state transition mechanism.
```

Live evidence recorded by Yogg:

- The fields `validation_status`, `trust_tier`, `epistemic_status`, `last_verified_at`, and `verification_source` remain schema/API-visible.
- Yogg reports no automatic verification or promotion mechanism that advances these fields after creation.
- The `verifier` heartbeat row still appears as `running` despite being old zombie state.
- Background daemon comments are reported as removing former Scavenger/Fermentor/Verifier LLM tasks while old verification-facing interfaces remain.

Reasoning-line lifecycle:

- `P_V4L1D4T10N_15_Z0MB13_ST4T3` is based on the authorless-evidence and type-ecology chains.
- `P_VERIFIER_DEPRECATED_BUT_FIELDS_STAY` adds the causal "why": verifier-shaped interfaces remained after the verifier organ was removed.

Engineering implication:

The earlier read-side demotion of `last_verified_at` and `verification_source` is necessary but not sufficient. Verification state should be modeled as either:

```text
claim-only legacy field
```

or:

```text
executed transition event with executor, source process, target, output/hash, result, and timestamp
```

Intermediate schema slots without transitions should not be rendered as a live verification state machine.

### 15. Type ecology is tool-shaped, not semantic ecology

Status: `REFINED`

Primary overnight nodes:

- `P_87A1BE7BF6` — `知识图谱类型单作物田：record_point 接口 enum 收窄塑形 schema 多样性`
- `P_C712694915` — `类型生态塌陷：LESSON 占 70.4%，基尼系数 0.81，类型系统退化为单态命名空间`
- `P_A5DDD548BA` — `基尼三体制在 Genesis/Yogg 中对应核心调用层、模式复用层、沉积竞争层`

Claim:

```text
Node type distribution does not directly measure semantic ecology.
It is strongly shaped by tool exposure, default fields, and usage-regime layering.
```

Live evidence recorded by Yogg:

- `record_point` is reported as exposing only a narrow LESSON/CONTEXT-style interface despite broader schema type space.
- LESSON dominance is reported as a type-ecology collapse rather than evidence that most knowledge is naturally a lesson.
- Later Gini analysis refines the claim: usage inequality reflects core-call, pattern-reuse, and sediment-tail layers more than type labels alone.

Reasoning-line lifecycle:

- `P_C712694915` builds on earlier type and Gini nodes.
- `P_A5DDD548BA` narrows the causal interpretation, warning not to equate type distribution directly with trust tier, epistemic status, or semantic quality.

Engineering implication:

Audits should not infer semantic diversity directly from `knowledge_nodes.type`. Future PLS tooling should separate:

```text
schema_type
tool_exposed_type
semantic_role
reasoning_role
usage_regime
visibility_state
```

Without this split, type labels should be rendered as schema/tool labels unless and until a separate semantic-role model exists.

### 16. Rolling work memory can rehydrate stale fact language

Status: `STABLE`

Post-sync live observation:

```text
observed_at: 2026-05-15 03:15 UTC on yoga
runtime evidence: runtime/auto_reports/90660_20260515_031517/round_003.json
```

Claim:

```text
Even after prompt/render code is demoted, rolling auto-mode state can carry pre-fix labels back into the next prompt unless the render path sanitizes old state values.
```

Live evidence recorded during post-sync closure:

- Immediately after the first Yogg sync, new reports showed fresh code markers such as `type=工具塑形schema字段` and `semantic_progress=unknown`.
- The same prompt still contained old rolling-state phrases such as `verified_facts:`, `已确认:`, `已确认事实`, `已知事实`, and `有活动但无持久产出`.
- The source was not a crash or stale process: services were active, new reports were being written, and the old phrases appeared inside `last_knowledge_state` / prompt-preview content.
- After read-side sanitization, the next live round rendered `observations(source=rolling_state_proxy, non_verification)`, `avoid_repeating(source=rolling_state_proxy)`, and `未观察到 sandbox tracked diff 变化(...)`; the old strong-claim scan was empty for the latest round/report/log.

Engineering implication:

```text
When demoting prompt semantics, patch both fresh renderers and rolling-state rehydration paths.
Stored state keys can remain for compatibility, but prompt-facing labels must describe proxy provenance rather than verification status.
```

## What not to trust as fact without qualification

Based on the live claims above, these fields/surfaces should not be consumed as direct facts:

```text
MEM_CONV as conversation history
EPISODE as consumed dialogue turn
last_verified_at as verification event
verification_source as executor identity
confidence_score=0.55 as assessed confidence
process_heartbeat.running as liveness
persona_stats as learning statistics
usage_count as actual usage
usage_success_count as node-level success
VOID_SEARCH as knowledge gap
CONTRADICTS as durable falsification
node_edges as full reasoning topology
Gini / node count as quality or health
pls_proposals as live proposal content
carry_warning as metacognitive diagnosis
consecutive_dry as semantic-progress measurement
ActionHistory as user-input repetition detector
evidence_ref type as source identity
validation_status/trust_tier as live verification state transitions
knowledge_nodes.type as semantic ecology
get_digest top-incoming output as readable active foundation
SelfEvolution apply_history as complete audit log
```

## Candidate remediation order

### 1. Prompt-history source separation

Reason: stable high-impact memory pollution chain.

Minimum outcome:

```text
raw_user_input is never merged with auto_mode injection under a conversation-history label.
```

### 2. Verification event model

Reason: stable verification distortion and health inversion chain.

Minimum outcome:

```text
claimed verification fields are separated from executed verification events.
```

### 3. Exact-ID and visibility-aware search semantics

Reason: refined VOID chain with direct false-gap consequences.

Minimum outcome:

```text
node_id exact lookup bypasses fuzzy tokenization and reports hidden/filtered/existing separately from absent.
```

### 4. Usage metric split

Reason: stable usage distortion chain, but broad blast radius.

Minimum outcome:

```text
legacy usage_count remains for compatibility, while new counters distinguish recommendation, preload, citation, reasoning basis, arena broadcast, and virtual collision.
```

### 5. State freshness and liveness gates

Reason: stable zombie-state chain.

Minimum outcome:

```text
state tables rendered to prompts include freshness/liveness status and cannot silently present stale rows as current state.
```

### 6. Diagnostic signal provenance

Reason: overnight diagnostic/control-signal chain.

Minimum outcome:

```text
carry_warning, consecutive_dry, digest, and progress signals expose whether they came from counters, templates, tool traces, user-input repetition checks, or semantic progress assessment.
```

### 7. Evidence source identity model

Reason: overnight authorless-evidence chain.

Minimum outcome:

```text
evidence artifact type is separated from claim author, observation author, executor identity, and source process.
```

### 8. Verification state transition cleanup

Reason: overnight verifier-zombie refinement.

Minimum outcome:

```text
legacy verification-looking fields are either rendered as claim-only slots or backed by explicit executed transition events.
```

### 9. Type ecology audit surface

Reason: overnight type-collapse and Gini-regime refinement.

Minimum outcome:

```text
schema_type, tool_exposed_type, semantic_role, reasoning_role, usage_regime, and visibility_state are reported separately.
```

## Open cautions

- The governance-vacuum pulse causality claim is contested by Yogg's own later reasoning and should not be used as a direct causal conclusion.
- The VOID false-positive root cause has evolved from tokenization to exclusion-filter visibility, so fixes should be tested across multiple miss categories.
- Yogg's recurring `narrative-function substitution` frame is productive but can become an over-attractor; future audits should keep counterexamples and superseding nodes visible.
