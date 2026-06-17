from __future__ import annotations

import json
from datetime import date
from urllib.parse import urlencode
from urllib.request import Request, urlopen


KRX_URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"


def fetch_kosdaq_quotes(trade_date: date, timeout: int = 20) -> list[dict]:
    """Fetch KOSDAQ all-stock quotes from KRX Data Marketplace.

    KRX occasionally changes bld codes and request requirements. Keep this adapter
    isolated so the rest of the app remains stable when the upstream endpoint moves.
    """
    params = {
        "bld": "dbms/MDC/STAT/standard/MDCSTAT01501",
        "mktId": "KSQ",
        "trdDd": trade_date.strftime("%Y%m%d"),
        "share": "1",
        "money": "1",
        "csvxls_isNo": "false",
    }
    req = Request(
        KRX_URL,
        data=urlencode(params).encode("utf-8"),
        headers={
            "User-Agent": "Mozilla/5.0 TL-MA-Radar/0.1",
            "Referer": "https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        },
        method="POST",
    )
    with urlopen(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("OutBlock_1", [])

