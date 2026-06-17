from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ROOT / "tl_ma_radar" / "data" / "pipeline_runs"


class StepFailed(Exception):
    def __init__(self, step: dict[str, Any]) -> None:
        self.step = step
        super().__init__(f"{step['name']} failed with return code {step['returncode']}")


def emit_text(text: str, *, stream: Any = sys.stdout) -> None:
    if not text:
        return
    try:
        print(text, file=stream)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        payload = f"{text}\n".encode(encoding, errors="replace")
        buffer = getattr(stream, "buffer", None)
        if buffer:
            buffer.write(payload)
            buffer.flush()
        else:
            stream.write(payload.decode(encoding, errors="replace"))


def run_step(name: str, args: list[str], timeout: int | None = None) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    command = [sys.executable, *args]
    emit_text(f"\n== {name} ==")
    emit_text(" ".join(command))
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
    finished = datetime.now(timezone.utc)
    emit_text(result.stdout)
    if result.stderr:
        emit_text(result.stderr, stream=sys.stderr)
    return {
        "name": name,
        "command": command,
        "returncode": result.returncode,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_seconds": round((finished - started).total_seconds(), 2),
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }


def run_required_step(
    payload: dict[str, Any],
    name: str,
    args: list[str],
    timeout: int | None = None,
) -> dict[str, Any]:
    step = run_step(name, args, timeout)
    payload["steps"].append(step)
    if step["returncode"] != 0:
        raise StepFailed(step)
    return step


def data_summary() -> dict[str, Any]:
    data_path = ROOT / "tl_ma_radar" / "data" / "real_candidates.json"
    if not data_path.exists():
        return {"candidates": 0}
    rows = json.loads(data_path.read_text(encoding="utf-8"))
    analyses = [row.get("report_analysis") or {} for row in rows]
    deal_memo_files = len(list((ROOT / "tl_ma_radar" / "data" / "deal_memos").glob("*.md")))
    embedded_deal_memos = sum(1 for row in rows if row.get("deal_memo"))
    summary = {
        "candidates": len(rows),
        "dart_ok": sum(1 for row in rows if row.get("dart_enrichment", {}).get("status") == "ok"),
        "dart_filing_files": len(list((ROOT / "tl_ma_radar" / "data" / "dart_filings").glob("*.json"))),
        "report_analysis": sum(1 for analysis in analyses if analysis),
        "report_text_analysis": sum(1 for analysis in analyses if int(analysis.get("text_chars") or 0) > 0),
        "report_analysis_errors": sum(1 for analysis in analyses if analysis.get("status") == "error"),
        "report_entries": sum(len(analysis.get("reports_analyzed") or []) for analysis in analyses),
        "deal_signals": sum(1 for row in rows if row.get("deal_signals")),
        "deal_memos": max(embedded_deal_memos, deal_memo_files),
        "deal_memo_files": deal_memo_files,
        "report_zips": len(list((ROOT / "tl_ma_radar" / "data" / "dart_reports").rglob("*.zip"))),
        "quality_reports": len(list((ROOT / "tl_ma_radar" / "data" / "quality_reports").glob("*.json"))),
    }
    news_path = ROOT / "tl_ma_radar" / "data" / "candidate_news.json"
    if news_path.exists():
        news_payload = json.loads(news_path.read_text(encoding="utf-8"))
        news_items = news_payload.get("items", news_payload) if isinstance(news_payload, dict) else {}
        summary["news_analysis"] = sum(1 for row in news_items.values() if row.get("status") == "ok")
        summary["news_errors"] = sum(1 for row in news_items.values() if row.get("status") == "error")
    monitoring_path = ROOT / "tl_ma_radar" / "data" / "monitoring" / "latest.json"
    if monitoring_path.exists():
        monitoring = json.loads(monitoring_path.read_text(encoding="utf-8"))
        summary["monitoring_alerts"] = len(monitoring.get("alerts") or [])
        summary["monitoring_baseline"] = bool(monitoring.get("baseline"))
    return summary


def write_run_log(payload: dict[str, Any]) -> Path:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    path = RUN_DIR / f"{payload['run_id']}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = RUN_DIR / "latest.json"
    latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_pipeline(args: argparse.Namespace) -> Path:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    payload: dict[str, Any] = {
        "run_id": run_id,
        "mode": "snapshot" if args.snapshot_only else args.mode,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "steps": [],
    }
    try:
        if args.snapshot_only:
            payload["status"] = "ok"
            payload["note"] = "Current persisted data snapshot; no collection or analysis steps were executed."
            payload["finished_at"] = datetime.now(timezone.utc).isoformat()
            payload["summary"] = data_summary()
            path = write_run_log(payload)
            print(f"\nPipeline {payload['status']} -> {path}")
            return path
        if args.mode == "full":
            run_required_step(
                payload,
                "refresh_candidates",
                ["scripts/refresh_candidates.py", *([] if args.limit is None else ["--limit", str(args.limit)])],
                timeout=900,
            )
            run_required_step(
                payload,
                "enrich_candidates",
                [
                    "scripts/enrich_candidates.py",
                    "--begin",
                    args.begin,
                    "--end",
                    args.end,
                    "--download-reports",
                    args.download_reports,
                    "--sleep",
                    str(args.sleep),
                    *([] if args.limit is None else ["--limit", str(args.limit)]),
                ],
                timeout=7200,
            )
        report_args = ["scripts/analyze_reports.py", "--max-reports", str(args.max_reports)]
        if args.save_text:
            report_args.append("--save-text")
        if args.include_pdfs:
            report_args.append("--include-pdfs")
        run_required_step(payload, "analyze_reports", report_args, timeout=3600)
        run_required_step(payload, "analyze_event_digest", ["scripts/analyze_event_digest.py"], timeout=900)
        run_required_step(payload, "analyze_deal_signals", ["scripts/analyze_deal_signals.py"], timeout=900)
        news_mode = "top" if args.news == "auto" and args.mode == "full" else args.news
        if args.news == "auto" and args.mode == "offline":
            news_mode = "skip"
        if news_mode != "skip":
            news_args = [
                "scripts/collect_news.py",
                "--months",
                str(args.news_months),
                "--max-articles",
                str(args.news_max_articles),
                "--sleep",
                str(args.news_sleep),
            ]
            if news_mode == "top":
                news_args.extend(["--limit", str(args.news_limit)])
            run_required_step(payload, "collect_news", news_args, timeout=3600)
        run_required_step(
            payload,
            "generate_deal_memos",
            ["scripts/generate_deal_memos.py", "--limit", str(args.memo_limit)],
            timeout=900,
        )
        run_required_step(
            payload,
            "analyze_monitoring",
            ["scripts/analyze_monitoring.py", "--run-id", run_id],
            timeout=900,
        )
        run_required_step(
            payload,
            "export_daily_quality_report",
            ["scripts/export_daily_quality_report.py"],
            timeout=900,
        )
        payload["status"] = "ok"
    except StepFailed as exc:
        payload["status"] = "failed"
        payload["error"] = str(exc)
        payload["aborted_after"] = exc.step["name"]
    except Exception as exc:
        payload["status"] = "error"
        payload["error"] = str(exc)
    payload["finished_at"] = datetime.now(timezone.utc).isoformat()
    payload["summary"] = data_summary()
    path = write_run_log(payload)
    print(f"\nPipeline {payload['status']} -> {path}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the TL M&A Radar refresh/analyze pipeline.")
    parser.add_argument("--mode", choices=["offline", "full"], default="offline")
    parser.add_argument("--begin", default="20250101")
    parser.add_argument("--end", default=date.today().strftime("%Y%m%d"))
    parser.add_argument("--download-reports", choices=["none", "latest", "all"], default="latest")
    parser.add_argument("--sleep", type=float, default=0.15)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-reports", type=int, default=2)
    parser.add_argument("--save-text", action="store_true")
    parser.add_argument("--include-pdfs", action="store_true")
    parser.add_argument("--memo-limit", type=int, default=30)
    parser.add_argument(
        "--snapshot-only",
        action="store_true",
        help="Write pipeline_runs/latest.json from current persisted data without running refresh steps.",
    )
    parser.add_argument("--news", choices=["auto", "skip", "top", "all"], default="auto")
    parser.add_argument("--news-limit", type=int, default=80)
    parser.add_argument("--news-months", type=int, default=6)
    parser.add_argument("--news-max-articles", type=int, default=30)
    parser.add_argument("--news-sleep", type=float, default=0.25)
    args = parser.parse_args()
    start = time.time()
    path = run_pipeline(args)
    print(f"elapsed={time.time() - start:.1f}s")
    print(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") != "ok":
        sys.exit(1)


if __name__ == "__main__":
    main()
