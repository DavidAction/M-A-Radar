from __future__ import annotations

from typing import Any


BENCHMARK_CODES = {
    "121850": "코이즈",
    "247660": "나노씨엠에스",
    "368600": "아이씨에이치",
    "177350": "베셀",
}


def _score(item: dict[str, Any], key: str) -> float:
    return float((item.get("scores") or {}).get(key) or 0)


def _judgment_score(item: dict[str, Any], key: str) -> float:
    return float(((item.get("acquisition_judgment") or {}).get("scores") or {}).get(key) or 0)


def _news_score(item: dict[str, Any], key: str) -> float:
    return float(((item.get("news_analysis") or {}).get("scores") or {}).get(key) or 0)


def _quality_score(item: dict[str, Any]) -> float:
    return float((item.get("data_quality") or {}).get("score") or 0)


def _drivers(item: dict[str, Any]) -> list[str]:
    rows = [
        ("전략 적합도", _score(item, "strategic_fit")),
        ("보고서 근거", _score(item, "report_evidence")),
        ("본업 안정성", _score(item, "core_business")),
        ("거래 가능성", _score(item, "opportunity")),
        ("뉴스 모멘텀", _news_score(item, "momentum")),
    ]
    rows.sort(key=lambda row: row[1], reverse=True)
    return [f"{label} {value:.1f}" for label, value in rows[:3] if value > 0]


def _risks(item: dict[str, Any]) -> list[str]:
    rows = []
    risk_level = _judgment_score(item, "risk_level")
    news_risk = _news_score(item, "risk")
    quality = _quality_score(item)
    if risk_level >= 75:
        rows.append(f"인수 리스크 {risk_level:.1f}")
    if news_risk >= 55:
        rows.append(f"뉴스 리스크 {news_risk:.1f}")
    if quality and quality < 70:
        rows.append(f"데이터 신뢰도 {quality:.1f}")
    flags = item.get("status_flags") or []
    rows.extend(str(flag) for flag in flags[:2])
    return rows[:4]


def _verdict(item: dict[str, Any], rank: int) -> str:
    total = _score(item, "total")
    fit = _score(item, "strategic_fit")
    risk = _judgment_score(item, "risk_level")
    quality = _quality_score(item)
    news_risk = _news_score(item, "risk")
    if risk >= 82 and total >= 62:
        return "과대평가 점검"
    if news_risk >= 65 and total >= 60:
        return "뉴스 리스크 확인"
    if quality and quality < 60:
        return "데이터 보강 후 판단"
    if fit >= 80 and total < 60:
        return "시너지 과소반영 점검"
    if rank <= 10 and fit >= 70:
        return "상위 유지"
    return "관찰"


def _tuning_notes(item: dict[str, Any], rank: int) -> list[str]:
    notes = []
    total = _score(item, "total")
    fit = _score(item, "strategic_fit")
    risk = _judgment_score(item, "risk_level")
    quality = _quality_score(item)
    report = _score(item, "report_evidence")
    if risk >= 82 and total >= 62:
        notes.append("위험도가 높은데 상위권에 있어 리스크 감점 가중치 재확인이 필요합니다.")
    if fit >= 80 and report >= 60 and total < 60:
        notes.append("TL/르네스 접점이 강한데 총점이 낮아 시너지 가중치가 과소반영됐는지 봅니다.")
    if quality and quality < 70:
        notes.append("데이터 신뢰도 보강 전에는 투자심의용 점수로 확정하지 않습니다.")
    if rank <= 20 and report < 35:
        notes.append("상위권 후보이나 보고서 근거가 약해 감사/사업보고서 원문 확인이 우선입니다.")
    if not notes:
        notes.append("현재 산식 기준으로 순위와 주요 근거가 대체로 일관됩니다.")
    return notes[:3]


def build_score_tuning(items: list[dict[str, Any]], limit: int = 20) -> dict[str, Any]:
    ranked = sorted(items, key=lambda item: _score(item, "total"), reverse=True)
    rank_by_code = {str(item.get("code")): index for index, item in enumerate(ranked, start=1)}
    top = ranked[:limit]
    rows = []
    for rank, item in enumerate(top, start=1):
        rows.append(
            {
                "rank": rank,
                "code": item.get("code"),
                "name": item.get("name"),
                "score": _score(item, "total"),
                "shortlist_score": item.get("shortlist_score"),
                "strategic_fit": _score(item, "strategic_fit"),
                "report_evidence": _score(item, "report_evidence"),
                "risk_level": _judgment_score(item, "risk_level"),
                "news_risk": _news_score(item, "risk"),
                "data_quality": _quality_score(item),
                "verdict": _verdict(item, rank),
                "drivers": _drivers(item),
                "risks": _risks(item),
                "notes": _tuning_notes(item, rank),
            }
        )

    benchmarks = []
    for code, expected_name in BENCHMARK_CODES.items():
        found = next((item for item in ranked if str(item.get("code")) == code), None)
        if found:
            rank = rank_by_code.get(code)
            benchmarks.append(
                {
                    "code": code,
                    "name": found.get("name") or expected_name,
                    "rank": rank,
                    "score": _score(found, "total"),
                    "verdict": _verdict(found, int(rank or 999)),
                    "drivers": _drivers(found),
                    "risks": _risks(found),
                }
            )
        else:
            benchmarks.append(
                {
                    "code": code,
                    "name": expected_name,
                    "rank": None,
                    "score": None,
                    "verdict": "데이터 없음",
                    "drivers": [],
                    "risks": ["후보 universe에 없음"],
                }
            )

    over_risk = sum(1 for row in rows if row["verdict"] in {"과대평가 점검", "뉴스 리스크 확인"})
    under_synergy = sum(1 for item in ranked if _score(item, "strategic_fit") >= 80 and _score(item, "total") < 60)
    low_quality_top = sum(1 for row in rows if float(row.get("data_quality") or 0) < 70)
    return {
        "status": "ok",
        "limit": limit,
        "summary": {
            "top_count": len(rows),
            "over_risk_count": over_risk,
            "under_synergy_count": under_synergy,
            "low_quality_top_count": low_quality_top,
            "benchmark_count": len(benchmarks),
        },
        "recommendations": [
            "상위 20개 중 리스크 과대 후보는 리스크 감점과 뉴스 리스크 가중치를 먼저 검수합니다.",
            "코이즈·나노씨엠에스·아이씨에이치·베셀은 벤치마크로 고정해 산식 변경 전후 순위를 추적합니다.",
            "데이터 신뢰도 70점 미만 후보는 투자심의 전에 보고서 원문과 최신 공시를 보강합니다.",
        ],
        "benchmarks": benchmarks,
        "items": rows,
    }
