from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tl_ma_radar.config import get_settings  # noqa: E402
from tl_ma_radar.notifier import notification_status  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate alert delivery channel configuration.")
    parser.add_argument("--allow-missing", action="store_true", help="Exit 0 even when no webhook/SMTP is configured.")
    args = parser.parse_args()
    status = notification_status(ROOT, get_settings(ROOT))
    print(json.dumps(status, ensure_ascii=False, indent=2))
    if status.get("ready_for_real_send"):
        return 0
    return 0 if args.allow_missing else 2


if __name__ == "__main__":
    raise SystemExit(main())
