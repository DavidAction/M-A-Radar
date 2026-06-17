from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DATA_DIR = Path("tl_ma_radar") / "data"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def _mtime(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def build_automation_plan(root: Path) -> dict[str, Any]:
    pipeline = _read_json(root / DATA_DIR / "pipeline_runs" / "latest.json", {"status": "not_run"})
    monitoring = _read_json(root / DATA_DIR / "monitoring" / "latest.json", {"status": "not_run"})
    scheduler = _read_json(root / DATA_DIR / "scheduler_config.json", {})
    server_task = _read_json(root / DATA_DIR / "server_task_config.json", {})
    return {
        "status": "ok",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current_state": {
            "pipeline_status": pipeline.get("status"),
            "pipeline_finished_at": pipeline.get("finished_at"),
            "monitoring_status": monitoring.get("status"),
            "monitoring_alert_count": len(monitoring.get("alerts") or []),
            "scheduler_configured": bool(scheduler),
            "always_on_server_configured": bool(server_task),
            "always_on_server_url": server_task.get("url"),
            "candidate_data_updated_at": _mtime(root / DATA_DIR / "real_candidates.json"),
            "news_updated_at": _mtime(root / DATA_DIR / "candidate_news.json"),
        },
        "cadence": [
            {
                "name": "Daily Radar Refresh",
                "frequency": "매일 장 시작 전 또는 업무 시작 전",
                "command": "powershell -ExecutionPolicy Bypass -File scripts\\run_daily_pipeline.ps1 -Mode full -News top -IncludePdfs -SaveText",
                "purpose": "DART 최신 공시, 상위 후보 뉴스, 보고서 원문, 품질/알림 리포트 갱신",
            },
            {
                "name": "Weekly Full Refresh",
                "frequency": "매주 1회",
                "command": "python scripts\\run_pipeline.py --mode full --download-reports latest --include-pdfs --save-text --news all",
                "purpose": "전체 후보 뉴스/보고서 보강 및 스코어 재산정",
            },
            {
                "name": "Monthly IC Pack",
                "frequency": "월 1회 또는 IC 전",
                "command": "브라우저에서 /api/export-deal-cards.docx?format=ic 다운로드",
                "purpose": "상위 후보 투자심의 패키지 생성",
            },
            {
                "name": "Always-On Web Server",
                "frequency": "Windows 로그인 시 자동 실행 또는 Docker restart",
                "command": "powershell -ExecutionPolicy Bypass -File scripts\\install_startup_server.ps1 -Lan -StartNow",
                "purpose": "로컬 실행 없이 팀이 접속 가능한 상시 M&A 레이더 운영",
            },
        ],
        "alert_rules": [
            "최대주주 변경, 유상증자, CB/BW, 감자, 거래정지 공시 발생",
            "뉴스 리스크 65점 이상 또는 리스크 이벤트 3건 이상 발생",
            "IC 준비도 70점 이상 신규 진입",
            "데이터 신뢰도 60점 미만으로 하락",
            "후보별 검토 기한 3영업일 이내 도래",
        ],
        "operator_checklist": [
            "매일 IC 패키지 상위 후보와 모니터링 알림 확인",
            "신규 공시 발생 후보는 보고서 원문 PDF 다운로드 후 리스크 문단 확인",
            "뉴스 이벤트가 큰 후보는 DART 공시와 매칭하여 오보/중복 여부 확인",
            "접촉/실사중 후보는 다음 액션과 기한을 반드시 업데이트",
            "주 1회 GitHub 원격 저장소와 데이터 export 정상 여부 확인",
        ],
        "setup_commands": [
            "powershell -ExecutionPolicy Bypass -File scripts\\install_daily_task.ps1",
            "powershell -ExecutionPolicy Bypass -File scripts\\install_always_on_server.ps1 -Lan -StartNow",
            "powershell -ExecutionPolicy Bypass -File scripts\\install_startup_server.ps1 -Lan -StartNow",
            "docker compose up -d --build",
            "powershell -ExecutionPolicy Bypass -File scripts\\git_auto_push.ps1 -Message \"daily refresh\"",
        ],
    }
