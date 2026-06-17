from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tl_ma_radar.report_parser import (  # noqa: E402
    RENES_SYNERGY_TERMS,
    TL_SYNERGY_TERMS,
    analyze_text,
    extract_pdf_text,
    extract_zip_text,
)


PARSER_KEYWORDS = set(TL_SYNERGY_TERMS) | set(RENES_SYNERGY_TERMS)
STALE_PARSER_KEYWORDS = {"원료", "유통", "가공/납품"}
REPORT_NOTE_RE = re.compile(r"\s*/\s*보고서 원문 \d+건 텍스트 분석")


def load_rows() -> list[dict[str, Any]]:
    path = ROOT / "tl_ma_radar" / "data" / "real_candidates.json"
    return json.loads(path.read_text(encoding="utf-8"))


def write_rows(rows: list[dict[str, Any]]) -> None:
    path = ROOT / "tl_ma_radar" / "data" / "real_candidates.json"
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def report_path(local_path: str) -> Path:
    return ROOT / "tl_ma_radar" / "data" / "dart_reports" / local_path


def cached_pdf_path(report: dict[str, Any]) -> Path | None:
    receipt_no = report.get("rcept_no") or report.get("rcp_no")
    if not receipt_no:
        return None
    pdf_root = ROOT / "tl_ma_radar" / "data" / "dart_pdfs"
    matches = sorted(pdf_root.glob(f"{receipt_no}_*.pdf"))
    return matches[0] if matches else None


def select_reports(row: dict[str, Any], max_reports: int) -> list[dict[str, Any]]:
    reports = row.get("dart_enrichment", {}).get("periodic_reports", [])
    preferred_order = ["사업보고서", "분기보고서", "반기보고서", "감사보고서"]
    selected: list[dict[str, Any]] = []
    for needle in preferred_order:
        for report in reports:
            if len(selected) >= max_reports:
                return selected
            if needle in (report.get("report_nm") or "") and report.get("local_path") and report not in selected:
                selected.append(report)
    for report in reports:
        if len(selected) >= max_reports:
            break
        if report.get("local_path") and report not in selected:
            selected.append(report)
    return selected


def merge_unique(original: list[str], added: list[str]) -> list[str]:
    return list(dict.fromkeys([*(original or []), *added]))


def update_source_note(note: str, report_count: int) -> str:
    cleaned = REPORT_NOTE_RE.sub("", note or "")
    parts = [part.strip() for part in cleaned.split("/") if part.strip()]
    unique_parts = list(dict.fromkeys(parts))
    unique_parts.append(f"보고서 원문 {report_count}건 텍스트 분석")
    return " / ".join(unique_parts)


def analyze_row(row: dict[str, Any], max_reports: int, save_text: bool, include_pdfs: bool) -> dict[str, Any]:
    selected = select_reports(row, max_reports)
    text_parts: list[str] = []
    parsed_reports = []
    for report in selected:
        path = report_path(report["local_path"])
        if not path.exists():
            continue
        parsed = extract_zip_text(path)
        if parsed.text:
            text_parts.append(parsed.text)
        parsed_reports.append(
            {
                "report_nm": report.get("report_nm"),
                "rcept_dt": report.get("rcept_dt"),
                "local_path": report.get("local_path"),
                "source": "zip_xml",
                "text_chars": len(parsed.text),
            }
        )
        if include_pdfs and (pdf_path := cached_pdf_path(report)) and pdf_path.exists():
            pdf_parsed = extract_pdf_text(pdf_path)
            if pdf_parsed.text:
                text_parts.append(pdf_parsed.text)
            parsed_reports.append(
                {
                    "report_nm": report.get("report_nm"),
                    "rcept_dt": report.get("rcept_dt"),
                    "local_path": pdf_path.relative_to(ROOT / "tl_ma_radar" / "data").as_posix(),
                    "source": "pdf",
                    "text_chars": len(pdf_parsed.text),
                }
            )

    combined_text = " ".join(text_parts)
    analysis = analyze_text(combined_text)
    analysis["analyzed_at"] = datetime.now(timezone.utc).isoformat()
    analysis["reports_analyzed"] = parsed_reports

    updated = dict(row)
    updated["report_analysis"] = analysis
    base_keywords = [
        keyword
        for keyword in (row.get("business_keywords") or [])
        if keyword not in PARSER_KEYWORDS and keyword not in STALE_PARSER_KEYWORDS
    ]
    updated["business_keywords"] = merge_unique(base_keywords, analysis["business_keywords"])
    updated["status_flags"] = merge_unique(row.get("status_flags") or [], analysis["risk_flags"])
    shareholder = analysis.get("largest_shareholder")
    if shareholder and updated.get("largest_shareholder_ratio") is None:
        updated["largest_shareholder_ratio"] = shareholder["ratio"]
    if analysis["inferred_sector"] and updated.get("sector") == "시장 스크리닝":
        updated["sector"] = analysis["inferred_sector"]
    if analysis["business_keywords"]:
        updated["has_operating_assets"] = True
    updated["source_note"] = update_source_note(updated.get("source_note", ""), len(parsed_reports))

    if save_text and combined_text:
        text_dir = ROOT / "tl_ma_radar" / "data" / "dart_texts"
        text_dir.mkdir(parents=True, exist_ok=True)
        (text_dir / f"{row['code']}.txt").write_text(combined_text, encoding="utf-8")
        updated["report_analysis"]["text_file"] = f"dart_texts/{row['code']}.txt"
    return updated


def analyze(limit: int | None, max_reports: int, save_text: bool, include_pdfs: bool) -> None:
    rows = load_rows()
    output = []
    target_count = min(limit or len(rows), len(rows))
    for idx, row in enumerate(rows, start=1):
        if limit and idx > limit:
            output.append(row)
            continue
        print(f"[{idx}/{target_count}] {row.get('code')} {row.get('name')}")
        try:
            output.append(
                analyze_row(
                    row,
                    max_reports=max_reports,
                    save_text=save_text,
                    include_pdfs=include_pdfs,
                )
            )
        except Exception as exc:
            failed = dict(row)
            failed["report_analysis"] = {
                "status": "error",
                "message": str(exc),
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
            }
            output.append(failed)
    write_rows(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze downloaded DART report ZIPs for M&A signals.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-reports", type=int, default=3)
    parser.add_argument("--save-text", action="store_true")
    parser.add_argument("--include-pdfs", action="store_true", help="Also parse cached DART PDF files when present.")
    args = parser.parse_args()
    analyze(limit=args.limit, max_reports=args.max_reports, save_text=args.save_text, include_pdfs=args.include_pdfs)


if __name__ == "__main__":
    main()
