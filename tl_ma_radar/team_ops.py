from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_DIR = Path("tl_ma_radar") / "data"


def _run_git(root: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=6,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _exists(root: Path, relative: str) -> bool:
    return (root / relative).exists()


def _file_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "size_mb": 0, "updated_at": None}
    stat = path.stat()
    return {
        "exists": True,
        "size_mb": round(stat.st_size / 1024 / 1024, 2),
        "updated_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def team_ops_status(root: Path, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    remote_url = _run_git(root, ["remote", "get-url", "origin"])
    branch = _run_git(root, ["branch", "--show-current"])
    commit = _run_git(root, ["rev-parse", "--short", "HEAD"])
    hook_path = root / ".git" / "hooks" / "post-commit"
    data_files = {
        "candidates": _file_info(root / DATA_DIR / "real_candidates.json"),
        "news": _file_info(root / DATA_DIR / "candidate_news.json"),
        "workflow": _file_info(root / DATA_DIR / "candidate_workflow.json"),
        "monitoring": _file_info(root / DATA_DIR / "monitoring" / "latest.json"),
    }
    filings_dir = root / DATA_DIR / "dart_filings"
    filing_count = len(list(filings_dir.glob("*.json"))) if filings_dir.exists() else 0
    checks = [
        {"label": "GitHub 원격 저장소", "status": "ok" if remote_url else "warn", "value": remote_url or "미설정"},
        {"label": "자동 푸시 훅", "status": "ok" if hook_path.exists() else "warn", "value": "설치됨" if hook_path.exists() else "미설치"},
        {"label": "Windows 첫 실행 스크립트", "status": "ok" if _exists(root, "FIRST_RUN_WINDOWS.ps1") else "warn", "value": "있음" if _exists(root, "FIRST_RUN_WINDOWS.ps1") else "없음"},
        {"label": "실행 스크립트", "status": "ok" if _exists(root, "start_radar.ps1") else "warn", "value": "있음" if _exists(root, "start_radar.ps1") else "없음"},
        {"label": "환경변수 예시", "status": "ok" if _exists(root, ".env.example") else "warn", "value": "있음" if _exists(root, ".env.example") else "없음"},
        {"label": "DART 공시 파일", "status": "ok" if filing_count else "warn", "value": f"{filing_count}개"},
    ]
    return {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git": {
            "remote": remote_url,
            "branch": branch,
            "commit": commit,
            "auto_push_hook": hook_path.exists(),
        },
        "data": {
            "candidate_count": len(candidates),
            "dart_filing_files": filing_count,
            "files": data_files,
        },
        "checks": checks,
        "handoff": {
            "clone": "git clone https://github.com/DavidAction/M-A-Radar.git",
            "first_run": "powershell -ExecutionPolicy Bypass -File FIRST_RUN_WINDOWS.ps1",
            "start": "powershell -ExecutionPolicy Bypass -File start_radar.ps1",
            "url": "http://127.0.0.1:8765",
            "note": ".env는 보안을 위해 GitHub에 올리지 않으므로 새 PC에서 DART/Naver 키를 입력해야 합니다.",
        },
        "exports": {
            "word_report": "/api/export-deal-cards.docx",
            "shortlist_csv": "/api/export-shortlist.csv",
            "monitoring_csv": "/api/export-monitoring.csv",
            "pipeline_sqlite": "/api/export-pipeline.sqlite",
        },
    }


def build_pipeline_sqlite(candidates: list[dict[str, Any]]) -> bytes:
    fd, raw_path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    db_path = Path(raw_path)
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                create table candidates (
                    code text primary key,
                    name text,
                    market text,
                    sector text,
                    score real,
                    shortlist_score real,
                    market_cap_krw real,
                    recommendation text,
                    data_quality_score real,
                    data_quality_grade text,
                    workflow_status text,
                    workflow_owner text,
                    next_action text,
                    raw_json text
                )
                """
            )
            conn.execute(
                """
                create table news (
                    code text,
                    article_count integer,
                    tone text,
                    risk_score real,
                    momentum_score real,
                    collected_at text,
                    raw_json text
                )
                """
            )
            conn.execute(
                """
                create table workflow_history (
                    code text,
                    event_at text,
                    event_type text,
                    summary text,
                    raw_json text
                )
                """
            )
            for item in candidates:
                scores = item.get("scores") or {}
                quality = item.get("data_quality") or {}
                workflow = item.get("workflow") or {}
                news = item.get("news_analysis") or {}
                news_scores = news.get("scores") or {}
                conn.execute(
                    """
                    insert or replace into candidates values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.get("code"),
                        item.get("name"),
                        item.get("market"),
                        item.get("sector"),
                        scores.get("total"),
                        item.get("shortlist_score"),
                        item.get("market_cap_krw"),
                        item.get("recommendation"),
                        quality.get("score"),
                        quality.get("grade"),
                        workflow.get("status"),
                        workflow.get("owner"),
                        workflow.get("next_action"),
                        json.dumps(item, ensure_ascii=False),
                    ),
                )
                conn.execute(
                    "insert into news values (?, ?, ?, ?, ?, ?, ?)",
                    (
                        item.get("code"),
                        news.get("article_count"),
                        news.get("tone"),
                        news_scores.get("risk"),
                        news_scores.get("momentum"),
                        news.get("collected_at"),
                        json.dumps(news, ensure_ascii=False),
                    ),
                )
                for event in workflow.get("history") or []:
                    conn.execute(
                        "insert into workflow_history values (?, ?, ?, ?, ?)",
                        (
                            item.get("code"),
                            event.get("at"),
                            event.get("type"),
                            event.get("summary"),
                            json.dumps(event, ensure_ascii=False),
                        ),
                    )
        body = db_path.read_bytes()
        return body
    finally:
        try:
            db_path.unlink(missing_ok=True)
        except PermissionError:
            pass
