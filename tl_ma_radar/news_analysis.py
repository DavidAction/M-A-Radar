from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

NEWS_CACHE_PATH = Path("tl_ma_radar") / "data" / "candidate_news.json"
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
NAVER_NEWS_API = "https://openapi.naver.com/v1/search/news.json"

RISK_TERMS = {
    "거래정지": 24,
    "상장폐지": 28,
    "관리종목": 18,
    "환기종목": 16,
    "불성실공시": 16,
    "감사의견": 20,
    "의견거절": 28,
    "한정": 18,
    "계속기업": 18,
    "횡령": 30,
    "배임": 30,
    "소송": 14,
    "적자": 10,
    "손실": 10,
    "감자": 18,
    "채무": 12,
}

OPPORTUNITY_TERMS = {
    "공급계약": 20,
    "수주": 18,
    "계약": 10,
    "흑자전환": 18,
    "실적개선": 16,
    "매출": 8,
    "영업이익": 8,
    "신사업": 10,
    "국책과제": 12,
    "특허": 8,
}

DEAL_TERMS = {
    "최대주주": 18,
    "경영권": 22,
    "인수": 22,
    "매각": 22,
    "M&A": 22,
    "유상증자": 16,
    "전환사채": 14,
    "CB": 12,
    "BW": 12,
    "제3자배정": 18,
    "투자유치": 16,
    "자금조달": 14,
}

SYNERGY_TERMS = {
    "화학": 12,
    "석유화학": 18,
    "수지": 14,
    "플라스틱": 14,
    "소재": 10,
    "필름": 12,
    "코팅": 14,
    "2차전지": 12,
    "환경": 10,
    "폐수": 12,
    "자원순환": 14,
    "재생": 10,
}


def load_news_cache(root: Path) -> dict[str, dict[str, Any]]:
    path = root / NEWS_CACHE_PATH
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("items"), dict):
        return payload["items"]
    return payload if isinstance(payload, dict) else {}


def save_news_cache(root: Path, items: dict[str, dict[str, Any]], metadata: dict[str, Any]) -> Path:
    path = root / NEWS_CACHE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metadata": metadata,
        "items": items,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def news_for_code(cache: dict[str, dict[str, Any]], code: str) -> dict[str, Any]:
    item = cache.get(code)
    if isinstance(item, dict):
        return item
    return {
        "status": "not_collected",
        "summary": "최근 6개월 뉴스 수집 전입니다.",
        "article_count": 0,
        "scores": {"momentum": 0, "risk": 0, "deal": 0, "synergy": 0},
        "key_points": [],
        "articles": [],
    }


def build_google_news_url(name: str, code: str, months: int) -> str:
    query = f'"{name}" 코스닥 주식'
    params = f"q={quote_plus(query)}&hl=ko&gl=KR&ceid=KR:ko"
    return f"{GOOGLE_NEWS_RSS}?{params}"


def build_naver_news_url(name: str, code: str, display: int = 30) -> str:
    query = f"{name} 코스닥"
    if len(name) <= 2 or re.fullmatch(r"[A-Za-z0-9&.\s]+", name):
        query = f"{name} {code} 코스닥"
    display = max(1, min(display, 100))
    params = f"query={quote_plus(query)}&display={display}&start=1&sort=date"
    return f"{NAVER_NEWS_API}?{params}"


def fetch_company_news(
    name: str,
    code: str,
    months: int = 6,
    timeout: int = 18,
    naver_client_id: str = "",
    naver_client_secret: str = "",
    naver_display: int = 30,
) -> list[dict[str, Any]]:
    articles: list[dict[str, Any]] = []
    errors: list[Exception] = []
    naver_attempted = bool(naver_client_id and naver_client_secret)
    naver_succeeded = False
    if naver_client_id and naver_client_secret:
        try:
            articles.extend(
                fetch_naver_news(
                    name,
                    code,
                    client_id=naver_client_id,
                    client_secret=naver_client_secret,
                    display=naver_display,
                    timeout=timeout,
                )
            )
            naver_succeeded = True
        except Exception as exc:
            errors.append(exc)
    if len(articles) < 2:
        try:
            articles.extend(fetch_google_news(name, code, months=months, timeout=timeout))
        except Exception as exc:
            errors.append(exc)
    if not articles and errors and not (naver_attempted and naver_succeeded):
        raise errors[-1]
    return _dedupe_articles(articles)


def fetch_naver_news(
    name: str,
    code: str,
    client_id: str,
    client_secret: str,
    display: int = 30,
    timeout: int = 18,
) -> list[dict[str, Any]]:
    url = build_naver_news_url(name, code, display=display)
    req = Request(
        url,
        headers={
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
            "User-Agent": "Mozilla/5.0 TL-MA-Radar/1.0",
            "Accept": "application/json",
        },
    )
    with urlopen(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return parse_naver_news(payload, name=name, code=code)


def fetch_google_news(name: str, code: str, months: int = 6, timeout: int = 18) -> list[dict[str, Any]]:
    url = build_google_news_url(name, code, months)
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 TL-MA-Radar/1.0",
            "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
        },
    )
    with urlopen(req, timeout=timeout) as response:
        raw = response.read()
    return parse_news_rss(raw, name=name, code=code, collector="Google News RSS")


def parse_naver_news(payload: dict[str, Any], name: str, code: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        title = _clean_text(item.get("title"))
        description = _clean_text(item.get("description"))
        link = str(item.get("originallink") or item.get("link") or "").strip()
        naver_link = str(item.get("link") or "").strip()
        published_at = _parse_date(str(item.get("pubDate") or ""))
        if not _is_relevant(title, description, name, code):
            continue
        rows.append(
            {
                "title": title,
                "description": description,
                "url": link or naver_link,
                "source": _host_label(link or naver_link),
                "published_at": published_at.isoformat() if published_at else None,
                "source_url": link,
                "naver_link": naver_link,
                "collector": "Naver News API",
            }
        )
    return _dedupe_articles(rows)


def parse_news_rss(raw: bytes, name: str, code: str, collector: str) -> list[dict[str, Any]]:
    root = ElementTree.fromstring(raw)
    rows: list[dict[str, Any]] = []
    for node in root.findall("./channel/item"):
        title = _clean_text(node.findtext("title"))
        description = _clean_text(node.findtext("description"))
        link = (node.findtext("link") or "").strip()
        source_node = node.find("source")
        source = _clean_text(source_node.text if source_node is not None else "")
        published_at = _parse_date(node.findtext("pubDate"))
        if not _is_relevant(title, description, name, code):
            continue
        rows.append(
            {
                "title": title,
                "description": description,
                "url": link,
                "source": source,
                "published_at": published_at.isoformat() if published_at else None,
                "source_url": source_node.attrib.get("url") if source_node is not None else "",
                "collector": collector,
            }
        )
    return _dedupe_articles(rows)


def parse_google_news_rss(raw: bytes, name: str, code: str) -> list[dict[str, Any]]:
    return parse_news_rss(raw, name=name, code=code, collector="Google News RSS")


def analyze_news(
    company: dict[str, Any],
    articles: list[dict[str, Any]],
    months: int = 6,
    max_articles: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=31 * months)
    filtered = []
    for article in articles:
        published = _datetime_from_iso(article.get("published_at"))
        if published is not None and published < cutoff:
            continue
        filtered.append(article)
    filtered.sort(key=lambda row: row.get("published_at") or "", reverse=True)

    analyzed_articles = []
    aggregate_hits = {"risk": {}, "opportunity": {}, "deal": {}, "synergy": {}}
    for article in filtered[:max_articles]:
        text = f"{article.get('title') or ''} {article.get('description') or ''}"
        tags = {
            "risk": _term_hits(text, RISK_TERMS),
            "opportunity": _term_hits(text, OPPORTUNITY_TERMS),
            "deal": _term_hits(text, DEAL_TERMS),
            "synergy": _term_hits(text, SYNERGY_TERMS),
        }
        for bucket, hits in tags.items():
            for term, count in hits.items():
                aggregate_hits[bucket][term] = aggregate_hits[bucket].get(term, 0) + count
        analyzed = dict(article)
        analyzed["tags"] = {bucket: sorted(hits) for bucket, hits in tags.items() if hits}
        analyzed_articles.append(analyzed)

    scores = {
        "risk": _weighted_score(aggregate_hits["risk"], RISK_TERMS),
        "opportunity": _weighted_score(aggregate_hits["opportunity"], OPPORTUNITY_TERMS),
        "deal": _weighted_score(aggregate_hits["deal"], DEAL_TERMS),
        "synergy": _weighted_score(aggregate_hits["synergy"], SYNERGY_TERMS),
    }
    scores["momentum"] = round(
        _clamp(scores["opportunity"] * 0.36 + scores["deal"] * 0.34 + scores["synergy"] * 0.20 - scores["risk"] * 0.18),
        1,
    )
    scores["attention"] = round(_clamp(scores["risk"] * 0.48 + scores["deal"] * 0.34 + scores["opportunity"] * 0.18), 1)

    tone = _tone(scores)
    key_points = _key_points(company, scores, aggregate_hits, analyzed_articles)
    return {
        "status": "ok",
        "source": _source_label(filtered),
        "query_months": months,
        "collected_at": now.isoformat(),
        "article_count": len(filtered),
        "displayed_article_count": len(analyzed_articles),
        "summary": _summary(company, len(filtered), scores, tone),
        "tone": tone,
        "scores": scores,
        "topics": {key: sorted(value.items(), key=lambda row: (-row[1], row[0]))[:8] for key, value in aggregate_hits.items()},
        "key_points": key_points,
        "articles": analyzed_articles,
    }


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _datetime_from_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_relevant(title: str, description: str, name: str, code: str) -> bool:
    text = f"{title} {description}".lower()
    name_text = name.lower()
    if code and code in text:
        return True
    if len(name_text) >= 3 and name_text in text:
        return True
    return bool(name_text and name_text in text and ("코스닥" in text or "주식" in text or "공시" in text))


def _dedupe_articles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped = []
    for row in rows:
        key = re.sub(r"\s+", " ", (row.get("title") or "").lower())
        if not key:
            key = row.get("url") or ""
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _source_label(rows: list[dict[str, Any]]) -> str:
    collectors = sorted({str(row.get("collector") or "") for row in rows if row.get("collector")})
    return ", ".join(collectors) if collectors else "News RSS"


def _host_label(url: str) -> str:
    if not url:
        return ""
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _term_hits(text: str, weights: dict[str, int]) -> dict[str, int]:
    result = {}
    normalized = text.upper()
    for term in weights:
        count = normalized.count(term.upper())
        if count:
            result[term] = count
    return result


def _weighted_score(hits: dict[str, int], weights: dict[str, int]) -> float:
    score = sum(weights.get(term, 0) * count for term, count in hits.items())
    return round(_clamp(score), 1)


def _tone(scores: dict[str, float]) -> str:
    if scores["risk"] >= 55 and scores["risk"] >= scores["momentum"]:
        return "리스크 우세"
    if scores["deal"] >= 45:
        return "딜 이벤트 감지"
    if scores["momentum"] >= 45:
        return "호재 모멘텀"
    if scores["opportunity"] >= 25 or scores["synergy"] >= 25:
        return "사업 뉴스 확인"
    return "중립/저노출"


def _summary(company: dict[str, Any], count: int, scores: dict[str, float], tone: str) -> str:
    name = company.get("name") or "-"
    if count == 0:
        return f"{name} 관련 최근 6개월 뉴스가 제한적으로 탐지됩니다. 공시와 보고서 중심 검토가 우선입니다."
    return (
        f"{name} 관련 최근 6개월 뉴스 {count}건을 분석했습니다. "
        f"뉴스 톤은 {tone}, 모멘텀 {scores['momentum']}점, 리스크 {scores['risk']}점, "
        f"딜 이벤트 {scores['deal']}점입니다."
    )


def _key_points(
    company: dict[str, Any],
    scores: dict[str, float],
    topics: dict[str, dict[str, int]],
    articles: list[dict[str, Any]],
) -> list[str]:
    points: list[str] = []
    if scores["deal"] >= 35:
        points.append("최대주주, 유상증자, CB/BW, 경영권 등 딜 관련 뉴스 키워드가 포착됩니다.")
    if scores["risk"] >= 35:
        points.append("거래정지, 감사의견, 상장폐지, 감자 등 리스크성 뉴스 키워드 원문 확인이 필요합니다.")
    if scores["opportunity"] >= 30:
        points.append("수주, 공급계약, 실적개선 등 본업 회복 또는 사업성 뉴스가 감지됩니다.")
    if scores["synergy"] >= 25:
        points.append("화학, 소재, 필름, 코팅, 환경/자원순환 등 TL/르네스 시너지 키워드가 뉴스에 포함됩니다.")
    if articles:
        latest = articles[0]
        points.append(f"최신 기사: {latest.get('published_at', '')[:10]} {latest.get('title') or '-'}")
    if not points:
        points.append("뉴스 신호는 약하므로 DART 공시, 감사보고서, 사업보고서 근거가 더 중요합니다.")
    return points[:5]


def _clamp(value: float, lower: float = 0, upper: float = 100) -> float:
    return max(lower, min(upper, value))
