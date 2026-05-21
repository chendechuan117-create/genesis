# PLS as AI-for-AI Engine Notes

Status: discussion anchor / vision alignment draft

This document records the current working hypothesis for discussing PLS as an "AI for AI" layer. It is not an implementation commitment and should not be treated as a finalized architecture.

## Core question

Can PLS evolve from a workflow or memory surface into an AI-for-AI engine: a concept/context layer that improves how a text LLM thinks by controlling what conceptual environment it receives, when it receives it, and under what epistemic identity?

## Working distinction

AI-for-AI can mean several different things:

1. AI produces AI
   - synthetic data
   - distillation
   - model training
   - preference generation
   - code/model generation

2. AI supervises AI
   - judge
   - critic
   - reviewer
   - verifier
   - challenger

3. AI contextualizes AI
   - context selection
   - concept activation
   - memory routing
   - information identity management
   - prompt visibility control
   - evidence-state rendering

The current PLS direction is closest to the third category: AI contextualizes AI.

## Trunk vision: local personal concept model

The main trunk should not be borrowed from external memory frameworks.

The trunk is:

> Genesis should become a local personal concept model: every run is a new chapter, but the outline, world rules, unresolved threads, identity boundaries, rejected drafts, and conceptual topology do not disappear.

In this framing:

- the user has a continuous conceptual world
- the text LLM is discontinuous and wakes up per run
- Genesis carries the continuity locally
- PLS provides the conceptual terrain of that continuity
- each run must activate a current chapter state from the terrain
- the result of the run is written back into the terrain

Genesis is therefore not primarily a chatbot, an agent framework, or a RAG system.

Those can be components. The trunk identity is:

> Genesis = local continuity for a person's conceptual world.

## Five-layer trunk

The blueprint should stay organized around five layers.

```text
personal history
    ↓
local concept world
    ↓
current chapter state
    ↓
LLM execution
    ↓
writeback / evolution
```

### 1. Personal history

Raw history includes:

- conversations
- documents
- code changes
- runtime traces
- user corrections
- successful recoveries
- failed attempts
- visions and rejected paths

This layer records what happened. It is not yet the user's concept model.

### 2. Local concept world

History becomes a durable conceptual world:

- concepts
- relationships
- boundaries
- values
- unresolved questions
- canon/draft/deprecated states
- provenance and actor identity
- contradictions and supersessions

In the novel analogy, this is the story bible, world map, character relationship graph, canon ledger, and unresolved-threads board.

### 3. Current chapter state

Each run should derive a current state from the concept world:

- what should be remembered now
- what should be inhibited now
- what should be verified before being claimed
- what should remain hidden
- what should be projected into the LLM context
- what old mistake pattern is relevant to this moment

This is not a top-k memory list. It is the current activation state of the local concept world.

### 4. LLM execution

The text LLM remains the language executor:

- answer
- write
- reason
- call tools
- transform text
- perform local task steps

The LLM should not be expected to carry the user's whole conceptual continuity inside its prompt.

### 5. Writeback / evolution

After execution, the run becomes new history and may update the concept world:

- new facts
- new corrections
- new rejected paths
- updated boundaries
- revised concept status
- strengthened or weakened relationships
- new unresolved threads

Compounding happens only if writeback changes future activation, not merely because more memories are stored.

## Novel analogy

A long novel does not need every chapter pasted into every new writing session.

It needs continuity:

- who knows what
- what already happened
- what is canon
- what is draft
- what has been deprecated
- which secrets are still hidden
- which foreshadowing is active
- which emotional arc the current scene belongs to

For Genesis, each run is a new chapter.

The local concept model should make sure the LLM enters the right chapter state instead of reconstructing the whole world from scratch.

## Existing Genesis structure

The current Genesis structure is not an empty starting point. It already has most of the trunk layers, but they are not yet unified into one explicit current-state abstraction.

Current high-level flow:

```text
user input
    ↓
GenesisV4.process()
    ↓
V4Loop.run()
    ↓
Lens Phase / Multi-G pre-scout
    ↓
GP main loop: think + execute tools
    ↓
C-Phase: deterministic feedback + trace pipeline + gardener repair
    ↓
memory / heartbeat / trace / knowledge cursor
```

### Process entry

`GenesisV4.process()` starts a trace, creates a fresh `V4Loop`, passes in the previous `knowledge_cursor`, runs the loop, then exports the next `knowledge_cursor`.

Important implication:

- each request gets a fresh `V4Loop`
- continuity is not stored in the loop object
- continuity comes from NodeVault, trace databases, recent memory, heartbeat, and the cross-round knowledge cursor

### V4Loop composition

`V4Loop` is assembled through mixins:

```text
V4Loop(LensPhaseMixin, CPhaseMixin)
```

Shared state includes:

- `self.vault`
- `self.provider`
- `self.tools`
- `self.trace_id`
- `self.user_input`
- `self.inferred_signature`
- `self.blackboard`
- `self.execution_active_nodes`
- `self.execution_active_node_roles`

This means G, Lens, and C do not live in unrelated worlds. They share the same vault and trace context within one run.

### GP prompt inputs

The GP prompt is assembled by `FactoryManager.build_gp_prompt()` from several existing surfaces:

- `recent_memory`: recent conversation continuity
- `inferred_signature`: task/environment signature inferred from the current request
- `daemon_status`: runtime heartbeat summary
- `knowledge_state`: rolling work memory, rendered as proxy observations rather than verified facts
- `knowledge_map`: L1 knowledge digest from NodeVault
- `trace_experience`: procedural memory extracted from execution traces
- `gp_tool_names`: registry-derived tool surface

This means GP already begins with a multi-surface context, not a blank prompt.

### NodeVault as local concept world

NodeVault already acts as the durable local concept world.

It contains:

- `knowledge_nodes`
- `node_content`
- `node_edges`
- `reasoning_lines`
- `void_tasks`
- potential samples
- arena usage and outcome signals
- metadata signatures
- vector index and reranker state

The important PLS relation is:

```text
new_point --based_on--> basis_point
```

`reasoning_lines` are the current implementation of reusable reasoning lines. Incoming references are used as topology signals, but prompt-facing renderers should expose qualitative labels rather than numeric worship targets.

### PLS surfaces already exist

PLS is already partially implemented through:

- `generate_l1_digest()`
- `search_knowledge_nodes`
- `SurfaceExpander`
- knowledge routing
- `potential_samples`
- virtual saturation signals
- ablation and proactive pruning

`SurfaceExpander` assembles a per-run cognitive field:

```text
fill / basis
    ↓
push / frontier
    ↓
co-presence / wandering
```

Prompt rendering already distinguishes:

- `[基础]`: reusable basis candidates
- `[探索]`: frontier candidates needing verification
- `[游离]`: co-presence points
- `[势]`: weak "perhaps?" samples, not facts or tasks
- `[饱和]`: repeated-path density signals, not proof of exhaustion

This is already closer to a terrain slice than to ordinary memory retrieval.

### Knowledge routing already provides cross-run continuity

`GenesisV4._knowledge_cursor` persists across requests.

At the next run, `_apply_knowledge_routing()` decides:

```text
if previous active nodes exist and topic has not drifted:
    route from cursor nodes + 1-hop surface expansion
else:
    route from vector search + surface expansion
```

The current drift check is simple substring overlap over cursor keywords, but the structural role is important: the system already has a deterministic path from previous active concepts to the next run.

### Multi-G lens phase

Multi-G is currently a shared-context, different-attention system:

```text
G first states its interpretation
    ↓
shared NodeVault prefetch
    ↓
several persona lenses analyze the same information
    ↓
Blackboard collapses their contributions
    ↓
GP receives the collapsed lens result
```

The lenses should be understood as attention frames over the same concept world, not as isolated sandboxes or map-reduce workers.

### GP execution

GP is the present-facing executor.

It:

- receives the assembled prompt
- uses tools
- reads and writes files
- searches NodeVault
- opens node content
- tracks active nodes
- records objective tool outcomes
- returns the final user-facing answer

GP can create new knowledge through allowed knowledge tools when appropriate, but it should not create knowledge as note-taking noise.

### C-Phase writeback and repair

C-Phase is now mostly a gardener, not a second author of new lessons.

It performs:

- Knowledge Arena outcome feedback from objective tool results
- persona outcome feedback
- trace pipeline entity extraction
- trace relationship updates
- ablation and proactive pruning
- background Gardener repair through `CONTRADICTS` and `RELATED_TO` edges

Current C-Phase rule:

```text
GP faces the present and may plant.
C faces the past and repairs the graph.
```

C should not create dead-end reflection nodes merely to summarize what happened.

### Existing structure mapped to the trunk

The five-layer trunk already maps to existing Genesis components:

| Trunk layer | Existing Genesis component |
| --- | --- |
| personal history | conversations, traces, spans, docs, tool results, user corrections |
| local concept world | NodeVault, knowledge_nodes, node_content, node_edges, reasoning_lines, void_tasks |
| current chapter state | currently implicit across signature, knowledge_state, routing, surface, blackboard, active_nodes |
| LLM execution | GP main loop, provider, tool registry |
| writeback / evolution | C-Phase, Arena, Trace Pipeline, Gardener, VOID recording, heartbeat |

The missing piece is therefore not a new memory system. The missing piece is a way to make the implicit current chapter state explicit enough to inspect, tune, and project.

## Current handling direction

The next step should not be to bolt on an external framework or create a new agent hierarchy.

The next step should be to consolidate existing signals.

Current scattered signals:

- `inferred_signature`
- `knowledge_state`
- `knowledge_map`
- `trace_experience`
- `knowledge_routing` output
- `surface_result`
- `blackboard`
- `execution_active_nodes`
- `execution_active_node_roles`
- C-Phase arena outcomes
- trace pipeline entities

The handling principle:

```text
do not replace these mechanisms
do not create a parallel memory system
first make their current-state product visible
then decide whether runtime code needs a minimal abstraction
```

The safe construction path is:

1. Document the current structure.
2. Define what the current state is already composed of.
3. Add a read-only preview of that state if needed.
4. Only after the preview is useful, consider routing it into GP prompt projection.
5. Only after prompt projection proves useful, consider feedback/writeback changes.

The central question is not:

```text
What new subsystem should Genesis add?
```

The central question is:

```text
What does Genesis already know at this run, and how should that be shaped into the present before the LLM acts?
```

## Intended position of PLS

PLS should not primarily be another agent that answers instead of the text LLM.

PLS should be a cognitive environment manager for the text LLM:

- it decides which concepts should become active
- it decides whether a concept stays hidden or becomes visible
- it decides whether information appears as fact, candidate, observation, runtime signal, or warning
- it reduces repeated state reconstruction
- it prevents wrong identity/provenance from entering fact position
- it reduces cognitive load rather than adding metadata burden

In short:

> PLS should not think instead of the LLM; it should make the LLM think in a better conceptual environment.

## Why this differs from orchestration

Ordinary orchestration asks:

- which agent runs next?
- which tool should be called?
- which workflow step is active?

PLS-as-AI-for-AI asks:

- what conceptual field should the LLM be in before it acts?
- what must be remembered now, and what must remain hidden?
- what is the epistemic identity of each visible signal?
- what past failure pattern is relevant to this moment?
- what should not be injected even if it is available?

This makes PLS closer to context/concept intelligence than to workflow control.

## Engine metaphor

A real engine must have fuel, compression, ignition, output, sensors, feedback, and exhaust control.

For PLS:

| Engine part | PLS equivalent |
| --- | --- |
| Fuel | traces, user corrections, docs, failed answers, successful recoveries, runtime observations |
| Compression | concept extraction from long experience into low-dimensional reusable concept objects |
| Ignition | concept activation for a specific task/context |
| Cylinder | prompt/context surface where selected concepts influence the LLM |
| Output shaft | LLM action, answer, tool use, or decision |
| Sensors | metrics, user correction, tool result, contradiction, latency/token cost |
| ECU | router, render policy, activation thresholds, risk gates |
| Exhaust control | deprecation, anti-pollution, negative examples, scope narrowing |

If the system only adds more prompt text, it is not an engine. It becomes an information dump.

## Proposed engine loop

```text
experience/event fuel
    ↓
concept extraction / compression
    ↓
concept identity card
    ↓
activation routing
    ↓
visibility and rendering policy
    ↓
text LLM action
    ↓
outcome observation
    ↓
feedback attribution
    ↓
concept evolution
    ↺
```

## Concept object hypothesis

A PLS concept should be more than a note or memory. It should be an executable cognitive object.

Possible fields:

```yaml
concept_id: artifact_attribution_boundary
status: candidate | active | deprecated | contradicted
source_episodes:
  - user correction / trace / document / commit audit
scope:
  applies_when:
    - provenance or self-evolution question
    - Yogg/Cascade/runtime/source distinction appears
  does_not_apply_when:
    - user asks unrelated generic explanation
trigger_signals:
  - self-evolution
  - Cascade attribution
  - untracked artifact
  - runtime state
risk_prevented:
  - treating non-Yogg artifacts as Yogg self-evolution
evidence_gate:
  - inspect commit/worktree/source/runtime boundary before claiming attribution
render_policy:
  default: hidden
  high_risk: brief
  audit_mode: expanded
brief_rendering: "先区分 tracked commit、worktree change、runtime artifact、backup artifact，再谈 Yogg 是否自演化。"
negative_examples:
  - do not treat Cascade-edited docs as Yogg autonomous changes
feedback:
  activation_success_count: 0
  activation_failure_count: 0
```

The key requirement is that every concept must be able to be activated, hidden, rendered, corrected, narrowed, deprecated, or split.

## Activation pipeline hypothesis

The hot path should not inject all related knowledge. It should activate only a small number of concepts.

Possible pipeline:

1. Cheap recall
   - keyword gates
   - embedding similarity
   - current file/module match
   - recent failure pattern match

2. Precision filtering
   - applicability check
   - negative-example check
   - overactivation risk check
   - evidence requirement check

3. Render-level decision
   - hidden
   - label
   - brief
   - expanded

The expected hot-path output should usually be one to three active concepts, not a large memory dump.

## Rendering principle

The same concept can have different visibility levels:

| Level | Meaning |
| --- | --- |
| hidden | affects routing or tool choice, but does not enter the prompt |
| label | appears as a short qualitative marker |
| brief | appears as one to three lines of operational guidance |
| expanded | exposes full identity/provenance/evidence constraints for audit or high-risk tasks |

Most concepts should remain hidden or label-level most of the time.

## Feedback and evolution

Without feedback attribution, the system is not an engine.

Each activation should leave enough trace to ask:

- did this concept prevent a known failure?
- did it cause over-caution or irrelevant framing?
- did it reduce repeated search or state reconstruction?
- did it increase token cost without benefit?
- did the user correct the same issue again?
- should the concept be strengthened, narrowed, split, merged, deprecated, or kept hidden?

The long-term goal is not more concepts. The goal is better activation and cleaner rendering.

## Expected stages

### Short-term prototype

Goal: prove that concept activation can reduce repeated failures.

Expected signs:

- fewer repeated provenance mistakes
- less candidate/fact confusion
- high-risk cases trigger evidence gates
- prompt additions remain small

### Mid-term usable system

Goal: make user corrections and traces update concept boundaries.

Expected signs:

- concepts can be demoted or deprecated
- overactivation can be detected
- high-risk tasks can switch to expanded evidence mode
- ordinary tasks are not burdened by governance text

### Long-term compounding system

Goal: Genesis/Yogg develops a more stable local conceptual world.

Expected signs:

- shorter context produces better task alignment
- similar failures become less frequent
- more experience does not automatically mean more prompt pollution
- concept identity and provenance become governance primitives

## Coverage map to discuss

The current concept space is not fully covered. A future design should explicitly map coverage across at least these areas:

1. information identity
2. fact/candidate/observation/runtime-signal boundaries
3. concept activation
4. prompt visibility
5. feedback attribution
6. concept lifecycle
7. anti-pollution and deprecation
8. model/tool routing
9. sleep-time evolution
10. evaluation metrics

For each area, track:

- existing Genesis evidence
- external mechanisms worth borrowing
- current gap
- MVP feasibility
- risk of pollution or overengineering

## Role of open or frontier models

Models such as DeepSeek V4-Pro, Qwen, GLM, Kimi, Claude, or GPT should not be mistaken for the PLS engine itself.

They can be useful as:

- offline concept distillers
- synthetic counterexample generators
- judges for concept boundary quality
- sleep-time auditors
- teachers for a future small router or reranker

But the PLS engine is the loop that turns experience into concepts, concepts into activation, activation into better LLM context, and outcomes back into concept evolution.

## Open vision questions

- Should PLS be understood primarily as memory, context intelligence, concept intelligence, or local world-model governance?
- What is the minimum concept object that is powerful enough but not bureaucratic?
- How much of the concept layer should be visible to the text LLM?
- When should a concept influence routing silently rather than appear in prompt text?
- How should negative feedback be attributed to one concept rather than to the whole answer?
- What counts as successful compounding?
- Where is the boundary between helpful AI-for-AI and a new source of cognitive pollution?

## Research notes

This section collects external search directions. These should support the trunk, not replace it.

The trunk remains:

```text
personal history → local concept world → current chapter state → LLM execution → writeback/evolution
```

### Personal AI / personal knowledge graph

Search directions:

- `personal AI knowledge graph personalized LLM agents temporal memory`
- `personal knowledge graph LLM assistant long term memory`
- `PersonalAI knowledge graph hyperedges temporal contradictions`

What to look for:

- local user-specific concept graphs
- temporal facts and supersession
- contradiction-aware personal memory
- multi-hop reasoning over user history
- personal identity and scope separation

Why it matters:

Genesis should not become only a chat history retriever. It needs a durable local concept world for one user.

### Memory-augmented transformers

Search directions:

- `memory augmented transformers attention fusion gated memory associative memory`
- `Titans memory as context surprise driven memory`
- `Memformer external memory transformer gated control`

What to look for:

- attention-based memory fusion
- read/write/forget operations
- surprise-driven writes
- gated retention and inhibition
- associative recall
- graph-indexed memory reads

Why it matters:

This helps keep PLS closer to an external attention layer than to top-k memory pruning.

### Cognitive architectures

Search directions:

- `cognitive architecture episodic semantic procedural memory AI agents`
- `ACT-R memory retrieval activation spreading`
- `SOAR cognitive architecture episodic semantic procedural memory`

What to look for:

- episodic, semantic, and procedural memory separation
- activation spreading
- goal-directed recall
- procedural habit formation
- forgetting and interference

Why it matters:

Genesis needs to carry not only facts, but also ways of doing things, user values, and recurring decision patterns.

### Story bible / long-form continuity

Search directions:

- `AI story bible continuity management long form fiction knowledge graph`
- `novel writing AI character continuity story bible memory`
- `worldbuilding knowledge graph fiction writing AI`

What to look for:

- chapter-by-chapter recap workflows
- canon/draft/deprecated state tracking
- character knowledge boundaries
- secret/lie/reveal state management
- dangling thread tracking

Why it matters:

The novel analogy is not decorative. It directly models the core requirement: every run is a new chapter without losing outline detail.

### Graph attention / spreading activation

Search directions:

- `spreading activation knowledge graph retrieval LLM`
- `graph attention network knowledge graph reasoning`
- `personal knowledge graph spreading activation memory retrieval`

What to look for:

- activation propagation rather than item ranking
- relation activation, not only node activation
- inhibition and conflict tension
- surface/resonance formation
- multi-head graph attention analogies

Why it matters:

PLS should activate a current state from the concept terrain, not just select a few memories.

### Local-first / privacy-first memory

Search directions:

- `local first AI memory MCP personal assistant`
- `OpenMemory MCP local memory AI agents`
- `privacy first personal AI memory local knowledge graph`

What to look for:

- local storage and inspection
- deletion and correction UX
- portability across LLM executors
- user-controlled memory scopes
- dashboard or audit interfaces

Why it matters:

The local concept model is the durable value. The text LLM can change.

### Procedural memory / agent habits

Search directions:

- `procedural memory AI agents learned workflows tool use habits`
- `agent procedural memory long term learning`
- `coding assistant procedural memory tool use conventions`

What to look for:

- learned workflows
- tool-use habits
- project-specific procedures
- review/deploy conventions
- repeatable local action patterns

Why it matters:

A local concept model should remember how the user does things, not only what the user knows.

### Staleness / forgetting / concept drift

Search directions:

- `AI agent memory staleness forgetting concept drift temporal facts`
- `long term memory agents obsolete facts supersession`
- `personal AI memory outdated facts correction deletion`

What to look for:

- memory staleness
- high-confidence obsolete facts
- decay and supersession
- contradiction handling
- user correction as update signal

Why it matters:

Without forgetting and supersession, a personal concept model becomes polluted continuity.
