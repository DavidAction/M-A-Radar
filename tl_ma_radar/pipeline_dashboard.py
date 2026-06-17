from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from typing import Any


STATUS_ORDER = ["관심", "추적", "접촉", "실사중", "제외", "미분류"]


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_date(value: object) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _workflow(item: dict[str, Any]) -> dict[str, Any]:
    return _dict(item.get("workflow"))


def _status(workflow: dict[str, Any]) -> str:
    value = str(workflow.get("status") or "").strip()
    return value if value else "미분류"


def _owner(workflow: dict[str, Any]) -> str:
    value = str(workflow.get("owner") or "").strip()
    return value if value else "미지정"


def _row(item: dict[str, Any], today: date) -> dict[str, Any]:
    workflow = _workflow(item)
    due = _parse_date(workflow.get("due_date"))
    days_left = (due - today).days if due else None
    score = _float(item.get("priority_score") or item.get("shortlist_score") or _dict(item.get("scores")).get("total"))
    judgment = _dict(item.get("acquisition_judgment"))
    investment = _dict(item.get("investment_case"))
    return {
        "code": item.get("code"),
        "name": item.get("name"),
        "status": _status(workflow),
        "owner": _owner(workflow),
        "next_action": workflow.get("next_action") or "다음 액션 미입력",
        "contact_status": workflow.get("contact_status") or "미확인",
        "due_date": due.isoformat() if due else "",
        "days_left": days_left,
        "memo": workflow.get("memo") or "",
        "priority_score": round(score, 1),
        "decision": investment.get("decision") or judgment.get("decision") or item.get("recommendation") or "-",
        "risk_level": judgment.get("risk_level") or "-",
        "shortlist_group": item.get("shortlist_group") or "-",
    }


def _due_bucket(days_left: int | None) -> str:
    if days_left is None:
        return "기한 없음"
    if days_left < 0:
        return "기한 초과"
    if days_left <= 3:
        return "3일 이내"
    if days_left <= 7:
        return "7일 이내"
    return "여유"


def build_pipeline_dashboard(items: list[dict[str, Any]]) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    rows = [_row(item, today) for item in items]
    active = [row for row in rows if row["status"] != "제외"]
    lanes: list[dict[str, Any]] = []
    statuses = STATUS_ORDER + sorted({str(row["status"]) for row in rows if row["status"] not in STATUS_ORDER})
    for status in statuses:
        status_rows = [row for row in rows if row["status"] == status]
        if not status_rows and status == "미분류":
            continue
        status_rows.sort(key=lambda row: (-_float(row.get("priority_score")), str(row.get("due_date") or "9999-12-31")))
        lanes.append({"status": status, "count": len(status_rows), "items": status_rows[:10]})

    by_status: dict[str, int] = {}
    by_owner: dict[str, int] = {}
    due_buckets: dict[str, int] = {}
    for row in rows:
        by_status[str(row["status"])] = by_status.get(str(row["status"]), 0) + 1
        by_owner[str(row["owner"])] = by_owner.get(str(row["owner"]), 0) + 1
        bucket = _due_bucket(row.get("days_left") if isinstance(row.get("days_left"), int) else None)
        due_buckets[bucket] = due_buckets.get(bucket, 0) + 1

    due_items = [
        row
        for row in active
        if isinstance(row.get("days_left"), int) and int(row["days_left"]) <= 7
    ]
    due_items.sort(key=lambda row: (int(row["days_left"]), -_float(row.get("priority_score"))))
    hygiene = {
        "no_owner": sum(1 for row in active if row["owner"] == "미지정"),
        "no_next_action": sum(1 for row in active if row["next_action"] == "다음 액션 미입력"),
        "no_due_date": sum(1 for row in active if not row["due_date"]),
        "overdue": sum(1 for row in active if isinstance(row.get("days_left"), int) and int(row["days_left"]) < 0),
    }

    return {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": len(rows),
            "active": len(active),
            "by_status": by_status,
            "by_owner": by_owner,
            "due_buckets": due_buckets,
            "hygiene": hygiene,
            "next_7_days": len(due_items),
        },
        "lanes": lanes,
        "due_items": due_items[:20],
        "recommended_actions": _recommended_actions(hygiene, due_items),
    }


def _recommended_actions(hygiene: dict[str, int], due_items: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    if hygiene.get("overdue"):
        actions.append(f"기한 초과 {hygiene['overdue']}건은 오늘 담당자 확인 및 상태 갱신")
    if hygiene.get("no_owner"):
        actions.append(f"담당자 미지정 {hygiene['no_owner']}건은 상위 점수순으로 배정")
    if hygiene.get("no_next_action"):
        actions.append(f"다음 액션 미입력 {hygiene['no_next_action']}건은 IR 자료 요청/원문 실사/접촉 중 하나로 지정")
    if due_items:
        top = due_items[0]
        actions.append(f"가장 급한 후보: {top.get('name')} - {top.get('next_action')}")
    if not actions:
        actions.append("현재 파이프라인 위생 상태 양호. 접촉·실사 전환율 관리에 집중")
    return actions


def pipeline_dashboard_csv(payload: dict[str, Any]) -> bytes:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "lane_status",
            "code",
            "name",
            "owner",
            "next_action",
            "contact_status",
            "due_date",
            "days_left",
            "priority_score",
            "decision",
            "risk_level",
            "shortlist_group",
            "memo",
        ]
    )
    for lane in payload.get("lanes") or []:
        if not isinstance(lane, dict):
            continue
        for row in lane.get("items") or []:
            if not isinstance(row, dict):
                continue
            writer.writerow(
                [
                    lane.get("status"),
                    row.get("code"),
                    row.get("name"),
                    row.get("owner"),
                    row.get("next_action"),
                    row.get("contact_status"),
                    row.get("due_date"),
                    row.get("days_left"),
                    row.get("priority_score"),
                    row.get("decision"),
                    row.get("risk_level"),
                    row.get("shortlist_group"),
                    row.get("memo"),
                ]
            )
    return ("\ufeff" + output.getvalue()).encode("utf-8")
