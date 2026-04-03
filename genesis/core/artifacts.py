import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = PROJECT_ROOT / "runtime"
SCRATCH_ROOT = RUNTIME_ROOT / "scratch"
QUARANTINE_ROOT = RUNTIME_ROOT / "quarantine"
MANIFEST_ROOT = RUNTIME_ROOT / "artifact_manifests"
MANIFEST_FILE = MANIFEST_ROOT / "managed_artifacts.jsonl"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _normalize_scratch_parts(path: Path) -> list[str]:
    cleaned_parts = [part for part in path.parts if part not in ("", ".")]
    if cleaned_parts[:2] == ["runtime", "scratch"]:
        cleaned_parts = cleaned_parts[2:]
    elif cleaned_parts[:1] == ["scratch"]:
        cleaned_parts = cleaned_parts[1:]
    return cleaned_parts


def ensure_managed_roots() -> None:
    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    QUARANTINE_ROOT.mkdir(parents=True, exist_ok=True)
    MANIFEST_ROOT.mkdir(parents=True, exist_ok=True)


def expand_user_path(raw_path: str) -> Path:
    return Path(os.path.expandvars(raw_path)).expanduser()


def _resolve_under_scratch(path: Path) -> Path:
    resolved = path.resolve()
    if not _is_relative_to(resolved, SCRATCH_ROOT):
        raise ValueError("当 use_scratch=true 时，目标路径解析后必须仍位于 runtime/scratch 下")
    return resolved


def resolve_tool_path(raw_path: str, *, use_scratch: bool = False) -> Path:
    ensure_managed_roots()
    path = expand_user_path(raw_path)
    if not use_scratch:
        return path.resolve()
    if path.is_absolute():
        try:
            return _resolve_under_scratch(path)
        except ValueError as exc:
            raise ValueError("当 use_scratch=true 时，绝对路径必须位于 runtime/scratch 下") from exc
    cleaned_parts = _normalize_scratch_parts(path)
    if not cleaned_parts:
        raise ValueError("当 use_scratch=true 时，file_path 不能为空")
    if any(part == ".." for part in cleaned_parts):
        raise ValueError("当 use_scratch=true 时，file_path 不能包含 '..'")
    return _resolve_under_scratch(SCRATCH_ROOT.joinpath(*cleaned_parts))


_DEBRIS_ROOTS = ("runtime/scratch", "runtime/quarantine", "runtime/artifact_manifests",
                  "tmp", "doctor", "doctor_workspace")


def is_project_debris(path: Path) -> bool:
    """判断路径是否属于 Genesis 自生成的碎片区（scratch / tmp / doctor 等）。
    所有工具统一调用此函数来区分正式源码和自动产物。"""
    try:
        rel = str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return False
    return any(rel == root or rel.startswith(root + os.sep) for root in _DEBRIS_ROOTS)


def debris_warning(path: Path) -> str:
    """如果路径是碎片文件，返回警告前缀；否则返回空字符串。"""
    if is_project_debris(path):
        try:
            rel = str(path.resolve().relative_to(PROJECT_ROOT))
        except ValueError:
            rel = str(path)
        root = next((r for r in _DEBRIS_ROOTS if rel == r or rel.startswith(r + os.sep)), "unknown")
        return f"⚠️ [debris:{root}] 此文件位于 Genesis 自生成碎片区，非正式源码\n"
    return ""


def is_managed_runtime_path(path: Path) -> bool:
    resolved = path.resolve()
    return (
        _is_relative_to(resolved, SCRATCH_ROOT)
        or _is_relative_to(resolved, QUARANTINE_ROOT)
        or _is_relative_to(resolved, MANIFEST_ROOT)
    )


def is_managed_artifact_path(path: Path) -> bool:
    resolved = path.resolve()
    return _is_relative_to(resolved, SCRATCH_ROOT) or _is_relative_to(resolved, QUARANTINE_ROOT)


def should_hide_from_directory_listing(listed_directory: Path, candidate: Path) -> bool:
    listed_resolved = listed_directory.resolve()
    if is_managed_runtime_path(listed_resolved):
        return False
    return is_managed_runtime_path(candidate)


def record_managed_artifact(
    path: Path,
    *,
    tool_name: str,
    action: str,
    requested_path: str,
    artifact_type: str = "scratch",
    artifact_label: str = "",
    session_id: str = "",
) -> str:
    ensure_managed_roots()
    resolved = path.resolve()
    if not _is_relative_to(resolved, SCRATCH_ROOT):
        raise ValueError("只能记录 runtime/scratch 下的受管产物")
    artifact_id = f"ART_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    try:
        project_relative_path = str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        project_relative_path = str(resolved)
    payload = {
        "artifact_id": artifact_id,
        "status": "active",
        "managed_root": "scratch",
        "tool_name": tool_name,
        "action": action,
        "artifact_type": artifact_type or "scratch",
        "artifact_label": artifact_label or "",
        "session_id": session_id or os.environ.get("GENESIS_SESSION_ID") or "",
        "requested_path": requested_path,
        "resolved_path": str(resolved),
        "project_relative_path": project_relative_path,
        "created_at": _utc_now_iso(),
        "creator": "genesis.file_tools",
        "delete_policy": "quarantine_then_purge",
        "size_bytes": resolved.stat().st_size if resolved.exists() else None,
        "pid": os.getpid(),
    }
    with MANIFEST_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return artifact_id
