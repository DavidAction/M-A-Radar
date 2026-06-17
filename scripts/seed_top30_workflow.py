from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import prepared_candidates  # noqa: E402
from tl_ma_radar.candidate_workflow import update_workflow, workflow_for_code, load_workflows  # noqa: E402
from tl_ma_radar.config import get_settings  # noqa: E402


def _today_kst() -> datetime:
    return datetime.now(timezone(timedelta(hours=9)))


def _score(item: dict[str, Any]) -> float:
    scores = item.get("scores") if isinstance(item.get("scores"), dict) else {}
    return float(item.get("priority_score") or item.get("shortlist_score") or scores.get("total") or 0)


def _risk_note(item: dict[str, Any]) -> str:
    quality = item.get("data_quality") if isinstance(item.get("data_quality"), dict) else {}
    warnings = quality.get("warnings") if isinstance(quality.get("warnings"), list) else []
    if warnings:
        return str(warnings[0])
    flags = item.get("status_flags") if isinstance(item.get("status_flags"), list) else []
    return str(flags[0]) if flags else "핵심 지분, 원문 보고서, 최신 뉴스 교차검증"


def _next_action(item: dict[str, Any]) -> str:
    report = item.get("report_analysis") if isinstance(item.get("report_analysis"), dict) else {}
    if int(report.get("text_chars") or 0) <= 0:
        return "사업보고서/감사보고서 원문 다운로드 및 핵심 리스크 문단 확인"
    intelligence = item.get("report_intelligence") if isinstance(item.get("report_intelligence"), dict) else {}
    severity = str(intelligence.get("severity") or "").lower()
    if severity in {"critical", "high"}:
        return "감사의견, 최대주주, CB/BW, 특수관계 거래 원문 근거 우선 검토"
    judgment = item.get("acquisition_judgment") if isinstance(item.get("acquisition_judgment"), dict) else {}
    if "즉시" in str(judgment.get("deal_window") or item.get("deal_window") or ""):
        return "IR 자료 요청 및 최대주주/특수관계인 접촉 가능성 확인"
    return "TL·르네스 시너지 가설, 지분 구조, 유증 후 희석 영향 검토"


def _payload(item: dict[str, Any], rank: int) -> dict[str, str]:
    today = _today_kst().date()
    due = today + timedelta(days=7 if rank <= 10 else 14)
    status = "접촉" if rank <= 10 else "추적"
    contact = "접촉준비" if rank <= 10 else "미접촉"
    memo = (
        f"자동 파이프라인 편입 #{rank}. "
        f"우선순위 {_score(item):.1f}, 그룹 {item.get('shortlist_group') or '-'}, "
        f"핵심 확인: {_risk_note(item)}"
    )
    return {
        "status": status,
        "contact_status": contact,
        "owner": "TL M&A Team",
        "due_date": due.isoformat(),
        "next_action": _next_action(item),
        "memo": memo,
    }


def seed(limit: int, overwrite: bool) -> dict[str, int]:
    settings = get_settings(ROOT)
    rows = prepared_candidates(settings)
    rows.sort(key=lambda item: (-_score(item), str(item.get("name") or "")))
    workflows = load_workflows(ROOT)
    updated = 0
    skipped = 0
    for rank, item in enumerate(rows[:limit], start=1):
        code = str(item.get("code") or "")
        existing = workflow_for_code(workflows, code)
        already_active = existing.get("status") not in {"", "미검토", None}
        has_manual_fields = any(existing.get(field) for field in ("owner", "next_action", "due_date"))
        if not overwrite and (already_active or has_manual_fields):
            skipped += 1
            continue
        update_workflow(ROOT, code, _payload(item, rank))
        updated += 1
    return {"updated": updated, "skipped": skipped, "limit": limit}


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed top candidates into the active deal workflow.")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    result = seed(limit=args.limit, overwrite=args.overwrite)
    print(result)


if __name__ == "__main__":
    main()
