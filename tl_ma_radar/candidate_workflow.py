from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKFLOW_FILE = Path("tl_ma_radar") / "data" / "candidate_workflow.json"
STATUS_OPTIONS = ["미검토", "관심", "제외", "추적", "접촉", "실사중"]
CONTACT_OPTIONS = ["미접촉", "접촉준비", "접촉완료", "자료요청", "미팅예정", "보류"]
TRACKED_FIELDS = ["status", "contact_status", "owner", "due_date", "next_action", "memo"]
FIELD_LABELS = {
    "status": "상태",
    "contact_status": "연락 상태",
    "owner": "담당자",
    "due_date": "검토 기한",
    "next_action": "다음 액션",
    "memo": "메모",
}


def default_workflow() -> dict[str, Any]:
    return {
        "status": "미검토",
        "memo": "",
        "owner": "",
        "next_action": "",
        "contact_status": "미접촉",
        "due_date": "",
        "updated_at": "",
        "history": [],
    }


def workflow_path(root: Path) -> Path:
    return root / WORKFLOW_FILE


def load_workflows(root: Path) -> dict[str, dict[str, Any]]:
    path = workflow_path(root)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("items"), dict):
        return {str(code): dict(value) for code, value in payload["items"].items() if isinstance(value, dict)}
    if isinstance(payload, dict):
        return {str(code): dict(value) for code, value in payload.items() if isinstance(value, dict)}
    return {}


def save_workflows(root: Path, workflows: dict[str, dict[str, Any]]) -> None:
    path = workflow_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": workflows,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def workflow_for_code(workflows: dict[str, dict[str, Any]], code: str) -> dict[str, Any]:
    merged = default_workflow()
    merged.update(workflows.get(str(code)) or {})
    if not isinstance(merged.get("history"), list):
        merged["history"] = []
    return merged


def sanitize_update(payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status") or "미검토").strip()
    contact_status = str(payload.get("contact_status") or "미접촉").strip()
    return {
        "status": status if status in STATUS_OPTIONS else "미검토",
        "memo": str(payload.get("memo") or "").strip()[:5000],
        "owner": str(payload.get("owner") or "").strip()[:80],
        "next_action": str(payload.get("next_action") or "").strip()[:500],
        "contact_status": contact_status if contact_status in CONTACT_OPTIONS else "미접촉",
        "due_date": str(payload.get("due_date") or "").strip()[:20],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _change_summary(changes: list[dict[str, str]]) -> str:
    labels = [FIELD_LABELS.get(change["field"], change["field"]) for change in changes]
    return ", ".join(labels[:4]) + (f" 외 {len(labels) - 4}" if len(labels) > 4 else "")


def _build_history_event(previous: dict[str, Any], updated: dict[str, Any]) -> dict[str, Any] | None:
    changes = []
    for field in TRACKED_FIELDS:
        before = str(previous.get(field) or "")
        after = str(updated.get(field) or "")
        if before == after:
            continue
        changes.append(
            {
                "field": field,
                "label": FIELD_LABELS.get(field, field),
                "before": before,
                "after": after,
            }
        )
    if not changes:
        return None
    return {
        "at": updated.get("updated_at") or datetime.now(timezone.utc).isoformat(),
        "type": "workflow_update",
        "summary": _change_summary(changes),
        "changes": changes,
        "snapshot": {field: updated.get(field) for field in TRACKED_FIELDS},
    }


def update_workflow(root: Path, code: str, payload: dict[str, Any]) -> dict[str, Any]:
    workflows = load_workflows(root)
    previous = workflow_for_code(workflows, code)
    current = dict(previous)
    current.update(sanitize_update(payload))
    history = list(previous.get("history") or [])
    event = _build_history_event(previous, current)
    if event:
        history.append(event)
    current["history"] = history[-100:]
    workflows[str(code)] = current
    save_workflows(root, workflows)
    return current


def workflow_options() -> dict[str, list[str]]:
    return {
        "statuses": STATUS_OPTIONS,
        "contact_statuses": CONTACT_OPTIONS,
    }
