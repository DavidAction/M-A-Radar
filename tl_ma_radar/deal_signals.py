from __future__ import annotations

from datetime import date, datetime
from typing import Any

from tl_ma_radar.scoring import clamp


EVENT_RULES = {
    "rescue_need": {
        "관리종목": 24,
        "투자주의환기": 18,
        "상장폐지": 28,
        "거래정지": 20,
        "파산": 26,
        "회생": 26,
        "감사의견": 16,
        "계속기업": 18,
    },
    "control_openness": {
        "최대주주변경": 28,
        "경영권": 26,
        "주식양수도": 24,
        "대량보유": 14,
        "임원ㆍ주요주주": 12,
        "주요주주": 10,
        "자기주식처분": 10,
    },
    "financing_pressure": {
        "유상증자": 24,
        "전환사채": 22,
        "신주인수권부사채": 22,
        "증권신고서": 16,
        "청약결과": 14,
        "증권발행결과": 14,
        "감자": 18,
        "자본감소": 18,
        "권리락": 10,
    },
    "governance_risk": {
        "불성실공시": 22,
        "감사의견": 18,
        "의견거절": 32,
        "횡령": 30,
        "배임": 30,
        "소송": 12,
        "특수관계": 16,
        "파산": 20,
        "회생": 20,
        "거래정지": 18,
        "상장폐지": 24,
    },
}

FLAG_WEIGHTS = {
    "rescue_need": {
        "관리종목": 30,
        "투자주의환기": 22,
        "계속기업불확실성": 28,
        "자본잠식": 28,
        "상장폐지위험": 36,
        "거래정지": 24,
        "거래정지/거래부진확인필요": 16,
        "회생절차": 34,
        "파산신청": 34,
        "적자": 12,
        "유동성갭": 24,
    },
    "control_openness": {
        "낮은최대주주지분": 28,
        "최대주주변경": 30,
        "CB오버행": 12,
    },
    "financing_pressure": {
        "유상증자공시": 26,
        "감자공시": 24,
        "CB/BW공시": 24,
        "CB오버행": 18,
        "유동성갭": 18,
        "자본잠식": 20,
    },
    "governance_risk": {
        "불성실공시": 22,
        "감사의견리스크": 34,
        "상장폐지위험": 30,
        "거래정지": 22,
        "회생절차": 28,
        "파산신청": 28,
        "특수관계거래": 20,
        "매출채권검증필요": 16,
    },
}


def parse_yyyymmdd(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None


def infer_as_of(filings: list[dict[str, Any]]) -> date:
    dates = [parsed for filing in filings if (parsed := parse_yyyymmdd(filing.get("rcept_dt")))]
    return max(dates) if dates else date.today()


def recency_multiplier(days_ago: int) -> float:
    if days_ago <= 30:
        return 1.0
    if days_ago <= 90:
        return 0.85
    if days_ago <= 180:
        return 0.65
    if days_ago <= 365:
        return 0.45
    return 0.2


def flag_score(flags: list[str], category: str) -> tuple[float, list[str]]:
    weights = FLAG_WEIGHTS[category]
    matched = [flag for flag in flags if flag in weights]
    return clamp(sum(weights[flag] for flag in matched), 0, 70), matched


def event_matches(filings: list[dict[str, Any]], category: str, as_of: date) -> tuple[float, list[dict[str, Any]]]:
    rules = EVENT_RULES[category]
    events: list[dict[str, Any]] = []
    raw_score = 0.0
    seen: set[tuple[str, str]] = set()
    for filing in filings:
        report_name = (filing.get("report_nm") or "").strip()
        filing_date = parse_yyyymmdd(filing.get("rcept_dt"))
        if not report_name or not filing_date:
            continue
        days_ago = max((as_of - filing_date).days, 0)
        for keyword, weight in rules.items():
            if keyword not in report_name:
                continue
            key = (category, keyword)
            adjusted = weight * recency_multiplier(days_ago)
            raw_score += adjusted
            if key not in seen or days_ago <= 90:
                events.append(
                    {
                        "category": category,
                        "keyword": keyword,
                        "report_nm": report_name,
                        "rcept_dt": filing.get("rcept_dt"),
                        "days_ago": days_ago,
                        "score": round(adjusted, 1),
                        "rcp_no": filing.get("rcept_no"),
                    }
                )
                seen.add(key)
            break
    events.sort(key=lambda event: (event["days_ago"], -event["score"]))
    return clamp(raw_score, 0, 45), events[:8]


def financial_adders(item: dict[str, Any]) -> dict[str, float]:
    adders = {
        "rescue_need": 0.0,
        "control_openness": 0.0,
        "financing_pressure": 0.0,
        "governance_risk": 0.0,
    }
    market_cap = item.get("market_cap_krw") or 0
    equity = item.get("equity_krw")
    debt = item.get("debt_krw")
    op = item.get("operating_profit_krw")
    ocf = item.get("operating_cash_flow_krw")
    shareholder_ratio = item.get("largest_shareholder_ratio")

    if market_cap and market_cap <= 10_000_000_000:
        adders["control_openness"] += 12
        adders["rescue_need"] += 8
    if shareholder_ratio is not None:
        if shareholder_ratio < 0.15:
            adders["control_openness"] += 24
        elif shareholder_ratio < 0.25:
            adders["control_openness"] += 16
        elif shareholder_ratio < 0.35:
            adders["control_openness"] += 8
    if op is not None and op < 0:
        adders["rescue_need"] += 12
        adders["financing_pressure"] += 8
    if ocf is not None and ocf < 0:
        adders["financing_pressure"] += 12
    if equity is not None and debt is not None and equity > 0:
        debt_ratio = debt / equity
        if debt_ratio >= 2:
            adders["financing_pressure"] += 18
            adders["rescue_need"] += 12
        elif debt_ratio >= 1:
            adders["financing_pressure"] += 10
    return {key: clamp(value, 0, 30) for key, value in adders.items()}


def classify_need(score: float) -> str:
    if score >= 72:
        return "높음"
    if score >= 48:
        return "중간"
    return "낮음"


def classify_window(score: float, latest_event_days: int | None, governance_score: float) -> str:
    if governance_score >= 78:
        return "고위험 선실사"
    if score >= 70 and latest_event_days is not None and latest_event_days <= 45:
        return "즉시 접촉 후보"
    if score >= 55:
        return "탐색 접촉 후보"
    return "모니터링"


def signal_summary(item: dict[str, Any], scores: dict[str, float], need: str, window: str) -> str:
    return (
        f"백기사 필요도는 {need}, 딜 실행 창은 '{window}'로 분류됩니다. "
        f"재무구조 개선 필요 {scores['rescue_need_score']}점, 경영권 개방성 {scores['control_openness_score']}점, "
        f"자금조달 압박 {scores['financing_pressure_score']}점, 거버넌스 주의 {scores['governance_risk_score']}점입니다."
    )


def analyze_deal_signals(item: dict[str, Any], filings: list[dict[str, Any]]) -> dict[str, Any]:
    flags = item.get("status_flags") or []
    as_of = infer_as_of(filings)
    financial = financial_adders(item)
    category_scores: dict[str, float] = {}
    evidence: list[dict[str, Any]] = []
    matched_flags: dict[str, list[str]] = {}

    for category in EVENT_RULES:
        flag_component, matched = flag_score(flags, category)
        event_component, events = event_matches(filings, category, as_of)
        score = clamp(flag_component + event_component + financial[category])
        category_scores[f"{category}_score"] = round(score, 1)
        matched_flags[category] = matched
        evidence.extend(events)

    governance = category_scores["governance_risk_score"]
    white_knight_score = clamp(
        category_scores["rescue_need_score"] * 0.42
        + category_scores["financing_pressure_score"] * 0.34
        + category_scores["control_openness_score"] * 0.24
    )
    execution_score = clamp(
        category_scores["control_openness_score"] * 0.36
        + category_scores["financing_pressure_score"] * 0.25
        + category_scores["rescue_need_score"] * 0.24
        - governance * 0.20
        + 18
    )
    evidence.sort(key=lambda event: (event["days_ago"], -event["score"]))
    latest_days = evidence[0]["days_ago"] if evidence else None
    need = classify_need(white_knight_score)
    window = classify_window(execution_score, latest_days, governance)

    scores = {
        **category_scores,
        "white_knight_need_score": round(white_knight_score, 1),
        "deal_execution_score": round(execution_score, 1),
    }
    return {
        "as_of": as_of.isoformat(),
        "white_knight_need": need,
        "deal_window": window,
        "scores": scores,
        "matched_flags": matched_flags,
        "financial_adders": financial,
        "evidence_events": evidence[:14],
        "summary": signal_summary(item, scores, need, window),
    }
