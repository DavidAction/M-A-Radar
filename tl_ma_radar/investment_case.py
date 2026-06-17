from __future__ import annotations

from typing import Any


SYNERGY_THEMES = {
    "석유화학": "TL 석유화학 수입·유통 물량과 교차 판매 가능",
    "용제/첨가제": "르네스 소재 가공·납품 역량과 제품 포트폴리오 확장 가능",
    "정밀화학/소재": "고객사 인증·스펙 영업 기반의 소재 밸류체인 확장 후보",
    "수지/플라스틱": "수지 원료 조달, 컴파운딩, 가공 납품으로 연결 가능",
    "2차전지": "첨가제·소재 응용처 확대 및 미래 성장 스토리 보강 가능",
    "환경/폐수": "화학물 취급·재활용·환경 규제 대응 서비스 확장 가능",
    "자원순환": "유통 원료와 회수·재가공 모델 결합 가능",
}


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _fmt_pct(value: object) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "-"


def _fmt_won(value: object) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if abs(number) >= 100_000_000:
        return f"{number / 100_000_000:,.1f}억"
    return f"{number:,.0f}원"


def _scorecard(item: dict[str, Any]) -> dict[str, int]:
    scores = _dict(item.get("scores"))
    deal_scenario = _dict(item.get("deal_scenario"))
    judgment = _dict(item.get("acquisition_judgment"))
    display = _dict(deal_scenario.get("display"))

    new_share = _float(display.get("new_share_raw") or deal_scenario.get("new_share"))
    conservative_share = _float(display.get("conservative_new_share_raw") or deal_scenario.get("conservative_new_share"))
    largest_share = _float(item.get("largest_shareholder_ratio")) / 100 if _float(item.get("largest_shareholder_ratio")) > 1 else _float(item.get("largest_shareholder_ratio"))

    synergy = min(100, int(_float(scores.get("tl_synergy")) + _float(scores.get("renes_synergy")) + _float(scores.get("core_business")) * 0.35))
    control = min(100, int((new_share * 100) * 1.2 + max(0, 30 - largest_share * 100) * 0.8))
    financing = min(100, int((conservative_share * 100) * 1.1 + _float(scores.get("dealability")) * 0.3))
    risk_adjusted = max(0, min(100, int(_float(scores.get("total")) - _float(scores.get("risk_penalty")) * 0.35)))
    exit_fit_text = str(judgment.get("exit_structure_fit") or "")
    exit_path = 82 if "높" in exit_fit_text or "우수" in exit_fit_text else 68 if "보통" in exit_fit_text else 55

    return {
        "control": control,
        "synergy": synergy,
        "financing": financing,
        "risk_adjusted": risk_adjusted,
        "exit_path": exit_path,
    }


def _decision(scorecard: dict[str, int], risk_level: str, audit_severity: str) -> tuple[str, str]:
    avg = sum(scorecard.values()) / max(1, len(scorecard))
    if audit_severity == "critical":
        return "조건부 추진", "감사의견·상장유지 리스크 해소를 선행조건으로 둔 구조화 딜"
    if avg >= 76 and risk_level not in {"높음", "매우 높음"}:
        return "우선 검토", "지배력 확보와 사업 시너지 모두 투자심의 상정 가능"
    if avg >= 62:
        return "조건부 검토", "가격·선행조건·CB/BW 오버행 통제가 전제되어야 함"
    return "보류", "현 단계에서는 원문 보강 또는 구조 개선 확인 후 재검토"


def _synergy_map(item: dict[str, Any]) -> list[dict[str, str]]:
    analysis = _dict(item.get("report_analysis"))
    keywords = _list(item.get("business_keywords")) + _list(analysis.get("business_keywords"))
    seen: set[str] = set()
    rows: list[dict[str, str]] = []
    for keyword in keywords:
        key = str(keyword)
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "keyword": key,
                "theme": SYNERGY_THEMES.get(key, "TL·르네스 네트워크와 고객/소재/가공 접점 확인 필요"),
                "fit": "High" if key in SYNERGY_THEMES else "Review",
            }
        )
        if len(rows) >= 6:
            break
    if not rows:
        rows.append(
            {
                "keyword": "사업 접점 미확정",
                "theme": "사업보고서 원문에서 제품·고객·원재료 키워드 추가 추출 필요",
                "fit": "Review",
            }
        )
    return rows


def _risk_conditions(item: dict[str, Any]) -> list[str]:
    analysis = _dict(item.get("report_analysis"))
    structured = _dict(analysis.get("structured_extracts"))
    audit = _dict(structured.get("audit_opinion"))
    risks = [str(value) for value in _list(analysis.get("risk_flags"))[:5]]
    conditions: list[str] = []
    severity = str(audit.get("severity") or "")
    if severity == "critical":
        conditions.append("감사의견·계속기업·상장유지 가능성에 대한 회계법인/거래소 확인")
    if any("CB" in risk or "유상증자" in risk or "감자" in risk for risk in risks):
        conditions.append("CB/BW, 유상증자, 감자 조건과 전환 가능 물량 락업 확인")
    if any("특수관계" in risk for risk in risks):
        conditions.append("특수관계자 거래, 자금대여, 보증의 정상가격·회수 가능성 확인")
    if any("매출채권" in risk for risk in risks):
        conditions.append("주요 매출처, 매출채권 회수, 재고자산 실재성 샘플 검증")
    if not conditions:
        conditions.append("최대주주 지분, 우발채무, 고객 집중도에 대한 표준 실사")
    return conditions


def _offer_range(item: dict[str, Any], scorecard: dict[str, int]) -> dict[str, str]:
    market_cap = _float(item.get("market_cap_krw"))
    if market_cap <= 0:
        return {
            "market_cap": "-",
            "control_premium": "-",
            "pre_money_range": "-",
            "comment": "시총 데이터 보강 후 협상 밴드 산정",
        }
    risk_adjusted = scorecard.get("risk_adjusted", 0)
    low = 0.05 if risk_adjusted < 55 else 0.1
    high = 0.18 if risk_adjusted < 55 else 0.28 if risk_adjusted < 75 else 0.35
    return {
        "market_cap": _fmt_won(market_cap),
        "control_premium": f"{low * 100:.0f}%~{high * 100:.0f}%",
        "pre_money_range": f"{_fmt_won(market_cap * (1 + low))}~{_fmt_won(market_cap * (1 + high))}",
        "comment": "리스크 높을수록 선행조건·에스크로·마일스톤형 지급 비중 확대",
    }


def _hundred_day_plan(item: dict[str, Any]) -> list[dict[str, str]]:
    synergy = _synergy_map(item)
    primary = synergy[0]["keyword"] if synergy else "사업 접점"
    return [
        {
            "period": "Day 0-30",
            "focus": "거래 안정화",
            "actions": "최대주주·CB/BW·우발채무 확정, 회계 리스크 클린업 계획 수립",
        },
        {
            "period": "Day 31-60",
            "focus": "시너지 검증",
            "actions": f"{primary} 관련 고객·원재료·가공 공정 실사와 TL/르네스 공동 영업 후보 도출",
        },
        {
            "period": "Day 61-100",
            "focus": "가치상승 실행",
            "actions": "유상증자 자금 사용계획, 관계사 거래 구조, IR 스토리와 공시 일정 정렬",
        },
    ]


def build_investment_case(item: dict[str, Any]) -> dict[str, Any]:
    report = _dict(item.get("report_analysis"))
    structured = _dict(report.get("structured_extracts"))
    audit = _dict(structured.get("audit_opinion"))
    judgment = _dict(item.get("acquisition_judgment"))
    scenario = _dict(item.get("deal_scenario"))
    display = _dict(scenario.get("display"))
    scorecard = _scorecard(item)
    decision, thesis = _decision(scorecard, str(judgment.get("risk_level") or ""), str(audit.get("severity") or ""))

    return {
        "decision": decision,
        "thesis": thesis,
        "scorecard": scorecard,
        "summary": {
            "control": f"300억 유증 기준 신규 지분 {display.get('new_share') or '-'}, 보수 기준 {display.get('conservative_new_share') or '-'}",
            "synergy": _synergy_map(item)[0]["theme"],
            "risk": judgment.get("risk_level") or audit.get("opinion") or "검토 필요",
            "exit_path": judgment.get("exit_structure_fit") or "관계사/자회사 1차 엑시트 구조 검토",
        },
        "dilution": {
            "base_new_share": display.get("new_share") or "-",
            "conservative_new_share": display.get("conservative_new_share") or "-",
            "post_largest_share": display.get("post_largest_share") or "-",
            "control_comment": "신규 유증 지분과 기존 최대주주 잔존 지분을 함께 비교해 경영권 확보 조건을 산정",
        },
        "synergy_map": _synergy_map(item),
        "offer_range": _offer_range(item, scorecard),
        "required_conditions": _risk_conditions(item),
        "hundred_day_plan": _hundred_day_plan(item),
        "ic_questions": [
            "인수 후 12개월 내 관계사·자회사 거래 구조를 공정거래/세무상 방어 가능한가?",
            "유상증자 300억 투입 시 기존 최대주주·CB/BW 오버행을 통제할 수 있는가?",
            "TL·르네스와 실제 매출/원가/고객 시너지가 숫자로 입증되는가?",
        ],
        "display": {
            "decision": decision,
            "headline": thesis,
            "control_score": scorecard["control"],
            "synergy_score": scorecard["synergy"],
            "financing_score": scorecard["financing"],
            "risk_adjusted_score": scorecard["risk_adjusted"],
            "base_new_share": display.get("new_share") or _fmt_pct(scenario.get("new_share")),
            "conservative_new_share": display.get("conservative_new_share") or _fmt_pct(scenario.get("conservative_new_share")),
        },
    }
