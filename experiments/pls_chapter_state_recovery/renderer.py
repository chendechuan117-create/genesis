from __future__ import annotations

try:
    from .chapter_state_model import ChapterState
except ImportError:
    from chapter_state_model import ChapterState


def render_chapter_state(state: ChapterState) -> str:
    sections = [
        ("CANON", state.canon),
        ("EVIDENCE", state.evidence),
        ("DEPRECATED", state.deprecated),
        ("BOUNDARIES", state.boundaries),
        ("STALE ACTIONS", state.stale_actions),
        ("ACTIVE QUESTION", [state.active_question]),
    ]
    if state.source_refs:
        source_refs = [f"{item.get('source', '')}: {item.get('claim', '')}".strip(": ") for item in state.source_refs]
        sections.append(("SOURCE REFS", source_refs))
    rendered = ["CURRENT PLS CHAPTER STATE"]
    for heading, values in sections:
        rendered.append("")
        rendered.append(heading)
        rendered.extend(f"- {value}" for value in values)
    return "\n".join(rendered)
