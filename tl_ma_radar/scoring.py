from __future__ import annotations

from typing import Any

from tl_ma_radar.config import Settings


TL_KEYWORDS = {
    "석유화학",
    "화학",
    "원료",
    "수입",
    "유통",
    "수지",
    "플라스틱",
    "첨가제",
    "용제",
}

RENES_KEYWORDS = {
    "가공",
    "납품",
    "코팅",
    "필름",
    "소재",
    "정밀화학",
    "폐수",
    "자원순환",
    "재생원료",
    "2차전지",
    "양극재",
}


def clamp(value: float, lower: float = 0, upper: float = 100) -> float:
    return max(lower, min(upper, value))


def _keyword_score(keywords: list[str], target: set[str]) -> float:
    normalized = " ".join(keywords)
    hits = sum(1 for word in target if word in normalized)
    return clamp(hits * 18, 0, 100)


def _report_analysis(item: dict[str, Any]) -> dict[str, Any]:
    analysis = item.get("report_analysis")
    return analysis if isinstance(analysis, dict) else {}


def _news_analysis(item: dict[str, Any]) -> dict[str, Any]:
    analysis = item.get("news_analysis")
    return analysis if isinstance(analysis, dict) else {}


def _news_score(item: dict[str, Any], key: str) -> float:
    scores = _news_analysis(item).get("scores") or {}
    if not isinstance(scores, dict):
        return 0.0
    return float(scores.get(key) or 0)


def _report_signal_count(item: dict[str, Any], key: str) -> int:
    values = _report_analysis(item).get(key) or []
    return len(values) if isinstance(values, list) else 0


def _undervaluation(item: dict[str, Any], settings: Settings) -> float:
    market_cap = item.get("market_cap_krw") or settings.market_cap_limit_krw
    pbr = item.get("pbr")
    score = 0.0
    if market_cap <= 10_000_000_000:
        score += 45
    elif market_cap <= 20_000_000_000:
        score += 35
    elif market_cap <= settings.market_cap_limit_krw:
        score += 25
    if pbr is not None:
        if pbr <= 0.4:
            score += 40
        elif pbr <= 0.7:
            score += 25
        elif pbr <= 1:
            score += 10
    if item.get("equity_krw") and market_cap:
        discount = 1 - (market_cap / max(item["equity_krw"], 1))
        score += clamp(discount * 30, 0, 20)
    return clamp(score)


def _core_business(item: dict[str, Any]) -> float:
    revenue = item.get("revenue_krw") or 0
    op = item.get("operating_profit_krw")
    ocf = item.get("operating_cash_flow_krw")
    score = 0.0
    if revenue >= 50_000_000_000:
        score += 40
    elif revenue >= 20_000_000_000:
        score += 28
    elif revenue >= 10_000_000_000:
        score += 18
    if op is not None:
        score += 25 if op > 0 else 8
    if ocf is not None:
        score += 25 if ocf > 0 else 6
    if item.get("has_operating_assets"):
        score += 10
    analysis = _report_analysis(item)
    if analysis.get("business_keywords"):
        score += 8
    if _report_signal_count(item, "customer_signals"):
        score += 8
    return clamp(score)


def _opportunity(item: dict[str, Any]) -> float:
    flags = set(item.get("status_flags", []))
    score = 0.0
    if "초저시총" in flags:
        score += 20
    if "관리종목" in flags:
        score += 24
    if "투자주의환기" in flags:
        score += 18
    if "계속기업불확실성" in flags:
        score += 18
    if "유동성갭" in flags:
        score += 18
    if "낮은최대주주지분" in flags:
        score += 14
    if "CB오버행" in flags:
        score += 8
    if "CB/BW공시" in flags:
        score += 8
    if "유상증자공시" in flags:
        score += 10
    if "감자공시" in flags:
        score += 10
    if "최대주주변경" in flags:
        score += 14
    if "적자" in flags:
        score += 6
    shareholder_ratio = item.get("largest_shareholder_ratio")
    if shareholder_ratio is not None:
        if shareholder_ratio < 0.15:
            score += 22
        elif shareholder_ratio < 0.25:
            score += 15
        elif shareholder_ratio < 0.35:
            score += 8
    score += min(_report_signal_count(item, "control_signals") * 7, 18)
    score += min(_report_signal_count(item, "financing_signals") * 5, 16)
    return clamp(score)


def _risk_penalty(item: dict[str, Any]) -> float:
    flags = set(item.get("status_flags", []))
    penalty = 0.0
    if "상장폐지위험" in flags:
        penalty += 24
    if "거래정지" in flags or "거래정지/거래부진확인필요" in flags:
        penalty += 20
    if "회생절차" in flags or "파산신청" in flags:
        penalty += 30
    if "불성실공시" in flags:
        penalty += 12
    if "계속기업불확실성" in flags:
        penalty += 18
    if "감사의견리스크" in flags:
        penalty += 28
    if "매출채권검증필요" in flags:
        penalty += 12
    if "CB오버행" in flags:
        penalty += 8
    if "감자공시" in flags:
        penalty += 8
    if "적자" in flags:
        penalty += 5
    analysis = _report_analysis(item)
    audit_signals = set(analysis.get("audit_signals") or [])
    financing_signals = set(analysis.get("financing_signals") or [])
    if "부적정/의견거절" in audit_signals:
        penalty += 30
    if "한정의견" in audit_signals:
        penalty += 18
    if "계속기업불확실성" in audit_signals:
        penalty += 16
    if "자본잠식" in financing_signals:
        penalty += 16
    if _report_signal_count(item, "related_party_signals"):
        penalty += 8
    return clamp(penalty)


def _strategic_fit(item: dict[str, Any], tl_score: float, renes_score: float) -> float:
    score = tl_score * 0.42 + renes_score * 0.50
    analysis = _report_analysis(item)
    if analysis.get("inferred_sector"):
        score += 8
    score += min(_report_signal_count(item, "customer_signals") * 4, 10)
    score += min(_report_signal_count(item, "exit_structure_signals") * 4, 10)
    return clamp(score)


def _report_evidence(item: dict[str, Any]) -> float:
    analysis = _report_analysis(item)
    if not analysis:
        return 0.0
    base = float(analysis.get("evidence_strength") or 0)
    parsed_reports = analysis.get("reports_analyzed") or []
    if isinstance(parsed_reports, list):
        base += min(len(parsed_reports) * 6, 18)
    if analysis.get("largest_shareholder"):
        base += 8
    return clamp(base)


def _capital_raise_case(item: dict[str, Any], settings: Settings) -> dict[str, Any]:
    market_cap = max(item.get("market_cap_krw") or 0, 1)
    new_money = settings.capital_raise_krw
    implied_new_share_ratio = new_money / (market_cap + new_money)
    equity = item.get("equity_krw")
    debt = item.get("debt_krw")
    after_equity = equity + new_money if equity is not None else None
    before_debt_ratio = debt / equity if debt is not None and equity else None
    after_debt_ratio = debt / after_equity if debt is not None and after_equity else None
    return {
        "new_money_krw": new_money,
        "implied_new_share_ratio": round(implied_new_share_ratio, 4),
        "after_equity_krw": after_equity,
        "before_debt_ratio": before_debt_ratio,
        "after_debt_ratio": after_debt_ratio,
    }


def _recommendation(total: float, penalty: float) -> str:
    if total >= 72 and penalty < 30:
        return "우선 검토"
    if total >= 55:
        return "조건부 검토"
    if total >= 42:
        return "관찰"
    return "보류"


def score_candidate(item: dict[str, Any], settings: Settings) -> dict[str, Any]:
    keywords = item.get("business_keywords", [])
    tl_score = round(_keyword_score(keywords, TL_KEYWORDS), 1)
    renes_score = round(_keyword_score(keywords, RENES_KEYWORDS), 1)
    scores = {
        "undervaluation": round(_undervaluation(item, settings), 1),
        "core_business": round(_core_business(item), 1),
        "opportunity": round(_opportunity(item), 1),
        "tl_synergy": tl_score,
        "renes_synergy": renes_score,
        "risk_penalty": round(_risk_penalty(item), 1),
        "strategic_fit": round(_strategic_fit(item, tl_score, renes_score), 1),
        "report_evidence": round(_report_evidence(item), 1),
        "news_momentum": round(_news_score(item, "momentum"), 1),
        "news_risk": round(_news_score(item, "risk"), 1),
    }
    signals = item.get("deal_signals") or {}
    signal_scores = signals.get("scores") or {}
    deal_execution = signal_scores.get("deal_execution_score") or 0
    weighted = (
        scores["undervaluation"] * 0.17
        + scores["core_business"] * 0.15
        + scores["opportunity"] * 0.18
        + scores["tl_synergy"] * 0.13
        + scores["renes_synergy"] * 0.17
        + scores["strategic_fit"] * 0.12
        + scores["report_evidence"] * 0.06
        + scores["news_momentum"] * 0.04
        + deal_execution * 0.08
        - scores["risk_penalty"] * 0.13
        - scores["news_risk"] * 0.035
    )
    weighted -= max(scores["risk_penalty"] - 65, 0) * 0.22
    weighted -= max((signal_scores.get("governance_risk_score") or 0) - 78, 0) * 0.18
    scores["total"] = round(clamp(weighted), 1)
    result = dict(item)
    result["scores"] = scores
    result["capital_raise_case"] = _capital_raise_case(item, settings)
    result["recommendation"] = _recommendation(scores["total"], scores["risk_penalty"])
    return result
