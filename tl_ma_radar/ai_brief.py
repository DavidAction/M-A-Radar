from __future__ import annotations

from typing import Any


def _list(values: list[Any] | None, limit: int = 5, empty: str = "-") -> str:
    clean = [str(value) for value in values or [] if value]
    return ", ".join(clean[:limit]) if clean else empty


def build_ai_brief(item: dict[str, Any]) -> dict[str, Any]:
    name = str(item.get("name") or "-")
    ic = item.get("ic_package") or {}
    report = item.get("report_intelligence") or {}
    news = item.get("news_events") or {}
    scenario = item.get("deal_scenario") or {}
    quality = item.get("data_quality") or {}
    findings = report.get("findings") or []
    top_finding = findings[0] if findings else {}
    risk_mitigants = ic.get("risk_mitigants") or []
    deal_structure = scenario.get("display") or {}
    memo = [
        f"{name}은 현재 {ic.get('decision', '검토 후보')}로 분류됩니다.",
        f"IC 준비도는 {ic.get('readiness_score', '-')}점, 데이터 신뢰도는 {quality.get('score', '-')}점입니다.",
        f"300억 유상증자 기준 신규 지분율은 {deal_structure.get('new_share', '-')}이며, 보수적 희석 후 {deal_structure.get('conservative_new_share', '-')}로 봅니다.",
        f"핵심 리스크는 {top_finding.get('title', '원문 보고서 추가 확인 필요')}입니다.",
        f"뉴스 이벤트는 {news.get('summary', '분류 가능한 뉴스가 제한적입니다')}",
    ]
    counterarguments = [
        "관리종목/환기/계속기업 이슈가 있다면 낮은 시가총액이 기회가 아니라 구조적 리스크일 수 있습니다.",
        "300억 유상증자가 가능하더라도 CB/BW 전환 후 완전희석 기준 경영권 확보율이 낮아질 수 있습니다.",
        "관계사 또는 자녀 회사 인수 구조는 공정가치와 이해상충 절차가 약하면 공시·세무·배임 리스크로 전환될 수 있습니다.",
        "뉴스상 공급계약이나 모멘텀이 있어도 매출 인식과 회수 가능성을 확인하지 않으면 본업 안정성을 과대평가할 수 있습니다.",
    ]
    request_items = [
        "최근 3개년 감사보고서와 최신 분기/반기보고서 원문 리스크 문단 검토",
        "최대주주, 특수관계인, 5% 이상 주주, 담보/질권 현황 확인",
        "CB/BW 미상환 잔액, 전환가액, 리픽싱, 콜옵션/풋옵션 캡테이블 반영",
        "관계사/자회사/비관계사 인수 후보의 공정가치 평가 가능성 확인",
        "300억 유상증자 자금사용 목적과 실제 집행 구조의 공시 적합성 검토",
    ]
    if risk_mitigants:
        request_items.extend(str(row.get("mitigant")) for row in risk_mitigants[:2] if isinstance(row, dict))
    return {
        "status": "ok",
        "memo_title": f"{name} 투자 검토 메모 초안",
        "executive_memo": memo,
        "counterarguments": counterarguments,
        "legal_accounting_request": request_items[:8],
        "diligence_questions": ic.get("board_questions") or [],
        "prompt_for_external_ai": (
            f"다음 후보 {name}에 대해 TL홀딩스의 300억 유상증자 기반 경영권 인수 및 관계사/자회사 편입 구조를 "
            f"투자위원회 관점에서 검토하라. 핵심 자료: IC 판단={ic.get('decision')}, "
            f"신규지분={deal_structure.get('new_share')}, 주요 리스크={_list([row.get('title') for row in findings if isinstance(row, dict)], 4)}."
        ),
        "source_map": {
            "ic_package": bool(ic),
            "report_intelligence": bool(report),
            "news_events": bool(news),
            "deal_scenario": bool(scenario),
        },
    }
