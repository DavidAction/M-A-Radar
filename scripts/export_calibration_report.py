from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import prepared_candidates  # noqa: E402
from tl_ma_radar.calibration import build_calibration_report  # noqa: E402
from tl_ma_radar.config import get_settings  # noqa: E402


REPORT_DIR = ROOT / "tl_ma_radar" / "data" / "quality_reports"


def export(limit: int = 30) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    settings = get_settings(ROOT)
    payload = build_calibration_report(prepared_candidates(settings), limit=limit)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = REPORT_DIR / f"{stamp}_calibration.json"
    latest = REPORT_DIR / "latest_calibration.json"
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(body, encoding="utf-8")
    latest.write_text(body, encoding="utf-8")
    print(path)
    return path


if __name__ == "__main__":
    export()
