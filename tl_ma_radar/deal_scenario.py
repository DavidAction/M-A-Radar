from __future__ import annotations

from typing import Any


def _num(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"


def _won(value: object) -> str:
    number = _num(value)
    if abs(number) >= 100_000_000:
        return f"{number / 100_000_000:,.1f}억"
    return f"{number:,.0f}원"


def _overhang_factor(item: dict[str, Any]) -> tuple[float, list[str]]:
    flags = set(str(flag) for flag in item.get("status_flags") or [])
    analysis = item.get("report_analysis") or {}
    financing = analysis.get("financing_signals") or []
    factor = 1.0
    reasons = []
    if "CB/BW공시" in flags or any("CB" in str(value) or "BW" in str(value) for value in financing):
        factor -= 0.10
        reasons.append("CB/BW 오버행 보수 반영")
    if "유상증자공시" in flags:
        factor -= 0.04
        reasons.append("기존 유상증자 이력 반영")
    if "감자공시" in flags or "자본잠식" in flags:
        factor -= 0.05
        reasons.append("감자/자본잠식 구조 변수 반영")
    return max(0.75, factor), reasons


def _control_feasibility(new_share: float, post_largest: float | None, shareholder: float | None) -> tuple[str, str]:
    if new_share >= 0.55:
        return "높음", "제3자배정만으로도 단순 지분율상 경영권 확보 가능성이 높습니다."
    if new_share >= 0.40:
        return "중간", "신규 지분은 의미 있으나 최대주주/우호지분 계약 또는 이사회 구성권이 필요합니다."
    if shareholder is not None and shareholder < 0.18 and new_share >= 0.30:
        return "중간", "기존 최대주주 지분이 낮아 우호지분 확보 시 경영권 협상 여지가 있습니다."
    if post_largest is not None and new_share > post_largest:
        return "중간", "유증 후 단순 비교로 신규 투자자가 최대주주가 될 가능성이 있습니다."
    return "낮음", "제3자배정만으로는 부족할 수 있어 기존 최대주주 지분 인수나 의결권 약정이 필요합니다."


def build_deal_scenario(item: dict[str, Any]) -> dict[str, Any]:
    cap_case = item.get("capital_raise_case") or {}
    new_money = _num(cap_case.get("new_money_krw"), 30_000_000_000)
    market_cap = max(_num(item.get("market_cap_krw"), 1), 1)
    new_share = _num(cap_case.get("implied_new_share_ratio"), new_money / (market_cap + new_money))
    shareholder = item.get("largest_shareholder_ratio")
    shareholder_ratio = _num(shareholder) if shareholder is not None else None
    existing_pool = max(0.0, 1 - new_share)
    post_largest = shareholder_ratio * existing_pool if shareholder_ratio is not None else None
    factor, overhang_reasons = _overhang_factor(item)
    conservative_new_share = new_share * factor
    conservative_post_largest = post_largest / factor if post_largest is not None and factor else post_largest
    control_grade, control_comment = _control_feasibility(new_share, post_largest, shareholder_ratio)
    conservative_grade, conservative_comment = _control_feasibility(
        conservative_new_share,
        conservative_post_largest,
        shareholder_ratio,
    )

    scenarios = [
        {
            "name": "Base Case",
            "new_share": round(new_share, 4),
            "post_largest_share": round(post_largest, 4) if post_largest is not None else None,
            "control_feasibility": control_grade,
            "comment": control_comment,
        },
        {
            "name": "Fully Diluted Conservative",
            "new_share": round(conservative_new_share, 4),
            "post_largest_share": round(conservative_post_largest, 4) if conservative_post_largest is not None else None,
            "control_feasibility": conservative_grade,
            "comment": conservative_comment,
        },
    ]
    return {
        "summary": (
            f"300억 유상증자 기준 신규 지분율은 {_pct(new_share)}, 보수적 희석 후 {_pct(conservative_new_share)}로 봅니다. "
            f"경영권 확보 가능성은 {control_grade}입니다."
        ),
        "new_money_krw": new_money,
        "market_cap_krw": market_cap,
        "scenarios": scenarios,
        "overhang_reasons": overhang_reasons,
        "control_requirements": [
            "최대주주 및 특수관계인 의결권 약정",
            "제3자배정 보호예수 및 이사회 구성권",
            "CB/BW 전환 후 완전희석 지분율 확인",
            "담보/질권 설정 주식의 의결권 행사 가능성 확인",
        ],
        "exit_structure_options": [
            {
                "structure": "자회사/관계사 인수",
                "use_case": "인수한 상장사를 통해 TL·르네스 네트워크 내 자산을 공정가치로 편입",
                "key_checks": "공정가치 평가, 이사회 승인, 특수관계자 거래 공시, 세무 검토",
            },
            {
                "structure": "비관계사 또는 자녀 회사 인수",
                "use_case": "합법적 1차 엑시트 목적의 자산 편입",
                "key_checks": "이해상충 절차, 외부평가기관, 자금사용 목적 공시, 부당지원 리스크",
            },
            {
                "structure": "영업양수도/공급계약",
                "use_case": "유증 전후 사업 시너지를 먼저 증명",
                "key_checks": "매출 인식 기준, 내부거래 가격, 지속가능성, 거래소 조회공시 가능성",
            },
        ],
        "legal_accounting_checkpoints": [
            "제3자배정 유상증자 발행가액 산정과 납입 가능성",
            "자금사용 목적과 실제 관계사/자회사 인수 계획의 일치성",
            "특수관계자 거래 및 이사의 자기거래 승인 절차",
            "외부평가기관 공정가치 평가와 손상 위험",
            "공시 전 미공개정보 이용 및 이해상충 통제",
        ],
        "display": {
            "new_money": _won(new_money),
            "market_cap": _won(market_cap),
            "new_share": _pct(new_share),
            "conservative_new_share": _pct(conservative_new_share),
            "post_largest_share": _pct(post_largest),
            "control_feasibility": control_grade,
        },
    }
