from __future__ import annotations

from typing import Any


def _score(item: dict[str, Any], key: str) -> float:
    return float((item.get("scores") or {}).get(key) or 0)


def _judgment_score(item: dict[str, Any], key: str) -> float:
    return float(((item.get("acquisition_judgment") or {}).get("scores") or {}).get(key) or 0)


def _signal_score(item: dict[str, Any], key: str) -> float:
    return float(((item.get("deal_signals") or {}).get("scores") or {}).get(key) or 0)


def _news_score(item: dict[str, Any], key: str) -> float:
    return float(((item.get("news_analysis") or {}).get("scores") or {}).get(key) or 0)


def _quality_score(item: dict[str, Any]) -> float:
    return float((item.get("data_quality") or {}).get("score") or 0)


def _pct(value: object) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "-"


def _won(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if abs(number) >= 100_000_000:
        return f"{number / 100_000_000:,.1f}억"
    return f"{number:,.0f}원"


def _decision(readiness: float, risk: float, quality: float, strategic_fit: float) -> tuple[str, str]:
    if quality < 55:
        return "자료 보강 후 재상정", "risk"
    if risk >= 86:
        return "고위험 보류", "risk"
    if readiness >= 72 and risk < 76:
        return "IC 상정 후보", "good"
    if readiness >= 62 and strategic_fit >= 70:
        return "조건부 IC 후보", "warn"
    if readiness >= 52:
        return "프리-IC 관찰", "warn"
    return "보류", "risk"


def _readiness(item: dict[str, Any]) -> float:
    readiness = (
        _score(item, "total") * 0.24
        + _score(item, "strategic_fit") * 0.22
        + _score(item, "report_evidence") * 0.16
        + _judgment_score(item, "execution_feasibility") * 0.14
        + _judgment_score(item, "exit_structure_fit") * 0.12
        + _quality_score(item) * 0.12
    )
    readiness -= max(_judgment_score(item, "risk_level") - 72, 0) * 0.25
    readiness -= max(_news_score(item, "risk") - 55, 0) * 0.10
    return round(max(0, min(100, readiness)), 1)


def _investment_case(item: dict[str, Any]) -> list[str]:
    cap_case = item.get("capital_raise_case") or {}
    keywords = item.get("business_keywords") or []
    points = [
        f"300억 유상증자 기준 신규 지분율은 약 {_pct(cap_case.get('implied_new_share_ratio'))}로 계산됩니다.",
        f"전략 적합도 {_score(item, 'strategic_fit'):.1f}점, 보고서 근거 {_score(item, 'report_evidence'):.1f}점으로 TL/르네스 접점 검토가 가능합니다.",
    ]
    if keywords:
        points.append("핵심 사업 키워드: " + ", ".join(str(word) for word in keywords[:6]))
    shareholder = item.get("largest_shareholder_ratio")
    if shareholder is not None:
        points.append(f"최대주주 지분율 {_pct(shareholder)} 기준으로 경영권 협상 여지를 별도 검토합니다.")
    news = item.get("news_analysis") or {}
    if news.get("article_count"):
        points.append(f"최근 6개월 뉴스 {news.get('article_count')}건, 톤은 {news.get('tone') or '-'}입니다.")
    return points[:5]


def _risk_mitigants(item: dict[str, Any]) -> list[dict[str, str]]:
    analysis = item.get("report_analysis") or {}
    flags = [str(flag) for flag in item.get("status_flags") or []]
    risks: list[dict[str, str]] = []
    if _judgment_score(item, "risk_level") >= 70 or flags:
        risks.append(
            {
                "risk": "공시/재무 리스크",
                "mitigant": "감사의견, 계속기업, 자본잠식, 거래정지 사유를 원문 기준으로 재확인하고 선행조건에 반영합니다.",
            }
        )
    if analysis.get("financing_signals") or "CB/BW공시" in flags:
        risks.append(
            {
                "risk": "CB/BW 및 희석",
                "mitigant": "전환가액, 리픽싱, 미상환 잔액, 콜옵션/풋옵션을 캡테이블에 반영합니다.",
            }
        )
    if analysis.get("related_party_signals") or "특수관계거래" in flags:
        risks.append(
            {
                "risk": "특수관계/관계사 거래",
                "mitigant": "자녀 회사·관계사 인수 구조는 이사회, 공정가치, 공시, 세무 검토를 선행합니다.",
            }
        )
    if _news_score(item, "risk") >= 45:
        risks.append(
            {
                "risk": "시장 뉴스 리스크",
                "mitigant": "부정 기사와 관련 공시의 사실관계를 매칭하고 최근 6개월 이후 이벤트를 재검색합니다.",
            }
        )
    if not risks:
        risks.append(
            {
                "risk": "중대 자동 리스크 미식별",
                "mitigant": "실사 전 단계에서는 누락 가능성을 전제로 원문 보고서와 주요 계약을 확인합니다.",
            }
        )
    return risks[:5]


def _diligence_workplan(item: dict[str, Any]) -> list[dict[str, str]]:
    judgment = item.get("acquisition_judgment") or {}
    focus = judgment.get("diligence_focus") or item.get("key_diligence") or []
    defaults = [
        "최대주주 및 우호지분, 담보/질권, 의결권 제한 여부 확인",
        "300억 유상증자 후 지분율, CB/BW 전환 후 완전희석 지분율 산정",
        "TL/르네스와 연결 가능한 매출처, 원재료, 가공/납품 품목 확인",
        "감사의견, 계속기업 불확실성, 관리/환기 사유 원문 확인",
        "자회사/관계사/비관계사 인수 가능 자산과 공정가치 검토",
    ]
    rows = []
    for index, task in enumerate((focus or defaults)[:6], start=1):
        rows.append(
            {
                "workstream": ["지배구조", "재무/회계", "사업 시너지", "법무/공시", "거래구조", "PMI"][index - 1],
                "task": str(task),
                "owner": ["IB/딜팀", "회계법인", "TL/르네스", "법무법인", "딜팀", "PMI TF"][index - 1],
                "target": f"D+{index * 3}",
            }
        )
    return rows


def _hundred_day_plan(item: dict[str, Any]) -> list[str]:
    return [
        "D+0~30: 경영권 안정화, 공시 리스크 정리, 주요 임직원/거래처 커뮤니케이션",
        "D+30~60: TL/르네스와 구매·가공·납품 연결 가능 품목별 파일럿 계약 설계",
        "D+60~100: 관계사/자회사 인수 후보와 공정가치 평가, 이사회 승인 패키지 준비",
        "D+100 이후: 유상증자 자금 사용 내역, 구조개선 KPI, 후속 M&A 파이프라인 점검",
    ]


def _deal_structure(item: dict[str, Any]) -> list[dict[str, str]]:
    cap_case = item.get("capital_raise_case") or {}
    shareholder = item.get("largest_shareholder_ratio")
    return [
        {"label": "기본 구조", "value": "제3자배정 유상증자 + 경영권/우호지분 협상"},
        {"label": "신규 자금", "value": _won(cap_case.get("new_money_krw"))},
        {"label": "시가총액", "value": _won(item.get("market_cap_krw"))},
        {"label": "유증 후 신규 지분", "value": _pct(cap_case.get("implied_new_share_ratio"))},
        {"label": "현재 최대주주 지분", "value": _pct(shareholder)},
        {"label": "우선 확인", "value": "완전희석 지분율, 보호예수, 담보/질권, 최대주주 의사"},
    ]


def _board_questions(item: dict[str, Any]) -> list[str]:
    return [
        "티엘홀딩스가 확보해야 할 최소 지분율과 이사회 구성권은 얼마인가?",
        "300억 유상증자 자금 중 관계사/자회사 인수에 배정 가능한 금액과 공시 리스크는 무엇인가?",
        "최대주주, CB/BW 보유자, 주요 채권자 중 거래 성사에 영향을 주는 이해관계자는 누구인가?",
        "TL/르네스와 12개월 내 실제 매출 또는 원가 절감으로 연결될 품목은 무엇인가?",
        "관리/환기/계속기업 이슈가 있다면 해소 일정과 선행조건은 무엇인가?",
    ]


def build_ic_package(item: dict[str, Any]) -> dict[str, Any]:
    readiness = _readiness(item)
    risk = _judgment_score(item, "risk_level")
    quality = _quality_score(item)
    strategic_fit = _score(item, "strategic_fit")
    decision, tone = _decision(readiness, risk, quality, strategic_fit)
    workflow = item.get("workflow") or {}
    next_action = workflow.get("next_action") or "IR/최대주주 접촉 가능성 및 최신 보고서 원문 확인"
    return {
        "decision": decision,
        "tone": tone,
        "readiness_score": readiness,
        "risk_score": round(risk, 1),
        "data_quality_score": round(quality, 1),
        "summary": (
            f"{decision}: IC 준비도 {readiness:.1f}점, 리스크 {risk:.1f}점, "
            f"데이터 신뢰도 {quality:.1f}점 기준입니다."
        ),
        "next_action": next_action,
        "investment_case": _investment_case(item),
        "deal_structure": _deal_structure(item),
        "risk_mitigants": _risk_mitigants(item),
        "diligence_workplan": _diligence_workplan(item),
        "hundred_day_plan": _hundred_day_plan(item),
        "board_questions": _board_questions(item),
        "gates": [
            "최대주주/우호지분 사전 의향 확인",
            "감사보고서 및 최근 분·반기보고서 원문 리스크 확인",
            "300억 유상증자 후 완전희석 지분율 산정",
            "관계사/자회사 인수 구조의 공정가치·공시·세무 검토",
        ],
    }


def build_ic_package_summary(items: list[dict[str, Any]], limit: int = 12) -> dict[str, Any]:
    rows = []
    for item in items:
        package = item.get("ic_package")
        if not isinstance(package, dict):
            package = build_ic_package(item)
        rows.append(
            {
                "code": item.get("code"),
                "name": item.get("name"),
                "decision": package.get("decision"),
                "tone": package.get("tone"),
                "readiness_score": package.get("readiness_score"),
                "risk_score": package.get("risk_score"),
                "data_quality_score": package.get("data_quality_score"),
                "next_action": package.get("next_action"),
            }
        )
    rows.sort(key=lambda row: float(row.get("readiness_score") or 0), reverse=True)
    counts: dict[str, int] = {}
    for row in rows:
        decision = str(row.get("decision") or "미분류")
        counts[decision] = counts.get(decision, 0) + 1
    return {
        "status": "ok",
        "summary": counts,
        "items": rows[:limit],
        "all_count": len(rows),
    }
