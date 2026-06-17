from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tl_ma_radar.collectors.dart import DartClient  # noqa: E402
from tl_ma_radar.config import get_settings  # noqa: E402


PERIODIC_REPORT_KEYWORDS = (
    "사업보고서",
    "분기보고서",
    "반기보고서",
    "감사보고서",
    "연결감사보고서",
)


def parse_amount(value: str | None) -> int | None:
    if not value:
        return None
    text = str(value).replace(",", "").strip()
    if not text or text == "-":
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def safe_filename(value: str) -> str:
    normalized = re.sub(r"[\\/:*?\"<>|]+", "_", value)
    normalized = re.sub(r"\s+", "_", normalized.strip())
    return normalized[:90] or "report"


def load_candidates() -> list[dict[str, Any]]:
    path = ROOT / "tl_ma_radar" / "data" / "real_candidates.json"
    if not path.exists():
        raise FileNotFoundError("real_candidates.json is missing. Run scripts/refresh_candidates.py first.")
    return json.loads(path.read_text(encoding="utf-8"))


def write_candidates(rows: list[dict[str, Any]]) -> None:
    path = ROOT / "tl_ma_radar" / "data" / "real_candidates.json"
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def load_stock_map(client: DartClient) -> dict[str, str]:
    return {row["stock_code"]: row["corp_code"] for row in client.corp_codes() if row.get("stock_code")}


def report_category(report_name: str) -> str | None:
    if "연결감사보고서" in report_name:
        return "연결감사보고서"
    if "감사보고서" in report_name:
        return "감사보고서"
    if "사업보고서" in report_name:
        return "사업보고서"
    if "반기보고서" in report_name:
        return "반기보고서"
    if "분기보고서" in report_name:
        return "분기보고서"
    return None


def select_periodic_reports(filings: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    periodic = [filing for filing in filings if report_category(filing.get("report_nm", ""))]
    if mode == "none":
        return periodic
    if mode == "all":
        return periodic
    latest_by_type: dict[str, dict[str, Any]] = {}
    for filing in periodic:
        category = report_category(filing.get("report_nm", ""))
        if category and category not in latest_by_type:
            latest_by_type[category] = filing
    return list(latest_by_type.values())


def infer_flags(filings: list[dict[str, Any]]) -> list[str]:
    text = " ".join(filing.get("report_nm", "") for filing in filings)
    checks = [
        ("유상증자", "유상증자공시"),
        ("감자", "감자공시"),
        ("전환사채", "CB/BW공시"),
        ("신주인수권부사채", "CB/BW공시"),
        ("최대주주변경", "최대주주변경"),
        ("최대주주 변경", "최대주주변경"),
        ("불성실공시", "불성실공시"),
        ("주권매매거래정지", "거래정지"),
        ("회생절차", "회생절차"),
        ("파산신청", "파산신청"),
        ("상장폐지", "상장폐지위험"),
        ("관리종목", "관리종목"),
        ("투자주의환기", "투자주의환기"),
    ]
    flags = []
    for needle, flag in checks:
        if needle in text and flag not in flags:
            flags.append(flag)
    return flags


def financial_candidates(today: date) -> list[tuple[str, str]]:
    year = today.year
    pairs: list[tuple[str, str]] = []
    if today >= date(year, 11, 15):
        pairs.append((str(year), "11014"))
    if today >= date(year, 8, 15):
        pairs.append((str(year), "11012"))
    if today >= date(year, 5, 15):
        pairs.append((str(year), "11013"))
    pairs.extend(
        [
            (str(year - 1), "11011"),
            (str(year - 1), "11014"),
            (str(year - 1), "11012"),
            (str(year - 1), "11013"),
        ]
    )
    return pairs


def choose_financial_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cfs = [row for row in rows if row.get("fs_div") == "CFS"]
    if cfs:
        return cfs
    ofs = [row for row in rows if row.get("fs_div") == "OFS"]
    return ofs or rows


def fetch_latest_financials(client: DartClient, corp_code: str) -> dict[str, Any]:
    for business_year, report_code in financial_candidates(date.today()):
        payload = client.financial_summary(corp_code, business_year, report_code)
        if payload.get("status") == "013":
            continue
        if payload.get("status") and payload.get("status") != "000":
            continue
        rows = choose_financial_rows(payload.get("list") or [])
        if not rows:
            continue
        result: dict[str, Any] = {
            "business_year": business_year,
            "report_code": report_code,
            "fs_div": rows[0].get("fs_div"),
        }
        account_map = {
            "revenue_krw": ("매출액", "영업수익", "수익(매출액)"),
            "operating_profit_krw": ("영업이익",),
            "net_income_krw": ("당기순이익", "분기순이익", "반기순이익"),
            "assets_krw": ("자산총계",),
            "debt_krw": ("부채총계",),
            "equity_krw": ("자본총계",),
        }
        for field, account_names in account_map.items():
            for row in rows:
                if row.get("account_nm") in account_names:
                    amount = parse_amount(row.get("thstrm_amount"))
                    if amount is not None:
                        result[field] = amount
                        break
        return result
    return {}


def report_download_url(relative_path: str) -> str:
    return f"/api/download-report?path={relative_path}"


def report_pdf_download_url(receipt_no: str, report_name: str) -> str:
    return f"/api/download-report-pdf?{urlencode({'rcp_no': receipt_no, 'name': report_name})}"


def download_reports(
    client: DartClient,
    candidate: dict[str, Any],
    reports: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    stock_code = candidate["code"]
    company_name = safe_filename(candidate["name"])
    company_dir = ROOT / "tl_ma_radar" / "data" / "dart_reports" / f"{stock_code}_{company_name}"
    enriched_reports = []
    for report in reports:
        report_name = report.get("report_nm", "report")
        receipt_no = report.get("rcept_no")
        receipt_date = report.get("rcept_dt", "")
        if not receipt_no:
            continue
        filename = f"{receipt_date}_{receipt_no}_{safe_filename(report_name)}.zip"
        output_path = company_dir / filename
        copied = dict(report)
        copied["pdf_download_url"] = report_pdf_download_url(receipt_no, report_name)
        try:
            if not output_path.exists():
                client.download_document(receipt_no, output_path)
            relative = output_path.relative_to(ROOT / "tl_ma_radar" / "data" / "dart_reports").as_posix()
            copied["local_path"] = relative
            copied["download_url"] = report_download_url(relative)
        except (HTTPError, URLError, RuntimeError, TimeoutError) as exc:
            copied["download_error"] = str(exc)
        enriched_reports.append(copied)
    return enriched_reports


def enrich_one(
    client: DartClient,
    candidate: dict[str, Any],
    stock_map: dict[str, str],
    begin_date: str,
    end_date: str,
    download_mode: str,
) -> dict[str, Any]:
    row = dict(candidate)
    corp_code = row.get("dart_corp_code") or stock_map.get(row.get("code", ""))
    if not corp_code:
        row["dart_enrichment"] = {
            "status": "no_corp_code",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        return row

    row["dart_corp_code"] = corp_code
    filings = client.filings_all(corp_code, begin_date, end_date)
    filings_dir = ROOT / "tl_ma_radar" / "data" / "dart_filings"
    filings_dir.mkdir(parents=True, exist_ok=True)
    (filings_dir / f"{row['code']}.json").write_text(
        json.dumps(filings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    financials = fetch_latest_financials(client, corp_code)
    for field in ("revenue_krw", "operating_profit_krw", "debt_krw", "equity_krw"):
        if financials.get(field) is not None:
            row[field] = financials[field]

    flags = list(dict.fromkeys([*(row.get("status_flags") or []), *infer_flags(filings)]))
    row["status_flags"] = flags

    periodic_all = [filing for filing in filings if report_category(filing.get("report_nm", ""))]
    selected_reports = select_periodic_reports(filings, download_mode)
    periodic_reports = download_reports(client, row, selected_reports) if download_mode != "none" else selected_reports

    row["dart_enrichment"] = {
        "status": "ok",
        "corp_code": corp_code,
        "begin_date": begin_date,
        "end_date": end_date,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "filing_count": len(filings),
        "latest_filing": filings[0] if filings else None,
        "periodic_report_count": len(periodic_all),
        "periodic_reports": periodic_reports,
        "financials": financials,
    }
    row["source_note"] = f"{row.get('source_note', '')} / DART {begin_date}-{end_date} 전체 공시 {len(filings)}건 보강"
    return row


def enrich(begin_date: str, end_date: str, limit: int | None, download_mode: str, sleep_seconds: float) -> None:
    settings = get_settings(ROOT)
    if not settings.dart_api_key:
        raise ValueError("DART_API_KEY is missing")
    client = DartClient(settings.dart_api_key, timeout=30)
    stock_map = load_stock_map(client)
    rows = load_candidates()
    target_count = min(limit or len(rows), len(rows))
    enriched_rows: list[dict[str, Any]] = []
    for idx, candidate in enumerate(rows, start=1):
        if limit and idx > limit:
            enriched_rows.append(candidate)
            continue
        print(f"[{idx}/{target_count}] {candidate.get('code')} {candidate.get('name')}")
        try:
            enriched_rows.append(
                enrich_one(client, candidate, stock_map, begin_date, end_date, download_mode)
            )
        except Exception as exc:  # keep the batch moving; record the issue in-row
            failed = dict(candidate)
            failed["dart_enrichment"] = {
                "status": "error",
                "message": str(exc),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
            enriched_rows.append(failed)
        time.sleep(sleep_seconds)
    write_candidates(enriched_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich candidate rows with DART filings and report downloads.")
    parser.add_argument("--begin", default="20240101", help="DART begin date YYYYMMDD")
    parser.add_argument("--end", default=date.today().strftime("%Y%m%d"), help="DART end date YYYYMMDD")
    parser.add_argument("--limit", type=int, default=None, help="Optional row limit for testing")
    parser.add_argument(
        "--download-reports",
        choices=["none", "latest", "all"],
        default="latest",
        help="Download no reports, latest report per type, or all periodic reports in range.",
    )
    parser.add_argument("--sleep", type=float, default=0.15, help="Seconds between companies")
    args = parser.parse_args()
    enrich(args.begin, args.end, args.limit, args.download_reports, args.sleep)


if __name__ == "__main__":
    main()
