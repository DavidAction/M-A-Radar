from __future__ import annotations

import re
from datetime import datetime, timezone
from io import StringIO
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


BASE_URL = "https://finance.naver.com/sise/sise_market_sum.naver"


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip().replace(",", "")
    if not text or text.lower() == "nan" or text == "N/A":
        return None
    text = text.replace("%", "")
    try:
        return float(text)
    except ValueError:
        return None


def _fetch_page(page: int, timeout: int = 20) -> str:
    params = urlencode({"sosok": "1", "page": str(page)})
    req = Request(
        f"{BASE_URL}?{params}",
        headers={
            "User-Agent": "Mozilla/5.0 TL-MA-Radar/0.1",
            "Referer": "https://finance.naver.com/sise/",
        },
    )
    with urlopen(req, timeout=timeout) as response:
        return response.read().decode("euc-kr", errors="ignore")


def fetch_kosdaq_market_caps(max_pages: int = 45, timeout: int = 20) -> list[dict[str, Any]]:
    fetched_at = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        html = _fetch_page(page, timeout=timeout)
        links = re.findall(r'/item/main\.naver\?code=(\d+)".*?class="tltle">([^<]+)</a>', html)
        if not links:
            break
        tables = pd.read_html(StringIO(html))
        quote_tables = [table for table in tables if "종목명" in table.columns and "시가총액" in table.columns]
        if not quote_tables:
            continue
        table = quote_tables[0].dropna(subset=["N", "종목명"]).reset_index(drop=True)
        for (_, row), (code, name) in zip(table.iterrows(), links):
            market_cap_eok = _number(row.get("시가총액"))
            if market_cap_eok is None:
                continue
            status_flags = _guess_status_flags(
                market_cap_krw=int(market_cap_eok * 100_000_000),
                per=_number(row.get("PER")),
                volume=int(_number(row.get("거래량")) or 0),
            )
            rows.append(
                {
                    "code": code,
                    "name": str(name).strip(),
                    "market": "KOSDAQ",
                    "sector": "시장 스크리닝",
                    "market_cap_krw": int(market_cap_eok * 100_000_000),
                    "pbr": None,
                    "per": _number(row.get("PER")),
                    "roe": _number(row.get("ROE")),
                    "current_price_krw": int(_number(row.get("현재가")) or 0),
                    "volume": int(_number(row.get("거래량")) or 0),
                    "largest_shareholder_ratio": None,
                    "has_operating_assets": False,
                    "status_flags": status_flags,
                    "business_keywords": _guess_keywords(str(name)),
                    "deal_thesis": "시총 300억 이하 코스닥 후보로 1차 시장 스크리닝에 포착됨. DART 재무·공시 기반 정밀 분석이 필요합니다.",
                    "key_diligence": [
                        "최근 사업보고서 기준 주력 사업과 매출원 확인",
                        "최대주주 지분율 및 최근 지분공시 확인",
                        "관리종목/환기종목/거래정지 여부 확인",
                        "티엘홀딩스·르네스머테리얼 사업 흐름과의 실제 접점 확인",
                    ],
                    "source_note": f"개발용 fallback: 네이버 금융 코스닥 시가총액 표, 수집시각 UTC {fetched_at}",
                }
            )
    return rows


def _guess_keywords(name: str) -> list[str]:
    keyword_map = {
        "화학": "화학",
        "케미": "화학",
        "소재": "소재",
        "머티": "소재",
        "필름": "필름",
        "코팅": "코팅",
        "환경": "자원순환",
        "리사이": "자원순환",
        "바이오": "바이오",
        "물류": "유통",
        "유통": "유통",
        "첨단": "소재",
        "정밀화학": "정밀화학",
    }
    hits = []
    for needle, keyword in keyword_map.items():
        if needle in name and keyword not in hits:
            hits.append(keyword)
    return hits


def _guess_status_flags(market_cap_krw: int, per: float | None, volume: int) -> list[str]:
    flags = []
    if market_cap_krw <= 10_000_000_000:
        flags.append("초저시총")
    if per is not None and per < 0:
        flags.append("적자")
    if volume == 0:
        flags.append("거래정지/거래부진확인필요")
    return flags
