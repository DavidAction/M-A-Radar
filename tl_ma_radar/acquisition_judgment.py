from __future__ import annotations

from typing import Any

from tl_ma_radar.scoring import clamp


def _score_value(item: dict[str, Any], key: str) -> float:
    return float((item.get("scores") or {}).get(key) or 0)


def _signal_score(item: dict[str, Any], key: str) -> float:
    signals = item.get("deal_signals") or {}
    return float((signals.get("scores") or {}).get(key) or 0)


def _analysis(item: dict[str, Any]) -> dict[str, Any]:
    analysis = item.get("report_analysis")
    return analysis if isinstance(analysis, dict) else {}


def _news(item: dict[str, Any]) -> dict[str, Any]:
    analysis = item.get("news_analysis")
    return analysis if isinstance(analysis, dict) else {}


def _news_score(item: dict[str, Any], key: str) -> float:
    scores = _news(item).get("scores") or {}
    return float(scores.get(key) or 0) if isinstance(scores, dict) else 0.0


def _tone(score: float, reverse: bool = False) -> str:
    good = score <= 35 if reverse else score >= 68
    warn = score <= 62 if reverse else score >= 45
    if good:
        return "good"
    if warn:
        return "warn"
    return "risk"


def _decision(attractiveness: float, risk: float, execution: float) -> str:
    if risk >= 82:
        return "선 리스크 해소"
    if attractiveness >= 70 and execution >= 55:
        return "우선 접촉"
    if attractiveness >= 55:
        return "심층 실사"
    if attractiveness >= 42:
        return "모니터링"
    return "보류"


def _ratio_text(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"


def build_acquisition_judgment(item: dict[str, Any]) -> dict[str, Any]:
    scores = item.get("scores") or {}
    signals = item.get("deal_signals") or {}
    analysis = _analysis(item)
    cap_case = item.get("capital_raise_case") or {}
    new_share_ratio = cap_case.get("implied_new_share_ratio")
    shareholder_ratio = item.get("largest_shareholder_ratio")

    strategic_fit = _score_value(item, "strategic_fit") or (
        (_score_value(item, "tl_synergy") + _score_value(item, "renes_synergy")) / 2
    )
    execution = _signal_score(item, "deal_execution_score")
    governance = _signal_score(item, "governance_risk_score")
    white_knight = _signal_score(item, "white_knight_need_score")
    news_risk = _news_score(item, "risk")
    news_momentum = _news_score(item, "momentum")
    risk = clamp(_score_value(item, "risk_penalty") * 0.54 + governance * 0.38 + news_risk * 0.08)
    exit_structure_fit = clamp(
        (new_share_ratio or 0) * 100 * 0.55
        + _signal_score(item, "control_openness_score") * 0.25
        + white_knight * 0.12
        + min(len(analysis.get("exit_structure_signals") or []) * 8, 16)
    )
    attractiveness = clamp(
        _score_value(item, "total") * 0.34
        + strategic_fit * 0.22
        + execution * 0.20
        + exit_structure_fit * 0.16
        + _score_value(item, "report_evidence") * 0.08
        + news_momentum * 0.04
        - max(risk - 65, 0) * 0.22
    )

    decision = _decision(attractiveness, risk, execution)
    fit_points = [
        f"TL/르네스 전략 적합도 {round(strategic_fit, 1)}점",
        f"300억 유증 시 신규 지분 약 {_ratio_text(new_share_ratio)}",
        f"딜 실행 창: {signals.get('deal_window') or '-'}",
    ]
    if shareholder_ratio is not None:
        fit_points.append(f"최대주주 지분 약 {_ratio_text(shareholder_ratio)}")
    if analysis.get("business_keywords"):
        fit_points.append("보고서 기반 시너지 키워드: " + ", ".join((analysis.get("business_keywords") or [])[:4]))
    news = _news(item)
    if news.get("status") == "ok":
        fit_points.append(
            f"최근 6개월 뉴스 톤: {news.get('tone') or '-'} "
            f"(모멘텀 {round(news_momentum, 1)}점, 리스크 {round(news_risk, 1)}점)"
        )

    blockers = []
    if risk >= 65:
        blockers.append(f"거버넌스/재무 리스크 점검 필요 {round(risk, 1)}점")
    audit = analysis.get("audit_signals") or []
    if audit:
        blockers.append("감사의견/계속기업 신호: " + ", ".join(audit[:3]))
    financing = analysis.get("financing_signals") or []
    if financing:
        blockers.append("자금조달 이슈: " + ", ".join(financing[:3]))
    if analysis.get("related_party_signals"):
        blockers.append("특수관계자 거래와 관계회사 구조 확인 필요")
    if news_risk >= 45:
        blockers.append("최근 뉴스상 리스크 키워드가 강해 기사 원문과 후속 공시 대조 필요")
    if not blockers:
        blockers.append("중대한 문구는 현재 자동 분석 기준에서 제한적으로 탐지됨")

    diligence_focus = [
        "최대주주 및 특수관계인 지분, 담보, 보호예수 상태 확인",
        "300억 유상증자 후 지분율과 경영권 확보 가능성 검토",
        "주요 매출처와 매출채권 회수 가능성 확인",
        "TL/르네스 거래로 연결 가능한 품목, 설비, 인허가 확인",
        "최근 6개월 뉴스의 계약/자금조달/최대주주/리스크 이벤트와 공시 일치 여부 확인",
    ]
    if audit:
        diligence_focus.insert(0, "감사의견, 계속기업 불확실성, 내부회계 문구 원문 확인")
    if financing:
        diligence_focus.insert(1, "CB/BW, 감자, 유증 조건과 잠재 희석률 확인")

    return {
        "decision": decision,
        "tone": _tone(attractiveness) if risk < 82 else "risk",
        "summary": (
            f"{decision}: 인수 매력도 {round(attractiveness, 1)}점, 실행 가능성 {round(execution, 1)}점, "
            f"리스크 {round(risk, 1)}점으로 분류됩니다."
        ),
        "scores": {
            "attractiveness": round(attractiveness, 1),
            "strategic_fit": round(strategic_fit, 1),
            "execution_feasibility": round(execution, 1),
            "exit_structure_fit": round(exit_structure_fit, 1),
            "risk_level": round(risk, 1),
            "white_knight_need": round(white_knight, 1),
        },
        "tones": {
            "attractiveness": _tone(attractiveness),
            "strategic_fit": _tone(strategic_fit),
            "execution_feasibility": _tone(execution),
            "exit_structure_fit": _tone(exit_structure_fit),
            "risk_level": _tone(risk, reverse=True),
        },
        "fit_points": fit_points,
        "blockers": blockers,
        "diligence_focus": diligence_focus,
    }
