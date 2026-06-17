from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tl_ma_radar.config import get_settings  # noqa: E402
from tl_ma_radar.deal_signals import analyze_deal_signals  # noqa: E402
from tl_ma_radar.repository import load_candidates  # noqa: E402
from tl_ma_radar.scoring import score_candidate  # noqa: E402


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


def analyze(limit: int | None = None) -> None:
    settings = get_settings(ROOT)
    rows = load_rows()
    merged_by_code = {row["code"]: row for row in load_candidates(ROOT)}
    output: list[dict[str, Any]] = []
    target_count = min(limit or len(rows), len(rows))
    for idx, row in enumerate(rows, start=1):
        updated = dict(row)
        if limit and idx > limit:
            output.append(updated)
            continue
        source = merged_by_code.get(updated["code"], updated)
        scored = score_candidate(source, settings)
        filings = load_filings(updated["code"])
        updated["deal_signals"] = analyze_deal_signals(scored, filings)
        signals = updated["deal_signals"]
        print(
            f"[{idx}/{target_count}] {updated['code']} {updated['name']} "
            f"need={signals['white_knight_need']} window={signals['deal_window']} "
            f"exec={signals['scores']['deal_execution_score']}"
        )
        output.append(updated)
    write_rows(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze DART filing patterns for dealability and white-knight signals.")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    analyze(limit=args.limit)


if __name__ == "__main__":
    main()
