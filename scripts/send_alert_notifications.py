from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app  # noqa: E402
from tl_ma_radar.alerts import build_alerts  # noqa: E402
from tl_ma_radar.config import get_settings  # noqa: E402
from tl_ma_radar.monitoring import latest_monitoring  # noqa: E402
from tl_ma_radar.notifier import send_alert_notifications  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Send TL M&A Radar alert notifications.")
    parser.add_argument("--dry-run", action="store_true", help="Build and persist a preview without sending.")
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()

    settings = get_settings(ROOT)
    candidates = app.prepared_candidates(settings)
    payload = build_alerts(candidates, latest_monitoring(ROOT), limit=args.limit)
    result = send_alert_notifications(ROOT, payload, settings, dry_run=args.dry_run, limit=args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
