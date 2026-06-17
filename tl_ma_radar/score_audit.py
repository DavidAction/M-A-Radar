from __future__ import annotations

from typing import Any


def _score(item: dict[str, Any], key: str) -> float:
    return float((item.get("scores") or {}).get(key) or 0)


def _judgment_score(item: dict[str, Any], key: str) -> float:
    judgment = item.get("acquisition_judgment") or {}
    return float((judgment.get("scores") or {}).get(key) or 0)


def _signals(item: dict[str, Any], key: str) -> list[str]:
    values = (item.get("report_analysis") or {}).get(key) or []
    return values if isinstance(values, list) else []


def _news_score(item: dict[str, Any], key: str) -> float:
    scores = (item.get("news_analysis") or {}).get("scores") or {}
    return float(scores.get(key) or 0) if isinstance(scores, dict) else 0.0


def _verdict(item: dict[str, Any]) -> str:
    risk = _judgment_score(item, "risk_level")
    total = _score(item, "total")
    fit = _score(item, "strategic_fit")
    news_risk = _news_score(item, "risk")
    if risk >= 82:
        return "과대평가 주의"
    if news_risk >= 65 and total >= 60:
        return "뉴스 리스크 확인"
    if total >= 68 and fit >= 80 and risk < 72:
        return "상위 유지"
    if risk >= 70:
        return "리스크 할인"
    if fit < 45:
        return "시너지 재검토"
    return "검토 유지"


def _checks(item: dict[str, Any]) -> list[str]:
    checks = []
    risk = _judgment_score(item, "risk_level")
    total = _score(item, "total")
    strategic_fit = _score(item, "strategic_fit")
    core = _score(item, "core_business")
    news_momentum = _news_score(item, "momentum")
    news_risk = _news_score(item, "risk")
    shareholder_ratio = item.get("largest_shareholder_ratio")
    if total >= 65 and risk >= 70:
        checks.append("상위권이나 리스크가 높아 선실사 필요")
    if strategic_fit >= 80:
        checks.append("TL/르네스 시너지 근거 강함")
    elif strategic_fit < 45:
        checks.append("시너지 근거 약함")
    if core < 35:
        checks.append("본업 안정성 추가 검증")
    if news_momentum >= 45:
        checks.append(f"최근 뉴스 모멘텀 확인: {news_momentum}점")
    if news_risk >= 45:
        checks.append(f"최근 뉴스 리스크 원문 대조: {news_risk}점")
    if shareholder_ratio is not None and shareholder_ratio < 0.15:
        checks.append("최대주주 지분 낮아 경영권 협상 가능성")
    audit = _signals(item, "audit_signals")
    if audit:
        checks.append("감사의견/계속기업 문구 확인: " + ", ".join(audit[:3]))
    financing = _signals(item, "financing_signals")
    if financing:
        checks.append("자금조달/희석 이슈 확인: " + ", ".join(financing[:3]))
    if not checks:
        checks.append("자동 검수상 큰 튜닝 이슈 없음")
    return checks[:5]


def build_score_audit(items: list[dict[str, Any]], limit: int = 20) -> dict[str, Any]:
    ranked = sorted(items, key=lambda item: _score(item, "total"), reverse=True)
    rows = []
    for rank, item in enumerate(ranked[:limit], start=1):
        judgment = item.get("acquisition_judgment") or {}
        rows.append(
            {
                "rank": rank,
                "code": item.get("code"),
                "name": item.get("name"),
                "score": _score(item, "total"),
                "decision": judgment.get("decision"),
                "attractiveness": _judgment_score(item, "attractiveness"),
                "strategic_fit": _score(item, "strategic_fit"),
                "risk_level": _judgment_score(item, "risk_level"),
                "report_evidence": _score(item, "report_evidence"),
                "news_momentum": _news_score(item, "momentum"),
                "news_risk": _news_score(item, "risk"),
                "verdict": _verdict(item),
                "checks": _checks(item),
            }
        )
    return {
        "status": "ok",
        "limit": limit,
        "summary": {
            "top_count": len(rows),
            "risk_discount": sum(1 for row in rows if row["verdict"] in {"리스크 할인", "과대평가 주의", "뉴스 리스크 확인"}),
            "keep": sum(1 for row in rows if row["verdict"] == "상위 유지"),
            "synergy_review": sum(1 for row in rows if row["verdict"] == "시너지 재검토"),
        },
        "items": rows,
    }
