from __future__ import annotations

import csv
from datetime import datetime, timezone
from io import StringIO
from typing import Any


BAD_SHAREHOLDER_TOKENS = (
    "출석률",
    "의안내용",
    "종속기업",
    "연결대상",
    "유효지분율",
    "주요출자자",
    "본문 위치",
    "단위 :",
)


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _analysis(item: dict[str, Any]) -> dict[str, Any]:
    return _dict(item.get("report_analysis"))


def _structured(item: dict[str, Any]) -> dict[str, Any]:
    analysis = _analysis(item)
    return _dict(analysis.get("structured_extracts"))


def _signal_counts(item: dict[str, Any]) -> dict[str, Any]:
    return _dict(_analysis(item).get("signal_counts"))


def _shareholder_quality(shareholder: dict[str, Any]) -> tuple[str, list[str]]:
    name = str(shareholder.get("name") or "").strip()
    ratio = _float(shareholder.get("ratio"))
    issues: list[str] = []
    if not name:
        issues.append("최대주주명 누락")
    if ratio <= 0:
        issues.append("최대주주 지분율 누락")
    if any(token in name for token in BAD_SHAREHOLDER_TOKENS):
        issues.append("최대주주명 오탐 가능")
    if len(name) > 45:
        issues.append("최대주주명 과다 추출")
    if ratio > 100:
        issues.append("최대주주 지분율 100% 초과")
    if issues:
        return "검수 필요", issues
    return "정상", []


def _audit_opinion(structured: dict[str, Any]) -> dict[str, Any]:
    opinion = _dict(structured.get("audit_opinion"))
    if opinion:
        return opinion
    return {"opinion": "-", "severity": "unknown", "counts": {}, "snippets": []}


def _coverage_score(item: dict[str, Any]) -> tuple[int, list[str], list[str]]:
    analysis = _analysis(item)
    structured = _structured(item)
    data_quality = _dict(item.get("data_quality"))
    shareholder = _dict(analysis.get("largest_shareholder"))
    audit = _audit_opinion(structured)
    counts = _signal_counts(item)

    score = 0
    issues: list[str] = []
    recommendations: list[str] = []

    text_chars = int(_float(analysis.get("text_chars")))
    if text_chars >= 80_000:
        score += 20
    elif text_chars >= 10_000:
        score += 12
        issues.append("본문 커버리지 보통")
    else:
        issues.append("사업/감사보고서 본문 부족")
        recommendations.append("사업보고서·감사보고서 원문 재다운로드 후 본문 재분석")

    shareholder_status, shareholder_issues = _shareholder_quality(shareholder)
    if shareholder_status == "정상":
        score += 18
    else:
        issues.extend(shareholder_issues)
        recommendations.append("최대주주 표 전용 파서로 재추출")

    severity = str(audit.get("severity") or "unknown")
    opinion = str(audit.get("opinion") or "-")
    if opinion != "-":
        score += 16
    else:
        issues.append("감사의견 미추출")
        recommendations.append("감사의견/계속기업 문단 우선순위 룰 보강")
    if severity == "critical":
        recommendations.append("의견거절·부적정 후보는 감사보고서 원문 수동 확인")

    financing_count = sum(int(_float(value)) for value in _dict(counts.get("financing")).values())
    related_count = sum(int(_float(value)) for value in _dict(counts.get("related_party")).values())
    control_count = sum(int(_float(value)) for value in _dict(counts.get("control")).values())
    if financing_count > 0:
        score += 10
    else:
        issues.append("CB/BW·유상증자 신호 약함")
    if related_count > 0:
        score += 9
    else:
        issues.append("특수관계 거래 신호 미확인")
    if control_count > 0:
        score += 9
    else:
        issues.append("경영권/지분 신호 미확인")

    snippets = _list(analysis.get("snippets"))
    if len(snippets) >= 4:
        score += 10
    elif snippets:
        score += 5
        issues.append("근거 스니펫 부족")
    else:
        issues.append("근거 스니펫 없음")
        recommendations.append("보고서 근거 문장 추출 범위 확대")

    quality_score = _float(data_quality.get("score"))
    if quality_score >= 80:
        score += 8
    elif quality_score:
        score += 4
        recommendations.append("데이터 품질 보강 대상")

    if not recommendations:
        recommendations.append("현재 파서 결과를 IC 검토 입력값으로 사용 가능")

    return min(score, 100), issues, recommendations


def _verdict(score: int, issues: list[str]) -> str:
    if score >= 82 and not any("오탐" in issue or "누락" in issue for issue in issues):
        return "투자심의 사용 가능"
    if score >= 62:
        return "애널리스트 검수"
    return "원문 보강 우선"


def _top_counts(counts: dict[str, Any], key: str, limit: int = 3) -> str:
    rows = sorted(_dict(counts.get(key)).items(), key=lambda row: int(_float(row[1])), reverse=True)
    if not rows:
        return "-"
    return ", ".join(f"{name} {int(_float(value))}" for name, value in rows[:limit])


def build_extraction_audit(items: list[dict[str, Any]], limit: int = 30) -> dict[str, Any]:
    ordered = sorted(
        items,
        key=lambda item: -_float(item.get("priority_score") or item.get("shortlist_score") or _dict(item.get("scores")).get("total")),
    )[:limit]
    rows: list[dict[str, Any]] = []
    for rank, item in enumerate(ordered, 1):
        analysis = _analysis(item)
        structured = _structured(item)
        shareholder = _dict(analysis.get("largest_shareholder"))
        audit = _audit_opinion(structured)
        counts = _signal_counts(item)
        score, issues, recommendations = _coverage_score(item)
        rows.append(
            {
                "rank": rank,
                "code": item.get("code"),
                "name": item.get("name"),
                "confidence_score": score,
                "verdict": _verdict(score, issues),
                "shareholder": shareholder.get("name") or "-",
                "shareholder_ratio": shareholder.get("ratio"),
                "shareholder_quality": _shareholder_quality(shareholder)[0],
                "audit_opinion": audit.get("opinion") or "-",
                "audit_severity": audit.get("severity") or "unknown",
                "text_chars": int(_float(analysis.get("text_chars"))),
                "evidence_strength": analysis.get("evidence_strength"),
                "business_keywords": _list(analysis.get("business_keywords"))[:6],
                "control_signals": _top_counts(counts, "control"),
                "financing_signals": _top_counts(counts, "financing"),
                "related_party_signals": _top_counts(counts, "related_party"),
                "issues": issues[:5],
                "recommended_tuning": recommendations[:4],
            }
        )

    verdict_counts: dict[str, int] = {}
    for row in rows:
        verdict_counts[str(row["verdict"])] = verdict_counts.get(str(row["verdict"]), 0) + 1
    avg = round(sum(int(row["confidence_score"]) for row in rows) / len(rows), 1) if rows else 0

    return {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "sample_size": len(rows),
            "average_confidence": avg,
            "verdict_counts": verdict_counts,
            "manual_review": verdict_counts.get("애널리스트 검수", 0),
            "remediation_first": verdict_counts.get("원문 보강 우선", 0),
        },
        "items": rows,
    }


def extraction_audit_csv(payload: dict[str, Any]) -> bytes:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "rank",
            "code",
            "name",
            "confidence_score",
            "verdict",
            "shareholder",
            "shareholder_ratio",
            "shareholder_quality",
            "audit_opinion",
            "audit_severity",
            "text_chars",
            "control_signals",
            "financing_signals",
            "related_party_signals",
            "issues",
            "recommended_tuning",
        ]
    )
    for row in payload.get("items") or []:
        if not isinstance(row, dict):
            continue
        writer.writerow(
            [
                row.get("rank"),
                row.get("code"),
                row.get("name"),
                row.get("confidence_score"),
                row.get("verdict"),
                row.get("shareholder"),
                row.get("shareholder_ratio"),
                row.get("shareholder_quality"),
                row.get("audit_opinion"),
                row.get("audit_severity"),
                row.get("text_chars"),
                row.get("control_signals"),
                row.get("financing_signals"),
                row.get("related_party_signals"),
                "; ".join(row.get("issues") or []),
                "; ".join(row.get("recommended_tuning") or []),
            ]
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")
