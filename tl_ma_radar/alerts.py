from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from io import StringIO
from typing import Any


SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "watch": 3, "opportunity": 4, "info": 5}


def _num(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _score(item: dict[str, Any]) -> float:
    scores = _dict(item.get("scores"))
    return _num(item.get("priority_score") or item.get("shortlist_score") or scores.get("total"))


def _parse_due_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _today_kst() -> date:
    # The app does not require pytz; UTC date is conservative enough for due-date alerting.
    return datetime.now(timezone.utc).date()


def _add(
    rows: list[dict[str, Any]],
    item: dict[str, Any],
    *,
    severity: str,
    category: str,
    title: str,
    detail: str,
    next_action: str,
    source: str,
    due_date: str | None = None,
) -> None:
    rows.append(
        {
            "severity": severity,
            "category": category,
            "code": item.get("code"),
            "name": item.get("name"),
            "title": title,
            "detail": detail,
            "next_action": next_action,
            "source": source,
            "due_date": due_date or "",
            "priority_score": round(_score(item), 1),
            "shortlist_group": item.get("shortlist_group"),
            "recommendation": item.get("recommendation"),
        }
    )


def _dart_alerts(rows: list[dict[str, Any]], item: dict[str, Any]) -> None:
    report = _dict(item.get("report_intelligence"))
    source = _dict(report.get("source"))
    extracts = _dict(source.get("structured_extracts"))
    audit = _dict(extracts.get("audit_opinion"))
    cb = _dict(extracts.get("convertible_bonds"))
    related = _dict(extracts.get("related_party_transactions"))
    findings = _list(report.get("findings"))
    severity = str(report.get("severity") or "").lower()

    if severity in {"critical", "high"}:
        finding = _dict(findings[0]) if findings else {}
        _add(
            rows,
            item,
            severity="critical" if severity == "critical" else "high",
            category="DART 원문",
            title=f"{item.get('name')} DART 원문 리스크",
            detail=str(finding.get("title") or "감사/지배구조/자금조달 원문 리스크 확인 필요"),
            next_action=str(finding.get("next_step") or "최신 사업보고서·감사보고서 원문 PDF에서 리스크 문단 확인"),
            source="report_intelligence",
        )

    audit_severity = str(audit.get("severity") or "").lower()
    if audit_severity in {"critical", "high"}:
        _add(
            rows,
            item,
            severity="critical" if audit_severity == "critical" else "high",
            category="감사의견",
            title=f"{item.get('name')} 감사의견 확인",
            detail=f"구조화 추출 결과: {audit.get('opinion') or '미확인'}",
            next_action="감사의견, 계속기업 불확실성, 내부회계관리제도 문단을 원문 대조",
            source="structured_extracts.audit_opinion",
        )

    if cb.get("has_convertible"):
        counts = _dict(cb.get("counts"))
        _add(
            rows,
            item,
            severity="medium",
            category="CB/BW",
            title=f"{item.get('name')} CB/BW 오버행 확인",
            detail=" / ".join(f"{key} {value}" for key, value in list(counts.items())[:4]) or "전환사채·신주인수권부사채 언급 감지",
            next_action="미상환 잔액, 전환가액, 리픽싱, 콜옵션·풋옵션 조건을 완전희석 지분율에 반영",
            source="structured_extracts.convertible_bonds",
        )

    if related.get("has_related_party"):
        counts = _dict(related.get("counts"))
        _add(
            rows,
            item,
            severity="watch",
            category="특수관계",
            title=f"{item.get('name')} 특수관계 거래 확인",
            detail=" / ".join(f"{key} {value}" for key, value in list(counts.items())[:4]) or "특수관계자 거래 언급 감지",
            next_action="자회사·관계사·대주주 거래의 공정가치, 이사회/주총, 공시 리스크 확인",
            source="structured_extracts.related_party_transactions",
        )


def _news_alerts(rows: list[dict[str, Any]], item: dict[str, Any]) -> None:
    news = _dict(item.get("news_analysis"))
    scores = _dict(news.get("scores"))
    risk = _num(scores.get("risk"))
    tone = str(news.get("tone") or "-")
    if risk >= 75:
        severity = "high"
    elif risk >= 55:
        severity = "medium"
    else:
        return
    _add(
        rows,
        item,
        severity=severity,
        category="뉴스",
        title=f"{item.get('name')} 최근 6개월 뉴스 리스크",
        detail=f"뉴스 리스크 {risk:.1f}점, 톤 {tone}, 기사 {news.get('article_count') or 0}건",
        next_action="뉴스 이벤트와 DART 공시 발생일을 대조하고 단발성 이슈인지 구조적 리스크인지 분리",
        source="news_analysis",
    )


def _ic_alerts(rows: list[dict[str, Any]], item: dict[str, Any]) -> None:
    ic = _dict(item.get("ic_package"))
    readiness = _num(ic.get("readiness_score"))
    if readiness < 72:
        return
    _add(
        rows,
        item,
        severity="opportunity",
        category="IC",
        title=f"{item.get('name')} IC 상정 후보",
        detail=f"IC 준비도 {readiness:.1f}점, 판단 {ic.get('decision') or '-'}",
        next_action=str(ic.get("next_action") or "후보별 1페이지 IC 요약을 다운로드해 사람 검수 진행"),
        source="ic_package",
    )


def _quality_alerts(rows: list[dict[str, Any]], item: dict[str, Any]) -> None:
    quality = _dict(item.get("data_quality"))
    score = _num(quality.get("score"), 100.0)
    if score >= 70:
        return
    severity = "high" if score < 55 else "medium"
    _add(
        rows,
        item,
        severity=severity,
        category="데이터",
        title=f"{item.get('name')} 데이터 신뢰도 보강",
        detail=f"신뢰도 {score:.1f}점, 등급 {quality.get('grade') or '-'}",
        next_action="DART 원문, 최신 공시, 뉴스 표본을 재수집한 뒤 스코어를 재계산",
        source="data_quality",
    )


def _workflow_alerts(rows: list[dict[str, Any]], item: dict[str, Any]) -> None:
    workflow = _dict(item.get("workflow"))
    due = _parse_due_date(workflow.get("due_date"))
    if not due:
        return
    days_left = (due - _today_kst()).days
    if days_left > 3:
        return
    severity = "critical" if days_left < 0 else "high"
    label = "기한 초과" if days_left < 0 else f"D-{days_left}"
    _add(
        rows,
        item,
        severity=severity,
        category="파이프라인",
        title=f"{item.get('name')} 검토 기한 {label}",
        detail=f"상태 {workflow.get('status') or '-'}, 담당 {workflow.get('owner') or '-'}, 다음 액션 {workflow.get('next_action') or '-'}",
        next_action="담당자 확인 후 상태·다음 액션·검토 기한 업데이트",
        source="candidate_workflow",
        due_date=str(due),
    )


def _monitoring_alerts(monitoring: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = []
    if not monitoring:
        return rows
    for alert in _list(monitoring.get("alerts"))[:30]:
        if not isinstance(alert, dict):
            continue
        rows.append(
            {
                "severity": str(alert.get("severity") or "watch").lower(),
                "category": str(alert.get("type") or "모니터링"),
                "code": alert.get("code"),
                "name": alert.get("name"),
                "title": alert.get("title") or f"{alert.get('name')} 변화 감지",
                "detail": alert.get("detail") or alert.get("reason") or "",
                "next_action": "변화 공시/뉴스 원문을 확인하고 후보 상태를 갱신",
                "source": "monitoring",
                "due_date": "",
                "priority_score": _num(alert.get("shortlist_score")),
                "shortlist_group": alert.get("group"),
                "recommendation": alert.get("recommendation"),
            }
        )
    return rows


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    out = []
    for row in rows:
        key = (str(row.get("code") or ""), str(row.get("category") or ""), str(row.get("title") or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def build_alerts(items: list[dict[str, Any]], monitoring: dict[str, Any] | None = None, limit: int = 80) -> dict[str, Any]:
    rows: list[dict[str, Any]] = _monitoring_alerts(monitoring)
    for item in items:
        _dart_alerts(rows, item)
        _news_alerts(rows, item)
        _ic_alerts(rows, item)
        _quality_alerts(rows, item)
        _workflow_alerts(rows, item)

    rows = _dedupe(rows)
    rows.sort(
        key=lambda row: (
            SEVERITY_ORDER.get(str(row.get("severity") or "info").lower(), 9),
            -_num(row.get("priority_score")),
            str(row.get("name") or ""),
        )
    )
    counts: dict[str, int] = {}
    categories: dict[str, int] = {}
    for row in rows:
        severity = str(row.get("severity") or "info")
        category = str(row.get("category") or "기타")
        counts[severity] = counts.get(severity, 0) + 1
        categories[category] = categories.get(category, 0) + 1
    return {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": len(rows),
            "severity": counts,
            "category": categories,
            "action_required": sum(counts.get(key, 0) for key in ("critical", "high", "medium")),
        },
        "items": rows[:limit],
        "alert_policy": [
            "Critical/High는 당일 원문 확인 및 후보 상태 업데이트",
            "CB/BW, 특수관계 거래는 완전희석 지분율과 공시 리스크에 즉시 반영",
            "IC opportunity는 1페이지 IC 요약 다운로드 후 사람 검수",
            "데이터 신뢰도 하락은 재수집 후 재스코어링",
        ],
    }


def alerts_csv(payload: dict[str, Any]) -> bytes:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["severity", "category", "code", "name", "title", "detail", "next_action", "due_date", "source", "priority_score"])
    for row in payload.get("items") or []:
        writer.writerow(
            [
                row.get("severity"),
                row.get("category"),
                row.get("code"),
                row.get("name"),
                row.get("title"),
                row.get("detail"),
                row.get("next_action"),
                row.get("due_date"),
                row.get("source"),
                row.get("priority_score"),
            ]
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")
