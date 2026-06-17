from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tl_ma_radar.shortlist import GROUP_ORDER, shortlist_items


MONITORING_DIR = Path("tl_ma_radar") / "data" / "monitoring"
IMPORTANT_FILING_KEYWORDS = (
    "유상증자",
    "전환사채",
    "신주인수권",
    "증권신고서",
    "최대주주",
    "대량보유",
    "경영권",
    "관리종목",
    "상장폐지",
    "거래정지",
    "감사의견",
    "감자",
    "합병",
    "영업양수",
    "자산양수",
)
EVENT_PRIORITY = {
    "자금조달": 0,
    "지분/경영권": 1,
    "거래소/상장유지": 2,
    "구조조정": 3,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _monitoring_root(root: Path) -> Path:
    return root / MONITORING_DIR


def _latest_filing(item: dict[str, Any]) -> dict[str, Any]:
    return ((item.get("dart_enrichment") or {}).get("latest_filing") or {}) if item else {}


def _event_counts(item: dict[str, Any]) -> dict[str, int]:
    counts = ((item.get("event_digest") or {}).get("counts") or {}) if item else {}
    return {str(key): int(value or 0) for key, value in counts.items()}


def _news_scores(item: dict[str, Any]) -> dict[str, Any]:
    news = (item.get("news_analysis") or {}) if item else {}
    scores = news.get("scores") or {}
    return {
        "news_tone": news.get("tone"),
        "news_article_count": news.get("article_count"),
        "news_momentum": scores.get("momentum") if isinstance(scores, dict) else None,
        "news_risk": scores.get("risk") if isinstance(scores, dict) else None,
    }


def _safe_round(value: Any, digits: int = 1) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _pct_change(old: Any, new: Any) -> float | None:
    try:
        old_num = float(old)
        new_num = float(new)
    except (TypeError, ValueError):
        return None
    if old_num == 0:
        return None
    return round((new_num - old_num) / abs(old_num), 4)


def _brief(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": row.get("code"),
        "name": row.get("name"),
        "group": row.get("group"),
        "shortlist_score": row.get("shortlist_score"),
        "recommendation": row.get("recommendation"),
        "market_cap_krw": row.get("market_cap_krw"),
        "sector": row.get("sector"),
        "deal_window": row.get("deal_window"),
        "white_knight_need": row.get("white_knight_need"),
        "latest_filing_date": row.get("latest_filing_date"),
        "latest_filing_name": row.get("latest_filing_name"),
        "news_tone": row.get("news_tone"),
        "news_article_count": row.get("news_article_count"),
        "news_momentum": row.get("news_momentum"),
        "news_risk": row.get("news_risk"),
        "reason": row.get("reason"),
    }


def _row_for_item(item: dict[str, Any], shortlist_row: dict[str, Any]) -> dict[str, Any]:
    scores = item.get("scores") or {}
    signals = item.get("deal_signals") or {}
    signal_scores = signals.get("scores") or {}
    latest = _latest_filing(item)
    return {
        **shortlist_row,
        "current_price_krw": item.get("current_price_krw"),
        "pbr": item.get("pbr"),
        "radar_score": scores.get("total"),
        "status_flags": item.get("status_flags") or [],
        "business_keywords": item.get("business_keywords") or [],
        "latest_filing_date": latest.get("rcept_dt"),
        "latest_filing_name": latest.get("report_nm"),
        "latest_filing_rcp_no": latest.get("rcept_no") or latest.get("rcp_no"),
        "filing_count": (item.get("dart_enrichment") or {}).get("filing_count"),
        "event_counts": _event_counts(item),
        "deal_execution_score": signal_scores.get("deal_execution_score"),
        "governance_risk_score": signal_scores.get("governance_risk_score"),
        **_news_scores(item),
    }


def build_snapshot(prepared_items: list[dict[str, Any]], run_id: str | None = None) -> dict[str, Any]:
    shortlist_rows = shortlist_items(prepared_items)
    by_code = {str(row.get("code")): row for row in shortlist_rows}
    rows = []
    for item in prepared_items:
        code = str(item.get("code") or "")
        if not code or code not in by_code:
            continue
        rows.append(_row_for_item(item, by_code[code]))
    rows.sort(key=lambda row: (GROUP_ORDER.get(row.get("group"), 9), -(row.get("shortlist_score") or 0)))
    return {
        "run_id": run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "created_at": _now(),
        "counts": {group: sum(1 for row in rows if row.get("group") == group) for group in GROUP_ORDER},
        "items": rows,
    }


def load_latest_snapshot(root: Path) -> dict[str, Any] | None:
    path = _monitoring_root(root) / "latest_snapshot.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def latest_monitoring(root: Path) -> dict[str, Any]:
    path = _monitoring_root(root) / "latest.json"
    if not path.exists():
        return {"status": "not_run"}
    return json.loads(path.read_text(encoding="utf-8"))


def _is_important_filing(name: str | None) -> bool:
    text = name or ""
    return any(keyword in text for keyword in IMPORTANT_FILING_KEYWORDS)


def _event_deltas(old: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    old_counts = old.get("event_counts") or {}
    new_counts = new.get("event_counts") or {}
    deltas = []
    for category, new_count in new_counts.items():
        old_count = int(old_counts.get(category) or 0)
        delta = int(new_count or 0) - old_count
        if delta > 0:
            deltas.append(
                {
                    "category": category,
                    "old_count": old_count,
                    "new_count": int(new_count or 0),
                    "delta": delta,
                }
            )
    deltas.sort(key=lambda item: (EVENT_PRIORITY.get(item["category"], 9), -item["delta"]))
    return deltas


def _alert(
    alert_type: str,
    severity: str,
    row: dict[str, Any],
    title: str,
    detail: str,
) -> dict[str, Any]:
    return {
        "type": alert_type,
        "severity": severity,
        "title": title,
        "detail": detail,
        **_brief(row),
    }


def diff_snapshots(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    current_items = {str(row.get("code")): row for row in current.get("items", [])}
    top_attention = [_brief(row) for row in current.get("items", [])[:12]]
    base = {
        "status": "ok",
        "run_id": current.get("run_id"),
        "generated_at": _now(),
        "current_snapshot_at": current.get("created_at"),
        "counts": current.get("counts") or {},
        "top_attention": top_attention,
    }

    if previous is None:
        return {
            **base,
            "baseline": True,
            "previous_run_id": None,
            "summary": "첫 모니터링 기준선이 생성되었습니다. 다음 실행부터 신규 후보, 등급 이동, 중요 공시 변화가 별도로 표시됩니다.",
            "alerts": [],
            "changes": {
                "new_candidates": [],
                "removed_candidates": [],
                "group_changes": [],
                "score_changes": [],
                "market_cap_changes": [],
                "latest_filing_changes": [],
                "event_count_changes": [],
                "news_risk_changes": [],
            },
        }

    previous_items = {str(row.get("code")): row for row in previous.get("items", [])}
    new_candidates = [_brief(current_items[code]) for code in current_items.keys() - previous_items.keys()]
    removed_candidates = [_brief(previous_items[code]) for code in previous_items.keys() - current_items.keys()]
    group_changes = []
    score_changes = []
    market_cap_changes = []
    latest_filing_changes = []
    event_count_changes = []
    news_risk_changes = []
    alerts = []

    for code in current_items.keys() & previous_items.keys():
        old = previous_items[code]
        new = current_items[code]
        old_group = old.get("group")
        new_group = new.get("group")
        if old_group != new_group:
            change = {
                **_brief(new),
                "old_group": old_group,
                "new_group": new_group,
            }
            group_changes.append(change)
            if new_group == "즉시 검토":
                alerts.append(
                    _alert(
                        "group_entered_immediate",
                        "high",
                        new,
                        f"{new.get('name')} 즉시 검토 진입",
                        f"{old_group or '-'}에서 {new_group}로 이동했습니다.",
                    )
                )

        old_score = _safe_round(old.get("shortlist_score"))
        new_score = _safe_round(new.get("shortlist_score"))
        if old_score is not None and new_score is not None:
            delta = round(new_score - old_score, 1)
            if abs(delta) >= 5:
                change = {
                    **_brief(new),
                    "old_score": old_score,
                    "new_score": new_score,
                    "delta": delta,
                }
                score_changes.append(change)
                if delta >= 8:
                    alerts.append(
                        _alert(
                            "score_jump",
                            "medium",
                            new,
                            f"{new.get('name')} 점수 급등",
                            f"숏리스트 점수가 {old_score}에서 {new_score}로 상승했습니다.",
                        )
                    )

        cap_change = _pct_change(old.get("market_cap_krw"), new.get("market_cap_krw"))
        if cap_change is not None and abs(cap_change) >= 0.12:
            market_cap_changes.append(
                {
                    **_brief(new),
                    "old_market_cap_krw": old.get("market_cap_krw"),
                    "new_market_cap_krw": new.get("market_cap_krw"),
                    "pct_change": cap_change,
                }
            )

        old_filing_key = (old.get("latest_filing_rcp_no"), old.get("latest_filing_date"), old.get("latest_filing_name"))
        new_filing_key = (new.get("latest_filing_rcp_no"), new.get("latest_filing_date"), new.get("latest_filing_name"))
        if new_filing_key != old_filing_key and any(new_filing_key):
            change = {
                **_brief(new),
                "old_latest_filing_date": old.get("latest_filing_date"),
                "old_latest_filing_name": old.get("latest_filing_name"),
            }
            latest_filing_changes.append(change)
            if _is_important_filing(new.get("latest_filing_name")):
                alerts.append(
                    _alert(
                        "important_filing",
                        "high",
                        new,
                        f"{new.get('name')} 중요 공시",
                        str(new.get("latest_filing_name") or ""),
                    )
                )

        deltas = _event_deltas(old, new)
        if deltas:
            event_count_changes.append({**_brief(new), "deltas": deltas})
            first = deltas[0]
            if first["category"] in {"자금조달", "지분/경영권", "거래소/상장유지"}:
                alerts.append(
                    _alert(
                        "event_count_increase",
                        "medium",
                        new,
                        f"{new.get('name')} {first['category']} 이벤트 증가",
                        f"{first['old_count']}건에서 {first['new_count']}건으로 증가했습니다.",
                    )
                )

        old_news_risk = _safe_round(old.get("news_risk"))
        new_news_risk = _safe_round(new.get("news_risk"))
        if new_news_risk is not None:
            news_delta = None if old_news_risk is None else round(new_news_risk - old_news_risk, 1)
            if new_news_risk >= 65 or (news_delta is not None and news_delta >= 20):
                change = {
                    **_brief(new),
                    "old_news_risk": old_news_risk,
                    "new_news_risk": new_news_risk,
                    "delta": news_delta,
                }
                news_risk_changes.append(change)
                alerts.append(
                    _alert(
                        "news_risk",
                        "high" if new_news_risk >= 65 else "medium",
                        new,
                        f"{new.get('name')} 뉴스 리스크 확인",
                        f"최근 6개월 뉴스 리스크 {new_news_risk}점, 뉴스 톤 {new.get('news_tone') or '-'}입니다.",
                    )
                )

    for row in new_candidates:
        if row.get("group") == "즉시 검토":
            alerts.append(
                _alert(
                    "new_immediate_candidate",
                    "high",
                    row,
                    f"{row.get('name')} 신규 즉시 검토 후보",
                    "새 후보가 즉시 검토 그룹으로 들어왔습니다.",
                )
            )

    severity_order = {"high": 0, "medium": 1, "low": 2}
    alerts.sort(key=lambda row: (severity_order.get(row.get("severity"), 9), -(row.get("shortlist_score") or 0)))
    group_changes.sort(key=lambda row: (GROUP_ORDER.get(row.get("new_group"), 9), -(row.get("shortlist_score") or 0)))
    score_changes.sort(key=lambda row: abs(row.get("delta") or 0), reverse=True)
    market_cap_changes.sort(key=lambda row: abs(row.get("pct_change") or 0), reverse=True)
    news_risk_changes.sort(key=lambda row: row.get("new_news_risk") or 0, reverse=True)

    return {
        **base,
        "baseline": False,
        "previous_run_id": previous.get("run_id"),
        "summary": f"알림 {len(alerts)}건, 등급 이동 {len(group_changes)}건, 중요/신규 공시 변화 {len(latest_filing_changes)}건, 뉴스 리스크 변화 {len(news_risk_changes)}건을 감지했습니다.",
        "alerts": alerts[:30],
        "changes": {
            "new_candidates": new_candidates[:30],
            "removed_candidates": removed_candidates[:30],
            "group_changes": group_changes[:30],
            "score_changes": score_changes[:30],
            "market_cap_changes": market_cap_changes[:30],
            "latest_filing_changes": latest_filing_changes[:30],
            "event_count_changes": event_count_changes[:30],
            "news_risk_changes": news_risk_changes[:30],
        },
    }


def create_monitoring_report(root: Path, prepared_items: list[dict[str, Any]], run_id: str | None = None) -> dict[str, Any]:
    monitoring_root = _monitoring_root(root)
    snapshots_dir = monitoring_root / "snapshots"
    changes_dir = monitoring_root / "changes"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    changes_dir.mkdir(parents=True, exist_ok=True)

    previous = load_latest_snapshot(root)
    current = build_snapshot(prepared_items, run_id)
    report = diff_snapshots(previous, current)

    snapshot_path = snapshots_dir / f"{current['run_id']}.json"
    report_path = changes_dir / f"{current['run_id']}.json"
    snapshot_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (monitoring_root / "latest_snapshot.json").write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    (monitoring_root / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def monitoring_csv(report: dict[str, Any]) -> bytes:
    rows = []
    for alert in report.get("alerts") or []:
        rows.append({"section": "alert", **alert})
    for section, changes in (report.get("changes") or {}).items():
        for change in changes or []:
            rows.append({"section": section, **change})
    buffer = io.StringIO()
    fieldnames = [
        "section",
        "severity",
        "type",
        "code",
        "name",
        "group",
        "shortlist_score",
        "title",
        "detail",
        "deal_window",
        "white_knight_need",
        "latest_filing_date",
        "latest_filing_name",
        "news_tone",
        "news_article_count",
        "news_momentum",
        "news_risk",
        "old_news_risk",
        "new_news_risk",
        "reason",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")
