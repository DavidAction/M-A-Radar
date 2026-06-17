from __future__ import annotations

import csv
import io
from typing import Any

from tl_ma_radar.scoring import clamp


GROUP_ORDER = {
    "즉시 검토": 0,
    "심층 실사": 1,
    "고위험 옵션": 2,
    "모니터링": 3,
}


def _priority_score(item: dict[str, Any]) -> float:
    scores = item.get("scores") or {}
    signals = item.get("deal_signals") or {}
    signal_scores = signals.get("scores") or {}
    radar = scores.get("total") or 0
    deal_execution = signal_scores.get("deal_execution_score") or 0
    white_knight = signal_scores.get("white_knight_need_score") or 0
    synergy = ((scores.get("tl_synergy") or 0) + (scores.get("renes_synergy") or 0)) / 2
    governance = signal_scores.get("governance_risk_score") or 0
    judgment = item.get("acquisition_judgment") or {}
    judgment_scores = judgment.get("scores") or {}
    attractiveness = judgment_scores.get("attractiveness") or radar
    raw = radar * 0.26 + attractiveness * 0.28 + deal_execution * 0.22 + white_knight * 0.12 + synergy * 0.14
    raw -= max(governance - 82, 0) * 0.18
    return round(clamp(raw), 1)


def _group(item: dict[str, Any], priority_score: float) -> str:
    signals = item.get("deal_signals") or {}
    signal_scores = signals.get("scores") or {}
    deal_window = signals.get("deal_window")
    governance = signal_scores.get("governance_risk_score") or 0
    recommendation = item.get("recommendation")
    if deal_window == "즉시 접촉 후보" and recommendation != "보류" and governance < 82:
        return "즉시 검토"
    if governance >= 82 or deal_window == "고위험 선실사":
        return "고위험 옵션"
    if priority_score >= 45 or deal_window == "탐색 접촉 후보":
        return "심층 실사"
    return "모니터링"


def _reason(item: dict[str, Any]) -> str:
    signals = item.get("deal_signals") or {}
    scores = item.get("scores") or {}
    keywords = item.get("business_keywords") or []
    parts = [
        f"레이더 {scores.get('total', '-')}",
        f"딜창 {signals.get('deal_window', '-')}",
        f"백기사 {signals.get('white_knight_need', '-')}",
    ]
    if keywords:
        parts.append("키워드 " + ", ".join(keywords[:4]))
    return " / ".join(parts)


def shortlist_items(items: list[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in items:
        scores = item.get("scores") or {}
        score = round(float(scores.get("total") or 0), 1)
        priority_score = _priority_score(item)
        signals = item.get("deal_signals") or {}
        signal_scores = signals.get("scores") or {}
        cap_case = item.get("capital_raise_case") or {}
        output.append(
            {
                "code": item.get("code"),
                "name": item.get("name"),
                "group": _group(item, priority_score),
                "shortlist_score": score,
                "priority_score": priority_score,
                "recommendation": item.get("recommendation"),
                "market_cap_krw": item.get("market_cap_krw"),
                "sector": item.get("sector"),
                "white_knight_need": signals.get("white_knight_need"),
                "deal_window": signals.get("deal_window"),
                "deal_execution_score": signal_scores.get("deal_execution_score"),
                "white_knight_need_score": signal_scores.get("white_knight_need_score"),
                "governance_risk_score": signal_scores.get("governance_risk_score"),
                "tl_synergy": (item.get("scores") or {}).get("tl_synergy"),
                "renes_synergy": (item.get("scores") or {}).get("renes_synergy"),
                "implied_new_share_ratio": cap_case.get("implied_new_share_ratio"),
                "latest_filing": ((item.get("dart_enrichment") or {}).get("latest_filing") or {}).get("report_nm"),
                "reason": _reason(item),
            }
        )
    output.sort(key=lambda row: (GROUP_ORDER.get(row["group"], 9), -(row.get("priority_score") or 0)))
    if limit:
        return output[:limit]
    return output


def grouped_shortlist(items: list[dict[str, Any]], per_group: int = 8) -> dict[str, Any]:
    rows = shortlist_items(items)
    groups: dict[str, list[dict[str, Any]]] = {name: [] for name in GROUP_ORDER}
    for row in rows:
        group_rows = groups.setdefault(row["group"], [])
        if len(group_rows) < per_group:
            group_rows.append(row)
    return {
        "groups": groups,
        "counts": {group: sum(1 for row in rows if row["group"] == group) for group in GROUP_ORDER},
        "items": rows,
    }


def shortlist_csv(items: list[dict[str, Any]]) -> bytes:
    rows = shortlist_items(items)
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=[
            "group",
            "shortlist_score",
            "priority_score",
            "code",
            "name",
            "recommendation",
            "market_cap_krw",
            "sector",
            "white_knight_need",
            "deal_window",
            "deal_execution_score",
            "white_knight_need_score",
            "governance_risk_score",
            "tl_synergy",
            "renes_synergy",
            "implied_new_share_ratio",
            "latest_filing",
            "reason",
        ],
    )
    writer.writeheader()
    writer.writerows(rows)
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")
