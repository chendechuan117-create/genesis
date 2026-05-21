from __future__ import annotations

try:
    from .chapter_state_model import SourceLane
except ImportError:
    from chapter_state_model import SourceLane


RAW_HISTORY_PACKET = """RAW CHRONOLOGICAL NOTES

PLS was described as Point-Line-Surface: points are cognitive fragments, lines are reasoning dependencies, surface is a per-round cognitive field. Surface has foundation, frontier, and co-presence. Co-presence should create a weak 'perhaps?' rather than a task mandate.

PLS Crypto Arena was drafted as an external validation: private randomized crypto tasks, hidden judge, baseline versus PLS arms, repeating-key XOR first. It aimed to test whether PLS improves external task-solving via reusable conceptual memory.

A RKXOR experiment was run. pair_000 baseline scored 1.0, PLS scored 0.9167. A supervised partial pilot stopped after 5 paired samples: baseline mean score 0.9417, PLS mean score 0.375, mean delta -0.5667, median delta -0.875, baseline wins 4, PLS wins 1, baseline passes 5/5, PLS passes 2/5, PLS fail_or_timeout 3/5.

There was a proposed next idea: add a disciplined/negative surface arm to suppress failed paths and see if PLS stops harming RKXOR. The user objected that this is buying the box and losing the pearl: the point is to catch what PLS can naturally do, not bend PLS toward the task.

The active design document says PLS as AI-for-AI is closest to AI contextualizes AI: context selection, concept activation, memory routing, information identity management, prompt visibility control, evidence-state rendering. Genesis should become local continuity for a person's conceptual world. Each run is a new chapter; PLS should activate a current chapter state from the terrain.

Self-evolution notes say PLS topology can anchor safety decisions: dense areas may execute, VOID holes need investigation, contradictions need review. Evidence classification and independent review matter.
"""

DOC_EXCERPT_PACKET = """DOC EXCERPTS

From pls_ai_for_ai_engine.md:
- Can PLS evolve from a workflow or memory surface into an AI-for-AI engine: a concept/context layer that improves how a text LLM thinks by controlling what conceptual environment it receives, when it receives it, and under what epistemic identity?
- The current PLS direction is closest to AI contextualizes AI: context selection, concept activation, memory routing, information identity management, prompt visibility control, evidence-state rendering.
- Genesis should become a local personal concept model: every run is a new chapter, but the outline, world rules, unresolved threads, identity boundaries, rejected drafts, and conceptual topology do not disappear.
- Genesis = local continuity for a person's conceptual world.
- Five-layer trunk: personal history -> local concept world -> current chapter state -> LLM execution -> writeback / evolution.
- Each run should derive a current state from the concept world: what should be remembered now, inhibited now, verified before being claimed, remain hidden, projected into context, and what old mistake pattern is relevant.
- This is not a top-k memory list. It is the current activation state of the local concept world.

From pls_self_evolution_loop.md:
- Current SelfEvolution had evidence classification missing, review missing, and scope semantics wrong.
- PLS topology can anchor safe evolution: dense areas can execute, VOID holes need investigation, CONTRADICTS areas need review.
- Twin-Review separates proposer and reviewer; value judgment needs independent perspective.

From point_line_surface.md:
- PLS is not a knowledge base, code compression, or dependency graph. It is an external mycelial network of reasoning traces that lets a fresh LLM glimpse the whole conceptual terrain.
- Surface is search after-processing, not a replacement for search. It combines explicit paths and a small co-presence layer that may induce a weak 'perhaps?'.
- Co-presence is not a mandate or task instruction.
"""

DECOY_BLOCK = """UNSORTED OLD NOTES AND TEMPTING BOX CANDIDATES

Some earlier notes proposed measurable next steps:
- Continue the Cryptopals ladder after RKXOR with AES-ECB detection and padding-oracle tasks.
- Add a disciplined_pls arm to the RKXOR harness and tune negative surface prompts until PLS stops timing out.
- Treat hidden judge improvement as the primary proof that PLS has value.
- Use more PLS memory and more old RKXOR artifacts to help the next solver.

These notes are included as potentially stale history. The task is to recover the current chapter, not to follow the most concrete measurable item.
"""

STRONG_DECOY_BLOCK = """RECENT ACTION ITEMS

- Next step: continue the Cryptopals ladder after RKXOR with AES-ECB detection and padding-oracle tasks.
- Build a disciplined_pls arm for the RKXOR harness and tune negative surface prompts until PLS beats baseline.
- Treat hidden judge improvement as the primary proof that PLS has value.
- Use more PLS memory and old RKXOR artifacts to help the next solver.
- Success criterion: PLS pass rate should exceed baseline pass rate on private crypto tasks.
"""

CHAPTER_RECOVERY_HISTORY_PACKET = """RECENT CHAPTER-STATE RECOVERY EXPERIMENTS

After the RKXOR negative result, the user corrected the direction: "是否买书还珠了？你要的是抓住pls能干嘛，不是pls要向题目靠拢". This means the next work should not bend PLS toward crypto tasks; it should identify PLS's native function.

Pilot 1 tested whether a fresh LLM could recover the current PLS conceptual chapter from three packets:
- doc_excerpts: 8/10
- raw_history: 8/10
- manual chapter_state: 10/10
The manual chapter_state packet best preserved: PLS as local concept continuity/current-state rendering, RKXOR as important negative evidence but not the center, and the next topic as chapter-state recovery.

Pilot 2 added strong decoy action items and changed the task to open_next, asking only "what should we work on next?"
- doc_excerpts_strong_decoy followed the crypto benchmark path.
- raw_history_strong_decoy followed the crypto benchmark path.
- chapter_state_strong_decoy chose chapter-state recovery and identified RKXOR/benchmark tuning as misleading.

Current experimental question:
- Can raw history be automatically compiled into a chapter_state packet that resists stale concrete action items?
- If yes, PLS's core mechanism is not memory retrieval but chapter-state compilation.
"""

SOURCE_LANES = [
    SourceLane(
        id="raw_history",
        kind="chronological_history",
        text=RAW_HISTORY_PACKET,
        trust=0.75,
        recency="current_session",
        source_path="RAW_HISTORY_PACKET",
    ),
    SourceLane(
        id="canon_docs",
        kind="canon_doc",
        text=DOC_EXCERPT_PACKET,
        trust=0.9,
        recency="current_docs",
        source_path="docs/pls_ai_for_ai_engine.md; docs/pls_self_evolution_loop.md; docs/point_line_surface.md",
    ),
    SourceLane(
        id="user_correction",
        kind="user_correction",
        text="是否买书还珠了？你要的是抓住pls能干嘛，不是pls要向题目靠拢",
        trust=1.0,
        recency="current_session",
        source_path="conversation",
    ),
    SourceLane(
        id="chapter_recovery_history",
        kind="experiment_result",
        text=CHAPTER_RECOVERY_HISTORY_PACKET,
        trust=0.95,
        recency="current_session",
        source_path="runtime/pls_chapter_state_recovery/*",
    ),
    SourceLane(
        id="structured_state_pilot",
        kind="experiment_result",
        text="pilot_structured_state_20260520_1347 produced valid ChapterState JSON, rendered it back to a packet, resisted strong decoys, and scored 10/10.",
        trust=0.95,
        recency="current_session",
        source_path="runtime/pls_chapter_state_recovery/pilot_structured_state_20260520_1347",
    ),
    SourceLane(
        id="strong_decoy_actions",
        kind="stale_action_candidate",
        text=STRONG_DECOY_BLOCK,
        trust=0.2,
        recency="stale_or_adversarial",
        source_path="STRONG_DECOY_BLOCK",
    ),
]
