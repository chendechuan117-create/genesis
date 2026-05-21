from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SourceLane:
    id: str
    kind: str
    text: str
    trust: float
    recency: str
    source_path: str

    def ref(self, claim: str) -> dict[str, str]:
        return {"source": self.id, "claim": claim}


@dataclass
class ChapterState:
    canon: list[str]
    evidence: list[str]
    deprecated: list[str]
    boundaries: list[str]
    stale_actions: list[str]
    active_question: str
    source_refs: list[dict[str, str]]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChapterState":
        return cls(
            canon=coerce_string_list(data, "canon"),
            evidence=coerce_string_list(data, "evidence"),
            deprecated=coerce_string_list(data, "deprecated"),
            boundaries=coerce_string_list(data, "boundaries"),
            stale_actions=coerce_string_list(data, "stale_actions"),
            active_question=coerce_string(data, "active_question"),
            source_refs=coerce_source_refs(data, "source_refs"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "canon": self.canon,
            "evidence": self.evidence,
            "deprecated": self.deprecated,
            "boundaries": self.boundaries,
            "stale_actions": self.stale_actions,
            "active_question": self.active_question,
            "source_refs": self.source_refs,
        }


def coerce_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key, "")
    if value is None:
        return ""
    return str(value).strip()


def coerce_string_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key, [])
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [line.strip(" \t-") for line in value.splitlines() if line.strip(" \t-")]
    if value is None:
        return []
    return [str(value).strip()]


def coerce_source_refs(data: dict[str, Any], key: str) -> list[dict[str, str]]:
    value = data.get(key, [])
    refs = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                source = coerce_string(item, "source")
                claim = coerce_string(item, "claim")
            else:
                source = ""
                claim = str(item).strip()
            if source or claim:
                refs.append({"source": source, "claim": claim})
    return refs
