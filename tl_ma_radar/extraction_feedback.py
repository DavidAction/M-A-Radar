from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FEEDBACK_FILE = Path("tl_ma_radar") / "data" / "extraction_feedback.json"
FIELDS = ["largest_shareholder", "audit_opinion", "cb_bw", "related_party", "business_keywords", "other"]
STATUSES = ["미검수", "정상", "오탐", "수정", "보류"]


def feedback_path(root: Path) -> Path:
    return root / FEEDBACK_FILE


def default_feedback() -> dict[str, Any]:
    return {
        "field": "largest_shareholder",
        "status": "미검수",
        "corrected_value": "",
        "note": "",
        "reviewer": "",
        "updated_at": "",
        "history": [],
    }


def load_feedbacks(root: Path) -> dict[str, dict[str, Any]]:
    path = feedback_path(root)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, dict):
        return {}
    return {str(code): value for code, value in items.items() if isinstance(value, dict)}


def save_feedbacks(root: Path, feedbacks: dict[str, dict[str, Any]]) -> None:
    path = feedback_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": feedbacks,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def feedback_for_code(feedbacks: dict[str, dict[str, Any]], code: str) -> dict[str, Any]:
    merged = default_feedback()
    merged.update(feedbacks.get(str(code)) or {})
    return merged


def update_feedback(root: Path, code: str, payload: dict[str, Any]) -> dict[str, Any]:
    feedbacks = load_feedbacks(root)
    previous = feedback_for_code(feedbacks, code)
    field = str(payload.get("field") or previous.get("field") or "largest_shareholder")
    status = str(payload.get("status") or previous.get("status") or "미검수")
    if field not in FIELDS:
        field = "other"
    if status not in STATUSES:
        status = "미검수"

    now = datetime.now(timezone.utc).isoformat()
    current = {
        **previous,
        "field": field,
        "status": status,
        "corrected_value": str(payload.get("corrected_value") or "").strip(),
        "note": str(payload.get("note") or "").strip(),
        "reviewer": str(payload.get("reviewer") or "").strip(),
        "updated_at": now,
    }
    history = list(previous.get("history") or [])
    history.append(
        {
            "at": now,
            "field": current["field"],
            "status": current["status"],
            "summary": current["note"] or current["corrected_value"] or "추출 검수 상태 업데이트",
        }
    )
    current["history"] = history[-20:]
    feedbacks[str(code)] = current
    save_feedbacks(root, feedbacks)
    return current


def feedback_options() -> dict[str, list[str]]:
    return {"fields": FIELDS, "statuses": STATUSES}


def feedback_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    field_counts: dict[str, int] = {}
    reviewed = 0
    for item in items:
        feedback = item.get("extraction_feedback")
        if not isinstance(feedback, dict):
            continue
        status = str(feedback.get("status") or "미검수")
        field = str(feedback.get("field") or "other")
        counts[status] = counts.get(status, 0) + 1
        field_counts[field] = field_counts.get(field, 0) + 1
        if status != "미검수":
            reviewed += 1
    return {
        "status": "ok",
        "total": len(items),
        "reviewed": reviewed,
        "status_counts": counts,
        "field_counts": field_counts,
        "options": feedback_options(),
    }
