from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean
from typing import Any


BENCHMARKS = {
    "121850": "코이즈",
    "247660": "나노씨엠에스",
    "368600": "아이씨에이치",
    "177350": "베셀",
}


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _score(item: dict[str, Any], key: str) -> float:
    return float(_dict(item.get("scores")).get(key) or 0)


def _judgment(item: dict[str, Any], key: str) -> float:
    return float(_dict(_dict(item.get("acquisition_judgment")).get("scores")).get(key) or 0)


def _news(item: dict[str, Any], key: str) -> float:
    return float(_dict(_dict(item.get("news_analysis")).get("scores")).get(key) or 0)


def _quality(item: dict[str, Any]) -> float:
    return float(_dict(item.get("data_quality")).get("score") or 0)


def _decision(item: dict[str, Any]) -> str:
    ic = _dict(item.get("investment_case"))
    return str(ic.get("decision") or item.get("recommendation") or "-")


def _risk_bucket(item: dict[str, Any]) -> str:
    risk = _judgment(item, "risk_level")
    report = str(_dict(item.get("report_intelligence")).get("severity") or "").lower()
    news_risk = _news(item, "risk")
    if report == "critical" or risk >= 85 or news_risk >= 80:
        return "High Risk"
    if report == "high" or risk >= 70 or news_risk >= 60:
        return "Watch"
    return "Normal"


def _row(item: dict[str, Any], rank: int) -> dict[str, Any]:
    total = _score(item, "total")
    risk = _judgment(item, "risk_level")
    fit = _score(item, "strategic_fit")
    evidence = _score(item, "report_evidence")
    quality = _quality(item)
    risk_bucket = _risk_bucket(item)
    flags: list[str] = []
    if rank <= 20 and risk_bucket == "High Risk":
        flags.append("상위권 고위험")
    if fit >= 80 and total < 60:
        flags.append("시너지 과소반영")
    if quality and quality < 70:
        flags.append("데이터 보강")
    if evidence < 45:
        flags.append("보고서 근거 약함")
    if not flags:
        flags.append("산식 일관")
    return {
        "rank": rank,
        "code": item.get("code"),
        "name": item.get("name"),
        "decision": _decision(item),
        "score": total,
        "priority_score": item.get("priority_score"),
        "strategic_fit": fit,
        "risk_level": risk,
        "report_evidence": evidence,
        "data_quality": quality,
        "news_risk": _news(item, "risk"),
        "risk_bucket": risk_bucket,
        "flags": flags[:4],
    }


def _metric_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    return {
        "avg_score": round(mean(float(row["score"]) for row in rows), 1),
        "avg_risk": round(mean(float(row["risk_level"]) for row in rows), 1),
        "avg_fit": round(mean(float(row["strategic_fit"]) for row in rows), 1),
        "avg_quality": round(mean(float(row["data_quality"]) for row in rows), 1),
        "high_risk_top": sum(1 for row in rows if row["risk_bucket"] == "High Risk"),
        "weak_evidence_top": sum(1 for row in rows if float(row["report_evidence"] or 0) < 45),
        "low_quality_top": sum(1 for row in rows if float(row["data_quality"] or 0) < 70),
    }


def build_calibration_report(items: list[dict[str, Any]], limit: int = 30) -> dict[str, Any]:
    ranked = sorted(
        items,
        key=lambda item: -float(item.get("priority_score") or item.get("shortlist_score") or _score(item, "total")),
    )
    top_rows = [_row(item, rank) for rank, item in enumerate(ranked[:limit], start=1)]
    all_rows = [_row(item, rank) for rank, item in enumerate(ranked, start=1)]

    decision_counts: dict[str, int] = {}
    risk_counts: dict[str, int] = {}
    for row in all_rows:
        decision_counts[str(row["decision"])] = decision_counts.get(str(row["decision"]), 0) + 1
        risk_counts[str(row["risk_bucket"])] = risk_counts.get(str(row["risk_bucket"]), 0) + 1

    benchmark_rows = []
    rank_by_code = {str(item.get("code")): rank for rank, item in enumerate(ranked, start=1)}
    for code, fallback_name in BENCHMARKS.items():
        found = next((item for item in ranked if str(item.get("code")) == code), None)
        if found:
            benchmark_rows.append(_row(found, rank_by_code[code]))
        else:
            benchmark_rows.append(
                {
                    "code": code,
                    "name": fallback_name,
                    "rank": None,
                    "score": None,
                    "flags": ["후보군 없음"],
                }
            )

    high_risk_top = [row for row in top_rows if row["risk_bucket"] == "High Risk"]
    weak_evidence = [row for row in top_rows if float(row["report_evidence"] or 0) < 45]
    under_synergy = [row for row in all_rows if float(row["strategic_fit"] or 0) >= 80 and float(row["score"] or 0) < 60]

    recommendations = [
        "상위 30개 중 High Risk 후보는 점수 유지 전에 감사의견, 계속기업, CB/BW, 특수관계 거래 원문을 다시 확인합니다.",
        "전략 적합도가 80점 이상인데 총점이 60점 미만인 후보는 TL/르네스 시너지 가중치 과소반영 여부를 별도 검수합니다.",
        "보고서 근거 45점 미만 후보는 IC 보고서에 올리기 전 원문 PDF/TXT 재분석과 추출 피드백을 먼저 확정합니다.",
    ]
    if len(high_risk_top) >= 10:
        recommendations.insert(0, "상위권 고위험 후보 비중이 높아 리스크 감점 가중치 상향 또는 우선 검토 컷오프 재조정이 필요합니다.")
    if len(weak_evidence) >= 10:
        recommendations.insert(0, "상위권 보고서 근거가 약하므로 DART 원문 신호를 점수 산식에 더 강하게 반영해야 합니다.")
    if len(under_synergy) >= 20:
        recommendations.append("시너지 과소반영 후보가 많아 사업 키워드 보강 결과를 반영한 재스코어링을 정례화합니다.")

    return {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "limit": limit,
        "summary": {
            "candidate_count": len(all_rows),
            "top": _metric_summary(top_rows),
            "decision_counts": decision_counts,
            "risk_counts": risk_counts,
            "high_risk_top_count": len(high_risk_top),
            "weak_evidence_top_count": len(weak_evidence),
            "under_synergy_count": len(under_synergy),
        },
        "recommendations": recommendations[:5],
        "benchmarks": benchmark_rows,
        "items": top_rows,
        "watchlists": {
            "high_risk_top": high_risk_top[:10],
            "weak_evidence_top": weak_evidence[:10],
            "under_synergy": under_synergy[:10],
        },
    }
