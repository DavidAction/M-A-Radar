from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tl_ma_radar.collectors.dart import DartClient  # noqa: E402
from tl_ma_radar.collectors.naver_finance import fetch_kosdaq_market_caps  # noqa: E402
from tl_ma_radar.config import get_settings  # noqa: E402


def _load_dart_stock_map(api_key: str) -> dict[str, str]:
    if not api_key:
        return {}
    rows = DartClient(api_key).corp_codes()
    return {row["stock_code"]: row["corp_code"] for row in rows if row.get("stock_code")}


def refresh(limit: int | None = None, use_dart: bool = True) -> Path:
    settings = get_settings(ROOT)
    rows = fetch_kosdaq_market_caps()
    filtered = [
        row
        for row in rows
        if row["market_cap_krw"] <= settings.market_cap_limit_krw
        and not _is_excluded_security(row["name"])
    ]
    filtered.sort(key=lambda row: row["market_cap_krw"])
    if limit:
        filtered = filtered[:limit]

    dart_map = _load_dart_stock_map(settings.dart_api_key) if use_dart else {}
    for row in filtered:
        corp_code = dart_map.get(row["code"])
        if corp_code:
            row["dart_corp_code"] = corp_code
            row["source_note"] += f" / OpenDART corp_code {corp_code} 매핑"

    output_path = ROOT / "tl_ma_radar" / "data" / "real_candidates.json"
    output_path.write_text(
        json.dumps(filtered, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def _is_excluded_security(name: str) -> bool:
    normalized = name.strip().upper()
    if "스팩" in normalized or "SPAC" in normalized:
        return True
    if normalized.endswith("우") or normalized.endswith("우B") or normalized.endswith("우C"):
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh KOSDAQ under-30B candidate data.")
    parser.add_argument("--limit", type=int, default=None, help="Optional max number of rows to save.")
    parser.add_argument("--no-dart", action="store_true", help="Skip OpenDART corp-code mapping.")
    args = parser.parse_args()
    path = refresh(limit=args.limit, use_dart=not args.no_dart)
    print(path)


if __name__ == "__main__":
    main()
