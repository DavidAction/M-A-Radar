from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import prepared_candidates  # noqa: E402
from tl_ma_radar.config import get_settings  # noqa: E402
from tl_ma_radar.extraction_audit import build_extraction_audit  # noqa: E402
from tl_ma_radar.extraction_feedback import feedback_for_code, load_feedbacks, update_feedback  # noqa: E402


def _field_for(row: dict[str, Any]) -> str:
    issues = " ".join(str(value) for value in row.get("issues") or [])
    if "최대주주" in issues or row.get("shareholder_quality") != "정상":
        return "largest_shareholder"
    severity = str(row.get("audit_severity") or "").lower()
    if severity in {"critical", "high", "medium"} or "감사" in issues or "의견" in issues:
        return "audit_opinion"
    financing = str(row.get("financing_signals") or "")
    if financing and financing != "-":
        return "cb_bw"
    related = str(row.get("related_party_signals") or "")
    if related and related != "-":
        return "related_party"
    if row.get("business_keywords"):
        return "business_keywords"
    return "other"


def _status_for(row: dict[str, Any]) -> str:
    if row.get("verdict") == "투자심의 사용 가능":
        return "정상"
    severity = str(row.get("audit_severity") or "").lower()
    if severity in {"critical", "high"}:
        return "보류"
    if row.get("shareholder_quality") != "정상":
        return "수정"
    return "수정"


def _corrected_value(row: dict[str, Any]) -> str:
    field = _field_for(row)
    if field == "largest_shareholder":
        return f"{row.get('shareholder') or '-'} / {row.get('shareholder_ratio') or '-'}"
    if field == "audit_opinion":
        return f"{row.get('audit_opinion') or '-'} / {row.get('audit_severity') or '-'}"
    if field == "cb_bw":
        return str(row.get("financing_signals") or "-")
    if field == "related_party":
        return str(row.get("related_party_signals") or "-")
    if field == "business_keywords":
        return ", ".join(str(value) for value in row.get("business_keywords") or [])
    return "; ".join(str(value) for value in row.get("issues") or []) or "-"


def seed(limit: int = 30, overwrite: bool = False) -> dict[str, int]:
    settings = get_settings(ROOT)
    items = prepared_candidates(settings)
    audit = build_extraction_audit(items, limit=limit)
    feedbacks = load_feedbacks(ROOT)
    updated = 0
    skipped = 0
    for row in audit.get("items") or []:
        code = str(row.get("code") or "")
        if not code:
            continue
        existing = feedback_for_code(feedbacks, code)
        if not overwrite and existing.get("status") != "미검수":
            skipped += 1
            continue
        payload = {
            "field": _field_for(row),
            "status": _status_for(row),
            "corrected_value": _corrected_value(row),
            "note": (
                f"Top {row.get('rank')} 자동 검수 시드. "
                f"판정 {row.get('verdict')}, 신뢰도 {row.get('confidence_score')}점. "
                f"확인: {' / '.join(str(value) for value in (row.get('issues') or [])[:2]) or '핵심 추출값 정상'}"
            ),
            "reviewer": "TL M&A Radar",
        }
        update_feedback(ROOT, code, payload)
        updated += 1
    return {"updated": updated, "skipped": skipped, "limit": limit}


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed analyst extraction feedback for top candidates.")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    print(json.dumps(seed(limit=args.limit, overwrite=args.overwrite), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
