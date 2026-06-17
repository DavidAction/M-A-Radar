from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tl_ma_radar.config import get_settings  # noqa: E402
from tl_ma_radar.news_analysis import analyze_news, fetch_company_news, load_news_cache, save_news_cache  # noqa: E402
from tl_ma_radar.repository import load_candidates  # noqa: E402
from tl_ma_radar.scoring import score_candidate  # noqa: E402


def _ranked_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    settings = get_settings(ROOT)
    scored = []
    for row in rows:
        try:
            item = score_candidate(row, settings)
            scored.append((float((item.get("scores") or {}).get("total") or 0), row))
        except Exception:
            scored.append((0.0, row))
    return [row for _, row in sorted(scored, key=lambda pair: pair[0], reverse=True)]


def _select_candidates(args: argparse.Namespace) -> list[dict[str, Any]]:
    rows = load_candidates(ROOT)
    if args.code:
        code_set = {code.strip() for code in args.code if code.strip()}
        rows = [row for row in rows if str(row.get("code")) in code_set]
    if args.order == "score":
        rows = _ranked_candidates(rows)
    if args.limit:
        rows = rows[: args.limit]
    return rows


def _empty_error(company: dict[str, Any], exc: Exception) -> dict[str, Any]:
    return {
        "status": "error",
        "source": "Naver News API + Google News RSS",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "article_count": 0,
        "displayed_article_count": 0,
        "summary": f"{company.get('name') or company.get('code')} 뉴스 수집 실패: {exc}",
        "tone": "수집 실패",
        "scores": {"momentum": 0, "risk": 0, "deal": 0, "synergy": 0, "attention": 0},
        "key_points": ["네트워크, 검색원 응답, 회사명 중복 여부를 확인해야 합니다."],
        "articles": [],
        "error": str(exc),
    }


def collect(args: argparse.Namespace) -> Path:
    settings = get_settings(ROOT)
    candidates = _select_candidates(args)
    cache = {} if args.replace else load_news_cache(ROOT)
    started_at = datetime.now(timezone.utc).isoformat()
    ok_count = 0
    error_count = 0
    for index, company in enumerate(candidates, start=1):
        code = str(company.get("code") or "")
        name = str(company.get("name") or "")
        if not code or not name:
            continue
        print(f"[{index}/{len(candidates)}] {code} {name}")
        try:
            articles = fetch_company_news(
                name,
                code,
                months=args.months,
                timeout=args.timeout,
                naver_client_id=settings.naver_client_id,
                naver_client_secret=settings.naver_client_secret,
                naver_display=args.naver_display,
            )
            cache[code] = analyze_news(
                company,
                articles,
                months=args.months,
                max_articles=args.max_articles,
            )
            ok_count += 1
            print(f"  ok articles={cache[code].get('article_count')} tone={cache[code].get('tone')}")
        except Exception as exc:  # Keep the rest of the watchlist moving.
            cache[code] = _empty_error(company, exc)
            error_count += 1
            print(f"  error {exc}", file=sys.stderr)
        if args.sleep and index < len(candidates):
            time.sleep(args.sleep)

    metadata = {
        "source": "Naver News API primary, Google News RSS fallback",
        "naver_configured": bool(settings.naver_client_id and settings.naver_client_secret),
        "started_at": started_at,
        "months": args.months,
        "max_articles": args.max_articles,
        "requested_candidates": len(candidates),
        "ok_count": ok_count,
        "error_count": error_count,
        "order": args.order,
        "limit": args.limit,
    }
    path = save_news_cache(ROOT, cache, metadata)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    print(path)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect and analyze latest company news.")
    parser.add_argument("--months", type=int, default=6, help="News search window in months.")
    parser.add_argument("--limit", type=int, default=None, help="Optional max company count.")
    parser.add_argument("--code", action="append", default=[], help="Collect only selected stock code. Repeatable.")
    parser.add_argument("--order", choices=["score", "file"], default="score")
    parser.add_argument("--max-articles", type=int, default=30)
    parser.add_argument("--naver-display", type=int, default=30)
    parser.add_argument("--timeout", type=int, default=18)
    parser.add_argument("--sleep", type=float, default=0.25)
    parser.add_argument("--replace", action="store_true", help="Replace the entire news cache instead of merging.")
    args = parser.parse_args()
    collect(args)


if __name__ == "__main__":
    main()
