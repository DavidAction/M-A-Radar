from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from io import StringIO
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
    quality_items = [item for item in items if isinstance(item.get("data_quality"), dict)]
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

    def quality_score(item: dict[str, Any]) -> float:
        return float((item.get("data_quality") or {}).get("score") or 0)

    def issue_row(item: dict[str, Any]) -> dict[str, Any]:
        quality = item.get("data_quality") or {}
        report = item.get("report_analysis") or {}
        dart = item.get("dart_enrichment") or {}
        latest = dart.get("latest_filing") if isinstance(dart, dict) else {}
        if not isinstance(latest, dict):
            latest = {}
        return {
            "code": item.get("code"),
            "name": item.get("name"),
            "score": quality.get("score"),
            "grade": quality.get("grade"),
            "warnings": quality.get("warnings") or [],
            "latest_filing": latest.get("rcept_dt"),
            "latest_report": latest.get("report_nm"),
            "report_text_chars": int(report.get("text_chars") or 0) if isinstance(report, dict) else 0,
            "news_count": quality.get("news_count"),
            "keyword_count": len(item.get("business_keywords") or []),
        }

    def issue_bucket(key: str, label: str, rows: list[dict[str, Any]], why: str) -> dict[str, Any]:
        ranked = sorted(rows, key=lambda item: (quality_score(item), str(item.get("name") or "")))
        return {
            "key": key,
            "label": label,
            "count": len(rows),
            "why": why,
            "items": [issue_row(item) for item in ranked[:8]],
        }

    missing_report_text = [
        item for item in quality_items if int(((item.get("report_analysis") or {}).get("text_chars") or 0)) <= 0
    ]
    keyword_gap = [item for item in quality_items if len(item.get("business_keywords") or []) < 2]
    shareholder_gap = [
        item
        for item in quality_items
        if not (item.get("report_analysis") or {}).get("largest_shareholder")
        and item.get("largest_shareholder_ratio") is None
    ]
    workflow_gap = [
        item
        for item in quality_items
        if ((item.get("workflow") or {}).get("status") in {"", "미검토", None})
    ]
    news_gap = [item for item in quality_items if int(((item.get("data_quality") or {}).get("news_count") or 0)) < 3]
    report_ready = len(quality_items) - len(missing_report_text)
    keyword_ready = len(quality_items) - len(keyword_gap)
    shareholder_ready = len(quality_items) - len(shareholder_gap)
    workflow_ready = len(quality_items) - len(workflow_gap)

    issue_buckets = [
        issue_bucket(
            "missing_report_text",
            "보고서 원문 분석 대기",
            missing_report_text,
            "공시 목록은 있으나 사업보고서/감사보고서 본문 근거가 아직 없어 신호 신뢰도가 낮습니다.",
        ),
        issue_bucket(
            "keyword_gap",
            "사업 키워드 보강",
            keyword_gap,
            "TL/르네스 시너지 판정의 설명력이 약해질 수 있습니다.",
        ),
        issue_bucket(
            "shareholder_gap",
            "최대주주/지분 보강",
            shareholder_gap,
            "경영권 협상 가능성과 백기사 필요도 판단의 핵심 입력입니다.",
        ),
        issue_bucket(
            "workflow_gap",
            "담당자/액션 미지정",
            workflow_gap,
            "레이더를 실제 딜 파이프라인으로 쓰려면 상태, 담당자, 다음 액션이 필요합니다.",
        ),
        issue_bucket(
            "news_gap",
            "뉴스 저노출 재확인",
            news_gap,
            "뉴스가 적은 후보는 검색어/상호 변경/비상장 관계사 이슈를 보강 확인해야 합니다.",
        ),
    ]

    coverage = {
        "total": len(quality_items),
        "investment_ready": grade_counts.get("투자심의 사용 가능", 0),
        "review_ready": grade_counts.get("검토 사용 가능", 0),
        "needs_work": grade_counts.get("보완 필요", 0) + grade_counts.get("데이터 부족", 0),
        "report_text_ready": report_ready,
        "report_text_missing": len(missing_report_text),
        "keyword_ready": keyword_ready,
        "keyword_gap": len(keyword_gap),
        "shareholder_ready": shareholder_ready,
        "shareholder_gap": len(shareholder_gap),
        "workflow_ready": workflow_ready,
        "workflow_gap": len(workflow_gap),
        "news_gap": len(news_gap),
    }

    remediation_plan = [
        {
            "priority": 1,
            "title": "128개 후보 보고서 본문 분석 확장",
            "impact": "보고서 근거와 사업 키워드 부족 경고를 동시에 줄여 상위 후보 설명력을 올립니다.",
            "action": "periodic_reports의 PDF/ZIP을 일괄 다운로드한 뒤 analyze_reports --include-pdfs --save-text로 재분석",
        },
        {
            "priority": 2,
            "title": "최대주주/특수관계자 구조 추출 강화",
            "impact": "백기사 필요도, 1차 엑시트 구조, 경영권 협상 가능성 판단 정확도를 높입니다.",
            "action": "주식등의대량보유상황보고서와 사업보고서 VII. 주주에 관한 사항을 별도 파서로 분리",
        },
        {
            "priority": 3,
            "title": "후보 상태/담당자 입력률 관리",
            "impact": "레이더를 단순 스크리닝에서 실제 딜 파이프라인 운영 도구로 전환합니다.",
            "action": "상위 30개부터 관심/제외/추적/접촉/실사중과 다음 액션, 기한을 지정",
        },
    ]

    export_rows = [
        {
            **issue_row(item),
            "report_evidence": (item.get("scores") or {}).get("report_evidence"),
            "shortlist_score": item.get("shortlist_score"),
            "priority_score": item.get("priority_score"),
        }
        for item in sorted(quality_items, key=lambda row: (quality_score(row), str(row.get("name") or "")))
    ]
    return {
        "status": "ok",
        "average_score": avg,
        "grade_counts": grade_counts,
        "coverage": coverage,
        "top_warnings": sorted(warning_counts.items(), key=lambda row: (-row[1], row[0]))[:6],
        "weakest": weak,
        "issue_buckets": issue_buckets,
        "remediation_plan": remediation_plan,
        "items": export_rows,
    }


def data_quality_csv(payload: dict[str, Any]) -> bytes:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "code",
            "name",
            "quality_score",
            "grade",
            "report_text_chars",
            "report_evidence",
            "keyword_count",
            "news_count",
            "shortlist_score",
            "priority_score",
            "latest_filing",
            "latest_report",
            "warnings",
        ]
    )
    for row in payload.get("items") or []:
        writer.writerow(
            [
                row.get("code"),
                row.get("name"),
                row.get("score"),
                row.get("grade"),
                row.get("report_text_chars"),
                row.get("report_evidence"),
                row.get("keyword_count"),
                row.get("news_count"),
                row.get("shortlist_score"),
                row.get("priority_score"),
                row.get("latest_filing"),
                row.get("latest_report"),
                " / ".join(row.get("warnings") or []),
            ]
        )
    return ("\ufeff" + output.getvalue()).encode("utf-8")
