from __future__ import annotations

import csv
from io import StringIO
from typing import Any

from tl_ma_radar.deal_report import Docx


def _score(item: dict[str, Any], key: str) -> float:
    return float((item.get("scores") or {}).get(key) or 0)


def _quality(item: dict[str, Any]) -> float:
    return float((item.get("data_quality") or {}).get("score") or 0)


def _risk(item: dict[str, Any]) -> float:
    return float(((item.get("acquisition_judgment") or {}).get("scores") or {}).get("risk_level") or 0)


def _readiness(item: dict[str, Any]) -> float:
    return float((item.get("ic_package") or {}).get("readiness_score") or 0)


def _news_risk(item: dict[str, Any]) -> float:
    return float(((item.get("news_analysis") or {}).get("scores") or {}).get("risk") or 0)


def _verdict(item: dict[str, Any]) -> tuple[str, str]:
    risk = _risk(item)
    quality = _quality(item)
    readiness = _readiness(item)
    strategic = _score(item, "strategic_fit")
    report = _score(item, "report_evidence")
    if quality < 60:
        return "자료 보강", "데이터 신뢰도가 낮아 원문/뉴스 보강 전 순위 확정 금지"
    if readiness >= 72 and risk < 76:
        return "상위 유지", "IC 상정 가능성이 높고 리스크가 허용 범위"
    if risk >= 82 and readiness >= 65:
        return "과대평가 점검", "위험도가 높은데 상위권이라 리스크 감점 재검수 필요"
    if strategic >= 80 and report < 45:
        return "근거 보강", "시너지는 강하나 보고서 근거가 약함"
    if strategic >= 80 and readiness < 62:
        return "과소평가 점검", "시너지 강도 대비 IC 준비도가 낮음"
    if _news_risk(item) >= 65:
        return "뉴스 리스크", "최근 뉴스 리스크가 높아 공시와 대조 필요"
    return "사람 검수", "정량 순위는 가능하나 담당자 판단 필요"


def _drivers(item: dict[str, Any]) -> list[str]:
    rows = [
        ("IC 준비도", _readiness(item)),
        ("전략 적합도", _score(item, "strategic_fit")),
        ("보고서 근거", _score(item, "report_evidence")),
        ("본업 안정성", _score(item, "core_business")),
        ("데이터 신뢰도", _quality(item)),
    ]
    rows.sort(key=lambda row: row[1], reverse=True)
    return [f"{name} {value:.1f}" for name, value in rows[:4]]


def _review_tasks(item: dict[str, Any]) -> list[str]:
    tasks = [
        "최대주주/우호지분 및 담보·질권 확인",
        "300억 유상증자 후 완전희석 지분율 확인",
        "감사의견/계속기업/관리·환기 사유 원문 확인",
    ]
    flags = set(str(flag) for flag in item.get("status_flags") or [])
    if "CB/BW공시" in flags:
        tasks.insert(1, "CB/BW 미상환 잔액과 전환가액 리픽싱 확인")
    if "특수관계거래" in flags:
        tasks.append("관계사/자녀 회사 인수 구조의 공정가치·공시 리스크 확인")
    if _news_risk(item) >= 45:
        tasks.append("뉴스 리스크 이벤트와 DART 공시 일치 여부 확인")
    return tasks[:6]


def build_top_review(items: list[dict[str, Any]], limit: int = 20) -> dict[str, Any]:
    ranked = sorted(
        items,
        key=lambda item: (
            -_readiness(item),
            -(float(item.get("priority_score") or item.get("shortlist_score") or _score(item, "total"))),
            str(item.get("name") or ""),
        ),
    )[:limit]
    rows = []
    for rank, item in enumerate(ranked, start=1):
        verdict, reason = _verdict(item)
        rows.append(
            {
                "rank": rank,
                "code": item.get("code"),
                "name": item.get("name"),
                "ic_decision": (item.get("ic_package") or {}).get("decision"),
                "review_verdict": verdict,
                "reason": reason,
                "readiness_score": _readiness(item),
                "score": _score(item, "total"),
                "strategic_fit": _score(item, "strategic_fit"),
                "risk_score": _risk(item),
                "news_risk": _news_risk(item),
                "data_quality": _quality(item),
                "drivers": _drivers(item),
                "review_tasks": _review_tasks(item),
            }
        )
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row["review_verdict"])
        counts[key] = counts.get(key, 0) + 1
    return {
        "status": "ok",
        "limit": limit,
        "summary": counts,
        "items": rows,
        "review_policy": [
            "상위 유지 후보도 원문 보고서와 완전희석 지분율 확인 전에는 IC 확정 금지",
            "과대평가 점검 후보는 리스크 감점 가중치 조정 여부 검토",
            "과소평가 점검 후보는 TL/르네스 시너지 가중치 조정 여부 검토",
            "자료 보강 후보는 DART 원문/뉴스 재수집 후 재점수화",
        ],
    }


def top_review_csv(payload: dict[str, Any]) -> bytes:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["rank", "code", "name", "ic_decision", "review_verdict", "readiness", "risk", "quality", "reason", "tasks"])
    for row in payload.get("items") or []:
        writer.writerow(
            [
                row.get("rank"),
                row.get("code"),
                row.get("name"),
                row.get("ic_decision"),
                row.get("review_verdict"),
                row.get("readiness_score"),
                row.get("risk_score"),
                row.get("data_quality"),
                row.get("reason"),
                " / ".join(row.get("review_tasks") or []),
            ]
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def top_review_docx(payload: dict[str, Any]) -> bytes:
    doc = Docx()
    doc.paragraph("Top 20 Candidate Review", style="Title", color="13232E", bold=True, size=38, after=120)
    doc.paragraph("IC-ready shortlist validation report for TL Holdings M&A Radar", color="0F766E", size=21, after=180)
    summary = payload.get("summary") or {}
    doc.table(
        [["구분", "건수"]]
        + [[key, value] for key, value in sorted(summary.items(), key=lambda row: (-row[1], row[0]))],
        widths=[4200, 5160],
        compact=True,
    )
    doc.paragraph("Review Policy", style="Heading1", color="13232E", bold=True, size=28, before=180, after=80)
    for point in payload.get("review_policy") or []:
        doc.bullet(point)
    doc.paragraph("Top 20 Review Table", style="Heading1", color="13232E", bold=True, size=28, before=180, after=80)
    doc.table(
        [["Rank", "회사", "판정", "IC준비도", "리스크", "검수 사유"]]
        + [
            [
                row.get("rank"),
                f"{row.get('name')} ({row.get('code')})",
                row.get("review_verdict"),
                row.get("readiness_score"),
                row.get("risk_score"),
                row.get("reason"),
            ]
            for row in payload.get("items") or []
        ],
        widths=[700, 2100, 1500, 1100, 1000, 2960],
        compact=True,
    )
    for row in payload.get("items") or []:
        doc.paragraph(f"#{row.get('rank')} {row.get('name')} ({row.get('code')})", style="Heading2", color="13232E", bold=True, size=24, before=180, after=70)
        doc.table(
            [
                ["항목", "내용"],
                ["IC 판단", row.get("ic_decision")],
                ["검수 판정", row.get("review_verdict")],
                ["상위 이유", " / ".join(row.get("drivers") or [])],
                ["확인 과제", " / ".join(row.get("review_tasks") or [])],
            ],
            widths=[1800, 7560],
            compact=True,
        )
    return doc.build()
