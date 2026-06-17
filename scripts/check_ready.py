from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _exists(path: str) -> bool:
    return (ROOT / path).exists()


def _json_count(path: str) -> int:
    target = ROOT / path
    if not target.exists():
        return 0
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return -1
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list):
            return len(items)
        if isinstance(items, dict):
            return len(items)
        return len(payload)
    return 0


def main() -> int:
    checks = [
        ("app.py", _exists("app.py")),
        ("static/index.html", _exists("static/index.html")),
        ("static/app.js", _exists("static/app.js")),
        ("real_candidates.json", _exists("tl_ma_radar/data/real_candidates.json")),
        ("candidate_news.json", _exists("tl_ma_radar/data/candidate_news.json")),
        (".env", _exists(".env")),
    ]
    candidate_count = _json_count("tl_ma_radar/data/real_candidates.json")
    filing_dir = ROOT / "tl_ma_radar" / "data" / "dart_filings"
    filing_count = len(list(filing_dir.glob("*.json"))) if filing_dir.exists() else 0

    print("Readiness check")
    print(f"- Python: {sys.version.split()[0]}")
    for name, ok in checks:
        print(f"- {name}: {'OK' if ok else 'MISSING'}")
    print(f"- candidate count: {candidate_count}")
    print(f"- DART filing JSON count: {filing_count}")

    if not _exists(".env"):
        print("")
        print("Warning: .env is missing. setup_windows.ps1 should create it from .env.example.")
    if candidate_count <= 0:
        print("")
        print("Warning: no candidate data found. Run scripts/run_pipeline.py or restore real_candidates.json.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
