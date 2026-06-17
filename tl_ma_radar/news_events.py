from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


EVENT_RULES = [
    ("최대주주/경영권", ["최대주주", "경영권", "인수", "매각", "M&A", "양수도"], "deal"),
    ("유상증자/CB/BW", ["유상증자", "제3자배정", "전환사채", "신주인수권", "CB", "BW", "자금조달"], "financing"),
    ("감사/상장유지", ["감사의견", "의견거절", "한정", "계속기업", "관리종목", "투자주의환기", "상장폐지", "거래정지"], "risk"),
    ("소송/제재", ["소송", "고소", "고발", "배임", "횡령", "제재", "과징금"], "risk"),
    ("공급계약/수주", ["공급계약", "수주", "계약", "납품", "매출 인식"], "opportunity"),
    ("실적/재무", ["실적", "매출", "영업이익", "적자", "흑자", "손실", "자본잠식"], "mixed"),
    ("사업/시너지", ["화학", "소재", "필름", "코팅", "플라스틱", "수지", "2차전지", "환경", "자원순환"], "synergy"),
]


def _parse_date(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _match_event(text: str) -> tuple[str, str, list[str]]:
    hits: list[tuple[str, str, list[str]]] = []
    for label, terms, tone in EVENT_RULES:
        matched = [term for term in terms if term.lower() in text.lower()]
        if matched:
            hits.append((label, tone, matched))
    if not hits:
        return "일반 뉴스", "neutral", []
    hits.sort(key=lambda row: len(row[2]), reverse=True)
    return hits[0]


def _importance(event_type: str, tone: str, matched: list[str], days_ago: int | None) -> float:
    base = {
        "최대주주/경영권": 85,
        "감사/상장유지": 82,
        "유상증자/CB/BW": 76,
        "소송/제재": 72,
        "공급계약/수주": 62,
        "실적/재무": 56,
        "사업/시너지": 48,
        "일반 뉴스": 25,
    }.get(event_type, 30)
    base += min(len(matched) * 4, 14)
    if days_ago is not None:
        if days_ago <= 14:
            base += 10
        elif days_ago <= 45:
            base += 6
        elif days_ago > 150:
            base -= 8
    if tone == "risk":
        base += 6
    return round(max(0, min(100, base)), 1)


def build_news_events(item: dict[str, Any]) -> dict[str, Any]:
    news = item.get("news_analysis") or {}
    articles = news.get("articles") or []
    now = datetime.now(timezone.utc)
    rows = []
    counts: dict[str, int] = {}
    tone_counts: dict[str, int] = {}
    for article in articles:
        if not isinstance(article, dict):
            continue
        text = f"{article.get('title') or ''} {article.get('description') or ''}"
        event_type, tone, matched = _match_event(text)
        published = _parse_date(article.get("published_at"))
        days_ago = (now - published).days if published else None
        row = {
            "date": str(article.get("published_at") or "")[:10],
            "days_ago": days_ago,
            "event_type": event_type,
            "tone": tone,
            "importance": _importance(event_type, tone, matched, days_ago),
            "title": article.get("title") or "-",
            "source": article.get("source") or "-",
            "url": article.get("url") or "",
            "matched_terms": matched,
        }
        rows.append(row)
        counts[event_type] = counts.get(event_type, 0) + 1
        tone_counts[tone] = tone_counts.get(tone, 0) + 1
    rows.sort(key=lambda row: (str(row.get("date") or ""), float(row.get("importance") or 0)), reverse=True)
    top_events = sorted(rows, key=lambda row: float(row.get("importance") or 0), reverse=True)[:8]
    risk_events = [row for row in rows if row.get("tone") == "risk"]
    deal_events = [row for row in rows if row.get("event_type") in {"최대주주/경영권", "유상증자/CB/BW"}]
    return {
        "status": "ok" if rows else "not_enough_news",
        "event_count": len(rows),
        "counts": counts,
        "tone_counts": tone_counts,
        "top_events": top_events,
        "timeline": rows[:30],
        "risk_events": risk_events[:10],
        "deal_events": deal_events[:10],
        "summary": (
            f"뉴스 이벤트 {len(rows)}건 중 리스크 {len(risk_events)}건, 딜 관련 {len(deal_events)}건을 분류했습니다."
            if rows
            else "분류 가능한 최근 뉴스가 부족합니다."
        ),
        "disclosure_match_needed": [
            "뉴스의 최대주주/경영권 이벤트와 DART 최대주주변경 공시 일치 여부 확인",
            "뉴스의 유상증자/CB/BW 이벤트와 DART 주요사항보고서 일치 여부 확인",
            "소송/감사/거래정지성 뉴스는 후속 정정공시와 해소 공시 확인",
        ],
    }
