from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tl_ma_radar.collectors.dart import DartClient, download_filing_pdf  # noqa: E402
from tl_ma_radar.config import get_settings  # noqa: E402


DATA_DIR = ROOT / "tl_ma_radar" / "data"
REPORT_ROOT = DATA_DIR / "dart_reports"
PDF_ROOT = DATA_DIR / "dart_pdfs"
FILINGS_ROOT = DATA_DIR / "dart_filings"
PERIODIC_ORDER = ("사업보고서", "감사보고서", "분기보고서", "반기보고서", "연결감사보고서")


def safe_filename(value: str) -> str:
    normalized = re.sub(r"[\\/:*?\"<>|]+", "_", value or "")
    normalized = re.sub(r"\s+", "_", normalized.strip())
    return normalized[:90] or "report"


def report_download_url(relative_path: str) -> str:
    return f"/api/download-report?path={relative_path}"


def report_pdf_download_url(receipt_no: str, report_name: str) -> str:
    return f"/api/download-report-pdf?{urlencode({'rcp_no': receipt_no, 'name': report_name})}"


def load_rows() -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / "real_candidates.json").read_text(encoding="utf-8"))


def write_rows(rows: list[dict[str, Any]]) -> None:
    (DATA_DIR / "real_candidates.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def report_category(report_name: str) -> str | None:
    for label in PERIODIC_ORDER:
        if label in (report_name or ""):
            return label
    return None


def filings_for(row: dict[str, Any]) -> list[dict[str, Any]]:
    code = str(row.get("code") or "")
    path = FILINGS_ROOT / f"{code}.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else []


def selected_reports(row: dict[str, Any], max_reports: int) -> list[dict[str, Any]]:
    dart = row.get("dart_enrichment") if isinstance(row.get("dart_enrichment"), dict) else {}
    reports = list(dart.get("periodic_reports") or [])
    if not reports:
        reports = [filing for filing in filings_for(row) if report_category(str(filing.get("report_nm") or ""))]
    unique: dict[str, dict[str, Any]] = {}
    for report in reports:
        if not isinstance(report, dict):
            continue
        receipt_no = str(report.get("rcept_no") or report.get("rcp_no") or "")
        if receipt_no and receipt_no not in unique:
            unique[receipt_no] = dict(report)
    def sort_key(report: dict[str, Any]) -> tuple[int, int]:
        category = report_category(str(report.get("report_nm") or ""))
        category_rank = PERIODIC_ORDER.index(category) if category in PERIODIC_ORDER else 99
        date_text = re.sub(r"\D+", "", str(report.get("rcept_dt") or "0"))
        date_rank = -int(date_text or "0")
        return (category_rank, date_rank)

    ordered = list(unique.values())
    ordered.sort(key=sort_key)
    return ordered[:max_reports]


def needs_report_text(row: dict[str, Any]) -> bool:
    report = row.get("report_analysis") if isinstance(row.get("report_analysis"), dict) else {}
    return int(report.get("text_chars") or 0) <= 0


def quality_rank(row: dict[str, Any]) -> tuple[int, float, str]:
    missing_text = 0 if needs_report_text(row) else 1
    scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
    report_score = float(scores.get("report_evidence") or 0)
    return (missing_text, report_score, str(row.get("name") or ""))


def local_zip_path(row: dict[str, Any], report: dict[str, Any]) -> Path:
    company_dir = REPORT_ROOT / f"{row.get('code')}_{safe_filename(str(row.get('name') or 'company'))}"
    filename = "_".join(
        [
            str(report.get("rcept_dt") or ""),
            str(report.get("rcept_no") or report.get("rcp_no") or ""),
            safe_filename(str(report.get("report_nm") or "report")),
        ]
    ).strip("_")
    return company_dir / f"{filename}.zip"


def local_pdf_path(report: dict[str, Any]) -> Path:
    receipt_no = str(report.get("rcept_no") or report.get("rcp_no") or "")
    report_name = safe_filename(str(report.get("report_nm") or "report"))
    return PDF_ROOT / f"{receipt_no}_{report_name}.pdf"


def enrich_report(client: DartClient, row: dict[str, Any], report: dict[str, Any], download_pdf: bool) -> dict[str, Any]:
    copied = dict(report)
    receipt_no = str(copied.get("rcept_no") or copied.get("rcp_no") or "")
    report_name = str(copied.get("report_nm") or "report")
    if not receipt_no:
        copied["download_error"] = "missing receipt number"
        return copied
    zip_path = local_zip_path(row, copied)
    try:
        if not zip_path.exists():
            client.download_document(receipt_no, zip_path)
        relative = zip_path.relative_to(REPORT_ROOT).as_posix()
        copied["local_path"] = relative
        copied["download_url"] = report_download_url(relative)
        copied["downloaded_at"] = datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        copied["download_error"] = str(exc)
    copied["pdf_download_url"] = report_pdf_download_url(receipt_no, report_name)
    if download_pdf:
        pdf_path = local_pdf_path(copied)
        try:
            if not pdf_path.exists():
                download_filing_pdf(receipt_no, pdf_path)
            copied["pdf_local_path"] = pdf_path.relative_to(DATA_DIR).as_posix()
        except Exception as exc:
            copied["pdf_download_error"] = str(exc)
    return copied


def merge_periodic_reports(existing: list[dict[str, Any]], updated: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for report in existing + updated:
        if not isinstance(report, dict):
            continue
        receipt_no = str(report.get("rcept_no") or report.get("rcp_no") or "")
        if not receipt_no:
            continue
        current = merged.get(receipt_no, {})
        current.update(report)
        merged[receipt_no] = current
    rows = list(merged.values())
    rows.sort(key=lambda report: str(report.get("rcept_dt") or ""), reverse=True)
    return rows


def download_missing(limit: int | None, max_reports: int, download_pdf: bool, only_missing: bool, sleep: float) -> dict[str, Any]:
    settings = get_settings(ROOT)
    if not settings.dart_api_key:
        raise ValueError("DART_API_KEY is missing")
    rows = load_rows()
    targets = [row for row in rows if needs_report_text(row)] if only_missing else list(rows)
    targets.sort(key=quality_rank)
    if limit:
        targets = targets[:limit]
    target_codes = {str(row.get("code") or "") for row in targets}
    client = DartClient(settings.dart_api_key, timeout=45)
    updated_count = 0
    report_count = 0
    error_count = 0
    output: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        code = str(row.get("code") or "")
        if code not in target_codes:
            output.append(row)
            continue
        selected = selected_reports(row, max_reports)
        print(f"[{idx}/{len(rows)}] {code} {row.get('name')} reports={len(selected)}")
        updated_reports = [enrich_report(client, row, report, download_pdf) for report in selected]
        error_count += sum(1 for report in updated_reports if report.get("download_error"))
        report_count += sum(1 for report in updated_reports if report.get("local_path"))
        updated = dict(row)
        dart = dict(updated.get("dart_enrichment") or {})
        dart["periodic_reports"] = merge_periodic_reports(list(dart.get("periodic_reports") or []), updated_reports)
        dart["report_backfill_at"] = datetime.now(timezone.utc).isoformat()
        updated["dart_enrichment"] = dart
        output.append(updated)
        updated_count += 1
        time.sleep(sleep)
    write_rows(output)
    return {
        "status": "ok",
        "updated_candidates": updated_count,
        "downloaded_or_cached_reports": report_count,
        "download_errors": error_count,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Download missing DART periodic report ZIP/PDF files.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-reports", type=int, default=4)
    parser.add_argument("--download-pdf", action="store_true")
    parser.add_argument("--all-candidates", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.12)
    args = parser.parse_args()
    payload = download_missing(
        limit=args.limit,
        max_reports=args.max_reports,
        download_pdf=args.download_pdf,
        only_missing=not args.all_candidates,
        sleep=args.sleep,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
