from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from enrich_candidates import infer_flags, report_category, report_pdf_download_url, select_periodic_reports  # noqa: E402


DATA_PATH = ROOT / "tl_ma_radar" / "data" / "real_candidates.json"
FILINGS_DIR = ROOT / "tl_ma_radar" / "data" / "dart_filings"


def load_rows() -> list[dict[str, Any]]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def write_rows(rows: list[dict[str, Any]]) -> None:
    DATA_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def load_filings(code: str) -> list[dict[str, Any]]:
    path = FILINGS_DIR / f"{code}.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else []


def _date_range(filings: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    dates = sorted({str(row.get("rcept_dt") or "") for row in filings if row.get("rcept_dt")})
    if not dates:
        return None, None
    return dates[0], dates[-1]


def _with_download_links(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for report in reports:
        copied = dict(report)
        receipt_no = copied.get("rcept_no")
        report_name = copied.get("report_nm") or "report"
        if receipt_no and not copied.get("pdf_download_url"):
            copied["pdf_download_url"] = report_pdf_download_url(receipt_no, report_name)
        output.append(copied)
    return output


def _append_note(source_note: str, filing_count: int) -> str:
    note = source_note or ""
    marker = "DART filings cache 백필"
    if marker in note:
        return note
    suffix = f"{marker} {filing_count}건 반영"
    return f"{note} / {suffix}".strip(" /")


def backfill(download_mode: str, overwrite: bool) -> int:
    rows = load_rows()
    output: list[dict[str, Any]] = []
    updated_count = 0
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        updated = dict(row)
        current = updated.get("dart_enrichment") or {}
        if current.get("status") == "ok" and not overwrite:
            output.append(updated)
            continue
        filings = load_filings(str(updated.get("code") or ""))
        if not filings:
            output.append(updated)
            continue
        begin_date, end_date = _date_range(filings)
        corp_code = updated.get("dart_corp_code") or filings[0].get("corp_code")
        periodic_all = [filing for filing in filings if report_category(filing.get("report_nm", ""))]
        selected = select_periodic_reports(filings, download_mode)
        updated["dart_corp_code"] = corp_code
        updated["dart_enrichment"] = {
            "status": "ok",
            "corp_code": corp_code,
            "begin_date": begin_date,
            "end_date": end_date,
            "fetched_at": now,
            "source": "dart_filings_cache",
            "filing_count": len(filings),
            "latest_filing": filings[0] if filings else None,
            "periodic_report_count": len(periodic_all),
            "periodic_reports": _with_download_links(selected),
            "financials": current.get("financials") or {},
        }
        updated["status_flags"] = list(dict.fromkeys([*(updated.get("status_flags") or []), *infer_flags(filings)]))
        updated["source_note"] = _append_note(updated.get("source_note", ""), len(filings))
        output.append(updated)
        updated_count += 1
    write_rows(output)
    return updated_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill dart_enrichment from cached DART filing list JSON files.")
    parser.add_argument("--download-reports", choices=["none", "latest", "all"], default="latest")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    count = backfill(download_mode=args.download_reports, overwrite=args.overwrite)
    print(f"backfilled={count}")


if __name__ == "__main__":
    main()
