from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


TASK_NAME = "TL M&A Radar Daily Pipeline"
SERVER_TASK_NAME = "TL M&A Radar Always-On Server"
DATA_DIR = Path("tl_ma_radar") / "data"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def _read_tail(path: Path, chars: int = 1200) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-chars:]


def _task_result_label(code: Any) -> str:
    try:
        value = int(code)
    except (TypeError, ValueError):
        return "unknown"
    if value == 0:
        return "success"
    if value == 267009:
        return "running"
    if value == 267011:
        return "not_run"
    return "failed"


def _scheduler_config(root: Path) -> dict[str, Any]:
    return _read_json(root / DATA_DIR / "scheduler_config.json", {})


def _server_config(root: Path) -> dict[str, Any]:
    return _read_json(root / DATA_DIR / "server_task_config.json", {})


def _query_scheduled_task(task_name: str = TASK_NAME) -> dict[str, Any]:
    command = f"""
$ErrorActionPreference = 'Stop'
$task = Get-ScheduledTask -TaskName {json.dumps(task_name)} -ErrorAction Stop
$info = Get-ScheduledTaskInfo -TaskName {json.dumps(task_name)} -ErrorAction Stop
[pscustomobject]@{{
  task_name = $task.TaskName
  state = $task.State.ToString()
  enabled = $task.Triggers[0].Enabled
  next_run_time = $info.NextRunTime.ToString('yyyy-MM-dd HH:mm:ss')
  last_run_time = $info.LastRunTime.ToString('yyyy-MM-dd HH:mm:ss')
  last_task_result = $info.LastTaskResult
  action = $task.Actions[0].Arguments
}} | ConvertTo-Json -Compress
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "unavailable", "error": str(exc)}

    if result.returncode != 0:
        return {
            "status": "unavailable",
            "error": (result.stderr or result.stdout or "").strip(),
        }

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"status": "unavailable", "error": "Invalid scheduler response"}
    payload["status"] = "ok"
    payload["last_task_result_label"] = _task_result_label(payload.get("last_task_result"))
    return payload


def _latest_pipeline(root: Path) -> dict[str, Any]:
    payload = _read_json(root / DATA_DIR / "pipeline_runs" / "latest.json", {"status": "not_run"})
    steps = payload.get("steps") or []
    duration = sum(float(step.get("duration_seconds") or 0) for step in steps)
    return {
        "status": payload.get("status"),
        "run_id": payload.get("run_id"),
        "mode": payload.get("mode"),
        "started_at": payload.get("started_at"),
        "finished_at": payload.get("finished_at"),
        "duration_seconds": round(duration, 1),
        "summary": payload.get("summary") or {},
        "error": payload.get("error"),
        "aborted_after": payload.get("aborted_after"),
    }


def _latest_monitoring(root: Path) -> dict[str, Any]:
    payload = _read_json(root / DATA_DIR / "monitoring" / "latest.json", {"status": "not_run"})
    return {
        "status": payload.get("status"),
        "run_id": payload.get("run_id"),
        "baseline": payload.get("baseline"),
        "summary": payload.get("summary"),
        "alert_count": len(payload.get("alerts") or []),
        "counts": payload.get("counts") or {},
    }


def _recent_scheduled_runs(root: Path, limit: int = 5) -> list[dict[str, Any]]:
    log_dir = root / DATA_DIR / "scheduled_runs"
    if not log_dir.exists():
        return []
    rows = []
    meta_paths = [path for path in log_dir.glob("*.meta.json") if path.name != "latest.meta.json"]
    for meta_path in sorted(meta_paths, key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
        meta = _read_json(meta_path, {})
        stdout_path = Path(meta.get("stdout_log") or "")
        stderr_path = Path(meta.get("stderr_log") or "")
        rows.append(
            {
                "id": meta_path.stem.removesuffix(".meta"),
                "started_at": meta.get("started_at"),
                "finished_at": meta.get("finished_at"),
                "exit_code": meta.get("exit_code"),
                "status": "success" if meta.get("exit_code") == 0 else "failed",
                "mode": meta.get("mode"),
                "download_reports": meta.get("download_reports"),
                "stdout_tail": _read_tail(stdout_path),
                "stderr_tail": _read_tail(stderr_path),
            }
        )
    return rows


def operations_status(root: Path) -> dict[str, Any]:
    config = _scheduler_config(root)
    scheduler = _query_scheduled_task(str(config.get("task_name") or TASK_NAME))
    if scheduler.get("status") != "ok" and config:
        scheduler = {
            "status": "configured",
            "query_status": scheduler.get("status"),
            "query_error": scheduler.get("error"),
            "task_name": config.get("task_name"),
            "state": "Unknown",
            "enabled": config.get("enabled"),
            "next_run_time": config.get("next_run_time"),
            "action": config.get("action"),
            "mode": config.get("mode"),
        }

    server_config = _server_config(root)
    server = _query_scheduled_task(str(server_config.get("task_name") or SERVER_TASK_NAME))
    if server.get("status") != "ok" and server_config:
        server = {
            "status": "configured",
            "query_status": server.get("status"),
            "query_error": server.get("error"),
            "task_name": server_config.get("task_name"),
            "state": "Unknown",
            "enabled": server_config.get("enabled"),
            "url": server_config.get("url"),
            "action": server_config.get("action"),
        }

    recent_runs = _recent_scheduled_runs(root)
    latest_run = recent_runs[0] if recent_runs else None
    pipeline = _latest_pipeline(root)
    monitoring = _latest_monitoring(root)
    return {
        "status": "ok",
        "scheduler": scheduler,
        "server": server,
        "latest_scheduled_run": latest_run,
        "recent_scheduled_runs": recent_runs,
        "pipeline": pipeline,
        "monitoring": monitoring,
        "log_dir": str(root / DATA_DIR / "scheduled_runs"),
    }
