from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATUS_DIR = Path("tl_ma_radar") / "data" / "quality_remediation"


def remediation_dir(root: Path) -> Path:
    return root / STATUS_DIR


def read_remediation_status(root: Path) -> dict[str, Any]:
    path = remediation_dir(root) / "latest.json"
    if not path.exists():
        return {"status": "not_run"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "error", "message": str(exc)}


def start_quality_remediation(root: Path, *, limit: int = 30, max_reports: int = 4) -> dict[str, Any]:
    log_dir = remediation_dir(root)
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stdout_path = log_dir / f"{stamp}.out.log"
    stderr_path = log_dir / f"{stamp}.err.log"
    command = [
        sys.executable,
        "scripts/run_quality_remediation.py",
        "--limit",
        str(limit),
        "--max-reports",
        str(max_reports),
    ]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(command, cwd=root, stdout=stdout, stderr=stderr, env=env)
    payload = {
        "status": "started",
        "pid": process.pid,
        "command": command,
        "limit": limit,
        "max_reports": max_reports,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
    }
    (log_dir / "latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
