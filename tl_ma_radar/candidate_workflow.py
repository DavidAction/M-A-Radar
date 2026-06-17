from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKFLOW_FILE = Path("tl_ma_radar") / "data" / "candidate_workflow.json"
STATUS_OPTIONS = ["미검토", "관심", "제외", "추적", "접촉", "실사중"]
CONTACT_OPTIONS = ["미접촉", "접촉준비", "접촉완료", "자료요청", "미팅예정", "보류"]


def default_workflow() -> dict[str, Any]:
    return {
        "status": "미검토",
        "memo": "",
        "owner": "",
        "next_action": "",
        "contact_status": "미접촉",
        "due_date": "",
        "updated_at": "",
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


def update_workflow(root: Path, code: str, payload: dict[str, Any]) -> dict[str, Any]:
    workflows = load_workflows(root)
    current = workflow_for_code(workflows, code)
    current.update(sanitize_update(payload))
    workflows[str(code)] = current
    save_workflows(root, workflows)
    return current


def workflow_options() -> dict[str, list[str]]:
    return {
        "statuses": STATUS_OPTIONS,
        "contact_statuses": CONTACT_OPTIONS,
    }
