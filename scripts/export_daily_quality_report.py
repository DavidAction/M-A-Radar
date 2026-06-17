from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import prepared_candidates  # noqa: E402
from tl_ma_radar.alerts import alerts_csv, build_alerts  # noqa: E402
from tl_ma_radar.config import get_settings  # noqa: E402
from tl_ma_radar.data_quality import build_data_quality_summary, data_quality_csv  # noqa: E402
from tl_ma_radar.monitoring import latest_monitoring  # noqa: E402


REPORT_DIR = ROOT / "tl_ma_radar" / "data" / "quality_reports"


def export() -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    settings = get_settings(ROOT)
    candidates = prepared_candidates(settings)
    monitoring = latest_monitoring(ROOT)
    quality = build_data_quality_summary(candidates)
    alerts = build_alerts(candidates, monitoring, limit=200)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quality": quality,
        "alerts": alerts,
        "monitoring": {
            "status": monitoring.get("status"),
            "alert_count": len(monitoring.get("alerts") or []),
            "run_id": monitoring.get("run_id"),
        },
    }
    json_path = REPORT_DIR / f"{stamp}.json"
    latest_path = REPORT_DIR / "latest.json"
    quality_csv_path = REPORT_DIR / f"{stamp}_data_quality.csv"
    alerts_csv_path = REPORT_DIR / f"{stamp}_alerts.csv"
    latest_quality_csv = REPORT_DIR / "latest_data_quality.csv"
    latest_alerts_csv = REPORT_DIR / "latest_alerts.csv"
    json_payload = json.dumps(payload, ensure_ascii=False, indent=2)
    json_path.write_text(json_payload, encoding="utf-8")
    latest_path.write_text(json_payload, encoding="utf-8")
    quality_bytes = data_quality_csv(quality)
    alert_bytes = alerts_csv(alerts)
    quality_csv_path.write_bytes(quality_bytes)
    alerts_csv_path.write_bytes(alert_bytes)
    latest_quality_csv.write_bytes(quality_bytes)
    latest_alerts_csv.write_bytes(alert_bytes)
    print(json_path)
    return json_path


if __name__ == "__main__":
    export()
