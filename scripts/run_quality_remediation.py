from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATUS_DIR = ROOT / "tl_ma_radar" / "data" / "quality_remediation"


def _write(payload: dict[str, Any]) -> None:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    (STATUS_DIR / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run(payload: dict[str, Any], name: str, args: list[str], timeout: int | None = None) -> None:
    started = datetime.now(timezone.utc)
    command = [sys.executable, *args]
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=timeout,
    )
    step = {
        "name": name,
        "command": command,
        "returncode": result.returncode,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "stdout_tail": result.stdout[-3000:],
        "stderr_tail": result.stderr[-3000:],
    }
    payload["steps"].append(step)
    _write(payload)
    if result.returncode != 0:
        raise RuntimeError(f"{name} failed with return code {result.returncode}")


def run(limit: int, max_reports: int, include_pdfs: bool) -> Path:
    run_id = datetime.now(timezone.utc).strftime("quality-%Y%m%dT%H%M%SZ")
    payload: dict[str, Any] = {
        "status": "running",
        "run_id": run_id,
        "limit": limit,
        "max_reports": max_reports,
        "include_pdfs": include_pdfs,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "steps": [],
    }
    _write(payload)
    try:
        download_args = [
            "scripts/download_missing_reports.py",
            "--limit",
            str(limit),
            "--max-reports",
            str(max_reports),
        ]
        if include_pdfs:
            download_args.append("--download-pdf")
        _run(payload, "download_missing_reports", download_args, timeout=7200)
        analyze_args = ["scripts/analyze_reports.py", "--max-reports", str(max_reports), "--save-text"]
        if include_pdfs:
            analyze_args.append("--include-pdfs")
        _run(payload, "analyze_reports", analyze_args, timeout=3600)
        _run(payload, "analyze_event_digest", ["scripts/analyze_event_digest.py"], timeout=900)
        _run(payload, "analyze_deal_signals", ["scripts/analyze_deal_signals.py"], timeout=900)
        _run(payload, "seed_top30_workflow", ["scripts/seed_top30_workflow.py", "--limit", "30"], timeout=900)
        _run(payload, "generate_deal_memos", ["scripts/generate_deal_memos.py", "--limit", "30"], timeout=900)
        _run(payload, "analyze_monitoring", ["scripts/analyze_monitoring.py", "--run-id", run_id], timeout=900)
        _run(payload, "export_daily_quality_report", ["scripts/export_daily_quality_report.py"], timeout=900)
        _run(payload, "snapshot", ["scripts/run_pipeline.py", "--snapshot-only"], timeout=900)
        payload["status"] = "ok"
    except Exception as exc:
        payload["status"] = "failed"
        payload["error"] = str(exc)
    payload["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write(payload)
    path = STATUS_DIR / "latest.json"
    print(path)
    if payload["status"] != "ok":
        sys.exit(1)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run data quality remediation for weakest candidates first.")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--max-reports", type=int, default=4)
    parser.add_argument("--no-pdfs", action="store_true")
    args = parser.parse_args()
    run(limit=args.limit, max_reports=args.max_reports, include_pdfs=not args.no_pdfs)


if __name__ == "__main__":
    main()
