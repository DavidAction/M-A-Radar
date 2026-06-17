from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_DIR = Path("tl_ma_radar") / "data"


def _parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if len(text) == 8 and text.isdigit():
            return datetime.strptime(text, "%Y%m%d").replace(tzinfo=timezone.utc)
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _file_mtime(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def _age_days(value: object) -> int | None:
    parsed = _parse_dt(value)
    if not parsed:
        return None
    return max(0, (datetime.now(timezone.utc) - parsed).days)


def _latest_filing_date(filings: list[dict[str, Any]], item: dict[str, Any]) -> str | None:
    dates = [str(row.get("rcept_dt") or "") for row in filings if row.get("rcept_dt")]
    dart = item.get("dart_enrichment") or {}
    if isinstance(dart, dict):
        latest = dart.get("latest_filing") or {}
        if isinstance(latest, dict) and latest.get("rcept_dt"):
            dates.append(str(latest.get("rcept_dt")))
    parsed = sorted((date for date in dates if _parse_dt(date)), reverse=True)
    return parsed[0] if parsed else None


def _news_latest_date(news: dict[str, Any]) -> str | None:
    dates = []
    if news.get("collected_at"):
        dates.append(str(news.get("collected_at")))
    for article in news.get("articles") or []:
        if isinstance(article, dict) and article.get("published_at"):
            dates.append(str(article.get("published_at")))
    parsed = sorted((date for date in dates if _parse_dt(date)), reverse=True)
    return parsed[0] if parsed else None


def _check(label: str, status: str, value: object, detail: str) -> dict[str, str]:
    return {
        "label": label,
        "status": status,
        "value": str(value if value is not None else "-"),
        "detail": detail,
    }


def _grade(score: float) -> str:
    if score >= 85:
        return "투자심의 사용 가능"
    if score >= 70:
        return "검토 사용 가능"
    if score >= 55:
        return "보완 필요"
    return "데이터 부족"


def build_data_quality(
    root: Path,
    item: dict[str, Any],
    filings: list[dict[str, Any]],
    news: dict[str, Any],
) -> dict[str, Any]:
    code = str(item.get("code") or "")
    score = 100.0
    warnings: list[str] = []
    checks: list[dict[str, str]] = []

    filing_count = len(filings)
    latest_filing = _latest_filing_date(filings, item)
    filing_age = _age_days(latest_filing)
    if filing_count <= 0:
        score -= 24
        warnings.append("DART 공시 원천 데이터가 없어 공시 기반 검증력이 낮습니다.")
        checks.append(_check("DART 공시", "risk", 0, "공시 목록 수집 필요"))
    elif filing_age is not None and filing_age > 240:
        score -= 16
        warnings.append("최신 공시가 오래되어 현재 상태와 차이가 있을 수 있습니다.")
        checks.append(_check("DART 공시", "warn", f"{filing_count}건", f"최신 {filing_age}일 전"))
    elif filing_age is not None and filing_age > 120:
        score -= 8
        checks.append(_check("DART 공시", "warn", f"{filing_count}건", f"최신 {filing_age}일 전"))
    else:
        checks.append(_check("DART 공시", "ok", f"{filing_count}건", "최신 공시 반영"))

    article_count = int(news.get("article_count") or 0) if isinstance(news, dict) else 0
    latest_news = _news_latest_date(news if isinstance(news, dict) else {})
    news_age = _age_days(latest_news)
    if article_count <= 0:
        score -= 18
        warnings.append("최근 6개월 뉴스가 부족해 시장 이벤트 해석이 제한됩니다.")
        checks.append(_check("뉴스", "warn", 0, "네이버/구글 뉴스 재수집 권장"))
    elif news_age is not None and news_age > 90:
        score -= 14
        warnings.append("뉴스 데이터가 오래되어 최신 모멘텀 판단을 보완해야 합니다.")
        checks.append(_check("뉴스", "warn", f"{article_count}건", f"최신 {news_age}일 전"))
    elif article_count < 3:
        score -= 7
        checks.append(_check("뉴스", "warn", f"{article_count}건", "표본 부족"))
    else:
        checks.append(_check("뉴스", "ok", f"{article_count}건", "최근 기사 반영"))

    scores = item.get("scores") or {}
    report_evidence = float(scores.get("report_evidence") or 0) if isinstance(scores, dict) else 0.0
    if report_evidence < 35:
        score -= 14
        warnings.append("보고서 근거 점수가 낮아 원문 보고서 확인이 필요합니다.")
        checks.append(_check("보고서 근거", "risk", f"{report_evidence:.1f}", "감사/사업보고서 신호 부족"))
    elif report_evidence < 60:
        score -= 6
        checks.append(_check("보고서 근거", "warn", f"{report_evidence:.1f}", "추가 원문 검토 권장"))
    else:
        checks.append(_check("보고서 근거", "ok", f"{report_evidence:.1f}", "보고서 신호 반영"))

    keywords = item.get("business_keywords") or []
    if len(keywords) < 2:
        score -= 8
        warnings.append("사업 키워드가 부족해 TL/르네스 시너지 판정이 흔들릴 수 있습니다.")
        checks.append(_check("사업 키워드", "warn", len(keywords), "사업보고서 기반 키워드 보강 필요"))
    else:
        checks.append(_check("사업 키워드", "ok", len(keywords), "시너지 분류에 사용 가능"))

    workflow = item.get("workflow") or {}
    if isinstance(workflow, dict) and workflow.get("status") not in {"", "미검토", None}:
        checks.append(_check("딜 파이프라인", "ok", workflow.get("status"), "사용자 검토 상태 반영"))
    else:
        checks.append(_check("딜 파이프라인", "warn", "미검토", "담당자/다음 액션 지정 권장"))

    score = max(0.0, min(100.0, round(score, 1)))
    return {
        "score": score,
        "grade": _grade(score),
        "as_of": datetime.now(timezone.utc).isoformat(),
        "latest_candidate_update": _file_mtime(root / DATA_DIR / "real_candidates.json"),
        "latest_news_update": _file_mtime(root / DATA_DIR / "candidate_news.json"),
        "latest_dart_update": latest_filing,
        "latest_news_article": latest_news,
        "filing_count": filing_count,
        "news_count": article_count,
        "report_evidence": report_evidence,
        "warnings": warnings[:5],
        "checks": checks,
    }


def build_data_quality_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    qualities = [item.get("data_quality") for item in items if isinstance(item.get("data_quality"), dict)]
    if not qualities:
        return {"status": "not_ready", "summary": "데이터 신뢰도 지표가 아직 생성되지 않았습니다."}
    avg = round(sum(float(row.get("score") or 0) for row in qualities) / len(qualities), 1)
    grade_counts: dict[str, int] = {}
    warning_counts: dict[str, int] = {}
    for row in qualities:
        grade = str(row.get("grade") or "미분류")
        grade_counts[grade] = grade_counts.get(grade, 0) + 1
        for warning in row.get("warnings") or []:
            warning_counts[str(warning)] = warning_counts.get(str(warning), 0) + 1
    weak = sorted(
        (
            {
                "code": item.get("code"),
                "name": item.get("name"),
                "score": (item.get("data_quality") or {}).get("score"),
                "grade": (item.get("data_quality") or {}).get("grade"),
                "warnings": (item.get("data_quality") or {}).get("warnings") or [],
            }
            for item in items
            if isinstance(item.get("data_quality"), dict)
        ),
        key=lambda row: float(row.get("score") or 0),
    )[:8]
    return {
        "status": "ok",
        "average_score": avg,
        "grade_counts": grade_counts,
        "top_warnings": sorted(warning_counts.items(), key=lambda row: (-row[1], row[0]))[:6],
        "weakest": weak,
    }
