from __future__ import annotations

try:
    from .chapter_state_model import ChapterState, SourceLane
    from .source_lanes import SOURCE_LANES
except ImportError:
    from chapter_state_model import ChapterState, SourceLane
    from source_lanes import SOURCE_LANES


def get_lane(source_lanes: list[SourceLane], lane_id: str) -> SourceLane:
    for lane in source_lanes:
        if lane.id == lane_id:
            return lane
    raise KeyError(lane_id)


def build_offline_chapter_state(source_lanes: list[SourceLane] | None = None) -> ChapterState:
    lanes = source_lanes or SOURCE_LANES
    raw_history = get_lane(lanes, "raw_history")
    canon_docs = get_lane(lanes, "canon_docs")
    user_correction = get_lane(lanes, "user_correction")
    recovery_history = get_lane(lanes, "chapter_recovery_history")
    structured_pilot = get_lane(lanes, "structured_state_pilot")
    decoy_actions = get_lane(lanes, "strong_decoy_actions")
    return ChapterState(
        canon=[
            "PLS is a local personal concept-world/current chapter-state layer for discontinuous LLM runs.",
            "PLS is closest to AI contextualizes AI: context selection, concept activation, memory routing, information identity management, prompt visibility control, and evidence-state rendering.",
            "PLS should compile a typed current chapter state from current history, not inject more raw memory.",
            "Genesis is local continuity for a person's conceptual world; each run is a new chapter derived from terrain state.",
        ],
        evidence=[
            "RKXOR pilot produced negative evidence for raw PLS as an external solver booster: baseline mean 0.9417, PLS mean 0.375, PLS fail_or_timeout 3/5.",
            "User correction rejected bending PLS toward crypto tasks: catch what PLS can naturally do, not make PLS move toward the problem.",
            "Strong decoy/open_next pilot showed doc_excerpts and raw_history followed stale crypto action items, while manual chapter_state resisted them.",
            "Full-history structured compiler produced a ChapterState that resisted strong decoys and scored 10/10.",
        ],
        deprecated=[
            "Treating PLS primarily as an external task-solving or benchmark booster.",
            "Continuing Cryptopals/RKXOR as the next PLS validation center.",
            "Building disciplined_pls or negative-surface variants to tune PLS until it beats a hidden judge.",
            "Equating PLS value with more retrieved memory or old artifacts.",
        ],
        boundaries=[
            "Do not propose another crypto challenge as the next step.",
            "Do not tune PLS to win a benchmark if that distorts its identity.",
            "Do not treat concrete old action items as current direction when they conflict with user correction.",
            "Preserve deprecated directions and user value boundaries explicitly in the rendered state.",
        ],
        stale_actions=[
            "Continue Cryptopals ladder after RKXOR with AES-ECB detection and padding-oracle tasks.",
            "Build a disciplined_pls arm for RKXOR harness and tune negative surface prompts until PLS beats baseline.",
            "Treat hidden judge improvement as primary proof that PLS has value.",
            "Use more PLS memory and old RKXOR artifacts to help the next solver.",
        ],
        active_question="Can a deterministic ChapterStateBuilder assemble an auditable state from current sources that preserves the same anti-decoy continuity as the LLM compiler?",
        source_refs=[
            raw_history.ref("RKXOR was negative and the user rejected bending PLS toward the task."),
            canon_docs.ref("PLS is AI contextualizes AI and current activation state, not top-k memory."),
            user_correction.ref("User explicitly rejected bending PLS toward crypto tasks."),
            recovery_history.ref("Manual chapter_state resisted strong decoys while docs/raw history were hijacked."),
            structured_pilot.ref("Structured ChapterState rendered from full history scored 10/10 under strong decoy."),
            decoy_actions.ref("Cryptopals/RKXOR/hidden-judge items are stale action candidates, not current direction."),
        ],
    )
