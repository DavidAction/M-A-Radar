from __future__ import annotations

from typing import Any

from tl_ma_radar.deal_report import Docx


def _fmt(value: object) -> str:
    return str(value if value is not None else "-")


def _score(value: object) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "-"


def _join(values: list[Any] | None, limit: int = 4) -> str:
    clean = [str(value) for value in values or [] if value]
    return " / ".join(clean[:limit]) if clean else "-"


def build_ic_one_pager_docx(item: dict[str, Any]) -> bytes:
    ic = item.get("ic_package") or {}
    scenario = item.get("deal_scenario") or {}
    display = scenario.get("display") or {}
    report = item.get("report_intelligence") or {}
    ai = item.get("ai_brief") or {}
    quality = item.get("data_quality") or {}
    news_events = item.get("news_events") or {}
    findings = report.get("findings") or []
    top_finding = findings[0] if findings else {}

    doc = Docx()
    doc.paragraph(
        f"{item.get('name', '-')} ({item.get('code', '-')}) IC One-Pager",
        style="Title",
        color="13232E",
        bold=True,
        size=34,
        after=90,
    )
    doc.paragraph(
        _fmt(ic.get("summary") or item.get("deal_thesis") or ""),
        style="BodyLead",
        color="374151",
        size=19,
        after=110,
    )
    doc.table(
        [
            ["항목", "내용", "항목", "내용"],
            ["IC 판단", ic.get("decision"), "IC 준비도", _score(ic.get("readiness_score"))],
            ["데이터 신뢰도", f"{quality.get('grade', '-')} / {_score(quality.get('score'))}", "DART 리스크", report.get("severity") or "-"],
            ["신규 지분", display.get("new_share") or "-", "보수 지분", display.get("conservative_new_share") or "-"],
            ["경영권 가능성", display.get("control_feasibility") or "-", "뉴스 이벤트", f"{news_events.get('event_count', 0)}건"],
        ],
        widths=[1700, 2980, 1700, 2980],
        compact=True,
    )
    doc.paragraph("Investment Case", style="Heading1", color="0F766E", bold=True, size=25, before=140, after=60)
    for point in (ic.get("investment_case") or [])[:4]:
        doc.bullet(point)
    doc.paragraph("Key Risk / Mitigation", style="Heading1", color="B42318", bold=True, size=25, before=120, after=60)
    doc.bullet(top_finding.get("title") or "원문 보고서 리스크 확인 필요")
    if top_finding.get("next_step"):
        doc.bullet(top_finding.get("next_step"))
    for row in (ic.get("risk_mitigants") or [])[:2]:
        if isinstance(row, dict):
            doc.bullet(f"{row.get('risk', '-')}: {row.get('mitigant', '-')}")
    doc.paragraph("Deal Structure / Legal Checks", style="Heading1", color="13232E", bold=True, size=25, before=120, after=60)
    for point in (scenario.get("legal_accounting_checkpoints") or [])[:4]:
        doc.bullet(point)
    doc.paragraph("Next 10 Days", style="Heading1", color="13232E", bold=True, size=25, before=120, after=60)
    tasks = []
    for row in (ic.get("diligence_workplan") or [])[:4]:
        if isinstance(row, dict):
            tasks.append(f"{row.get('target', '-')}: {row.get('task', '-')}")
    for task in tasks:
        doc.bullet(task)
    doc.paragraph("AI Memo Draft", style="Heading1", color="13232E", bold=True, size=25, before=120, after=60)
    for point in (ai.get("executive_memo") or [])[:3]:
        doc.bullet(point)
    return doc.build()
