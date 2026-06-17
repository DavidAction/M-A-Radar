from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import ROOT, prepared_candidates
from tl_ma_radar.config import get_settings
from tl_ma_radar.team_ops import build_pipeline_sqlite


def main() -> None:
    parser = argparse.ArgumentParser(description="Export TL M&A Radar pipeline data to SQLite.")
    parser.add_argument(
        "--output",
        default="tl_ma_radar/data/exports/tl_ma_radar_pipeline.sqlite",
        help="Output SQLite path.",
    )
    args = parser.parse_args()

    settings = get_settings(ROOT)
    candidates = prepared_candidates(settings)
    body = build_pipeline_sqlite(candidates)
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(body)
    print(f"Exported {len(candidates)} candidates to {output}")


if __name__ == "__main__":
    main()
