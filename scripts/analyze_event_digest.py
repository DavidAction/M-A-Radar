from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tl_ma_radar.event_digest import build_event_digest  # noqa: E402


DATA_PATH = ROOT / "tl_ma_radar" / "data" / "real_candidates.json"
FILINGS_DIR = ROOT / "tl_ma_radar" / "data" / "dart_filings"


def load_rows() -> list[dict[str, Any]]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def write_rows(rows: list[dict[str, Any]]) -> None:
    DATA_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def load_filings(code: str) -> list[dict[str, Any]]:
    path = FILINGS_DIR / f"{code}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def analyze(limit: int | None, lookback_days: int) -> None:
    rows = load_rows()
    output: list[dict[str, Any]] = []
    target_count = min(limit or len(rows), len(rows))
    for idx, row in enumerate(rows, start=1):
        updated = dict(row)
        if limit and idx > limit:
            output.append(updated)
            continue
        filings = load_filings(updated["code"])
        updated["event_digest"] = build_event_digest(filings, lookback_days=lookback_days)
        print(f"[{idx}/{target_count}] {updated['code']} {updated['name']} {updated['event_digest']['counts']}")
        output.append(updated)
    write_rows(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build recent DART event digests for diligence.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--lookback-days", type=int, default=365)
    args = parser.parse_args()
    analyze(limit=args.limit, lookback_days=args.lookback_days)


if __name__ == "__main__":
    main()
