from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tl_ma_radar.acquisition_judgment import build_acquisition_judgment
from tl_ma_radar.config import get_settings
from tl_ma_radar.deal_signals import analyze_deal_signals
from tl_ma_radar.event_digest import build_event_digest
from tl_ma_radar.monitoring import create_monitoring_report
from tl_ma_radar.news_analysis import load_news_cache, news_for_code
from tl_ma_radar.repository import load_candidates
from tl_ma_radar.scoring import score_candidate


def load_filings(code: str) -> list[dict[str, Any]]:
    path = ROOT / "tl_ma_radar" / "data" / "dart_filings" / f"{code}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_candidate(item: dict[str, Any], settings: Any, news_cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
    prepared = dict(item)
    prepared["news_analysis"] = news_for_code(news_cache, str(prepared.get("code", "")))
    filings = load_filings(str(prepared.get("code", "")))
    prepared["deal_signals"] = analyze_deal_signals(prepared, filings)
    prepared["event_digest"] = build_event_digest(filings)
    scored = score_candidate(prepared, settings)
    scored["acquisition_judgment"] = build_acquisition_judgment(scored)
    return scored


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a monitoring snapshot and change report.")
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    settings = get_settings(ROOT)
    news_cache = load_news_cache(ROOT)
    prepared = [prepare_candidate(item, settings, news_cache) for item in load_candidates(ROOT)]
    report = create_monitoring_report(ROOT, prepared, args.run_id)
    counts = report.get("counts") or {}
    print(
        "monitoring "
        f"run={report.get('run_id')} "
        f"baseline={report.get('baseline')} "
        f"alerts={len(report.get('alerts') or [])} "
        f"immediate={counts.get('즉시 검토', 0)} "
        f"deep={counts.get('심층 실사', 0)} "
        f"high_risk={counts.get('고위험 옵션', 0)} "
        f"watch={counts.get('모니터링', 0)}"
    )


if __name__ == "__main__":
    main()
