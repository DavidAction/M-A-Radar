from __future__ import annotations

import json
import mimetypes
import re
import sys
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse

from tl_ma_radar.acquisition_judgment import build_acquisition_judgment
from tl_ma_radar.ai_brief import build_ai_brief
from tl_ma_radar.automation_plan import build_automation_plan
from tl_ma_radar.candidate_workflow import load_workflows, update_workflow, workflow_for_code, workflow_options
from tl_ma_radar.collectors.dart import download_filing_pdf
from tl_ma_radar.config import get_settings
from tl_ma_radar.data_quality import build_data_quality, build_data_quality_summary
from tl_ma_radar.deal_report import build_deal_cards_docx
from tl_ma_radar.deal_scenario import build_deal_scenario
from tl_ma_radar.deal_signals import analyze_deal_signals
from tl_ma_radar.event_digest import build_event_digest
from tl_ma_radar.ic_package import build_ic_package, build_ic_package_summary
from tl_ma_radar.monitoring import latest_monitoring, monitoring_csv
from tl_ma_radar.news_analysis import load_news_cache, news_for_code
from tl_ma_radar.news_events import build_news_events
from tl_ma_radar.operations import operations_status
from tl_ma_radar.repository import data_source, load_candidates
from tl_ma_radar.report_intelligence import build_report_intelligence
from tl_ma_radar.scoring import score_candidate
from tl_ma_radar.score_audit import build_score_audit
from tl_ma_radar.score_tuning import build_score_tuning
from tl_ma_radar.shortlist import grouped_shortlist, shortlist_csv, shortlist_items
from tl_ma_radar.team_ops import build_pipeline_sqlite, team_ops_status


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"

if sys.stdout is None:
    sys.stdout = (ROOT / "server.out.log").open("a", encoding="utf-8", buffering=1)
if sys.stderr is None:
    sys.stderr = (ROOT / "server.err.log").open("a", encoding="utf-8", buffering=1)


def json_response(handler: BaseHTTPRequestHandler, payload: object, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    write_body(handler, body)


def write_body(handler: BaseHTTPRequestHandler, body: bytes) -> None:
    try:
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
        # Browsers may cancel in-flight API requests while the user navigates or refreshes.
        # Treat that as a normal client disconnect instead of polluting server logs.
        return


def read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, object]:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    body = handler.rfile.read(length)
    if not body:
        return {}
    payload = json.loads(body.decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def file_response(handler: BaseHTTPRequestHandler, path: Path) -> None:
    if not path.exists() or not path.is_file():
        handler.send_error(404, "Not found")
        return
    body = path.read_bytes()
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if content_type.startswith("text/") or path.suffix in {".js", ".css"}:
        content_type = f"{content_type}; charset=utf-8"
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    write_body(handler, body)


def bytes_response(
    handler: BaseHTTPRequestHandler,
    body: bytes,
    content_type: str,
    filename: str | None = None,
) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    if filename:
        ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("._") or "download"
        handler.send_header(
            "Content-Disposition",
            f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}",
        )
    handler.end_headers()
    write_body(handler, body)


def report_response(handler: BaseHTTPRequestHandler, relative_path: str) -> None:
    reports_root = (ROOT / "tl_ma_radar" / "data" / "dart_reports").resolve()
    candidate_path = (reports_root / relative_path.replace("\\", "/")).resolve()
    if reports_root not in candidate_path.parents and candidate_path != reports_root:
        handler.send_error(400, "Invalid report path")
        return
    file_response(handler, candidate_path)


def safe_download_name(value: str) -> str:
    normalized = re.sub(r"[\\/:*?\"<>|]+", "_", value)
    normalized = re.sub(r"\s+", "_", normalized.strip())
    return normalized[:90] or "report"


def report_pdf_download_url(receipt_no: str, report_name: str) -> str:
    return f"/api/download-report-pdf?{urlencode({'rcp_no': receipt_no, 'name': report_name})}"


def report_pdf_response(handler: BaseHTTPRequestHandler, receipt_no: str, report_name: str) -> None:
    if not re.fullmatch(r"\d{14}", receipt_no):
        handler.send_error(400, "Invalid DART receipt number")
        return
    pdf_root = (ROOT / "tl_ma_radar" / "data" / "dart_pdfs").resolve()
    safe_name = safe_download_name(report_name)
    candidate_path = (pdf_root / f"{receipt_no}_{safe_name}.pdf").resolve()
    if pdf_root not in candidate_path.parents and candidate_path != pdf_root:
        handler.send_error(400, "Invalid PDF path")
        return
    if not candidate_path.exists():
        download_filing_pdf(receipt_no, candidate_path)
    body = candidate_path.read_bytes()
    if not body.startswith(b"%PDF"):
        candidate_path.unlink(missing_ok=True)
        handler.send_error(502, "Cached DART file is not a PDF")
        return
    bytes_response(handler, body, "application/pdf", f"{safe_name}_{receipt_no}.pdf")


def memo_response(handler: BaseHTTPRequestHandler, relative_path: str) -> None:
    memos_root = (ROOT / "tl_ma_radar" / "data" / "deal_memos").resolve()
    safe_path = relative_path.replace("\\", "/").removeprefix("deal_memos/")
    candidate_path = (memos_root / safe_path).resolve()
    if memos_root not in candidate_path.parents and candidate_path != memos_root:
        handler.send_error(400, "Invalid memo path")
        return
    file_response(handler, candidate_path)


def load_filings(code: str) -> list[dict[str, object]]:
    path = ROOT / "tl_ma_radar" / "data" / "dart_filings" / f"{code}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_candidate(
    item: dict[str, object],
    settings: object,
    workflows: dict[str, dict[str, object]] | None = None,
    news_cache: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    prepared = dict(item)
    code = str(prepared.get("code", ""))
    prepared["news_analysis"] = news_for_code(news_cache or {}, code)
    prepared["news_events"] = build_news_events(prepared)
    filings = load_filings(str(prepared.get("code", "")))
    prepared["deal_signals"] = analyze_deal_signals(prepared, filings)
    prepared["event_digest"] = build_event_digest(filings)
    prepared["report_intelligence"] = build_report_intelligence(prepared, filings)
    dart = prepared.get("dart_enrichment")
    if isinstance(dart, dict) and isinstance(dart.get("periodic_reports"), list):
        for report in dart["periodic_reports"]:
            if not isinstance(report, dict):
                continue
            receipt_no = str(report.get("rcept_no") or report.get("rcp_no") or "")
            if receipt_no:
                report["pdf_download_url"] = report_pdf_download_url(
                    receipt_no,
                    str(report.get("report_nm") or receipt_no),
                )
    scored = score_candidate(prepared, settings)
    scored["acquisition_judgment"] = build_acquisition_judgment(scored)
    scored["workflow"] = workflow_for_code(workflows or {}, str(scored.get("code") or ""))
    scored["data_quality"] = build_data_quality(ROOT, scored, filings, scored["news_analysis"])
    scored["ic_package"] = build_ic_package(scored)
    scored["deal_scenario"] = build_deal_scenario(scored)
    scored["ai_brief"] = build_ai_brief(scored)
    shortlist_row = shortlist_items([scored])[0]
    scored["shortlist_score"] = shortlist_row["shortlist_score"]
    scored["priority_score"] = shortlist_row["priority_score"]
    scored["shortlist_group"] = shortlist_row["group"]
    return scored


def prepared_candidates(settings: object) -> list[dict[str, object]]:
    workflows = load_workflows(ROOT)
    news_cache = load_news_cache(ROOT)
    return [prepare_candidate(item, settings, workflows, news_cache) for item in load_candidates(ROOT)]


def pipeline_status() -> dict[str, object]:
    path = ROOT / "tl_ma_radar" / "data" / "pipeline_runs" / "latest.json"
    if not path.exists():
        return {"status": "not_run"}
    return json.loads(path.read_text(encoding="utf-8"))


class RadarHandler(BaseHTTPRequestHandler):
    server_version = "TLRadar/0.1"

    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/":
            file_response(self, STATIC_DIR / "index.html")
            return

        if path.startswith("/static/"):
            safe_name = path.removeprefix("/static/").replace("\\", "/")
            if ".." in safe_name:
                self.send_error(400, "Invalid static path")
                return
            file_response(self, STATIC_DIR / safe_name)
            return

        if path == "/api/config":
            settings = get_settings(ROOT)
            json_response(
                self,
                {
                    "target_market": settings.target_market,
                    "market_cap_limit_krw": settings.market_cap_limit_krw,
                    "capital_raise_krw": settings.capital_raise_krw,
                    "dart_configured": bool(settings.dart_api_key),
                    "naver_configured": bool(settings.naver_client_id and settings.naver_client_secret),
                    "data_source": data_source(ROOT),
                    "synergy_network": ["티엘홀딩스", "르네스머테리얼"],
                },
            )
            return

        if path == "/api/download-report":
            relative_path = (query.get("path", [""])[0] or "").strip()
            if not relative_path:
                self.send_error(400, "Missing report path")
                return
            report_response(self, relative_path)
            return

        if path == "/api/download-report-pdf":
            receipt_no = (
                query.get("rcp_no", [""])[0]
                or query.get("rcept_no", [""])[0]
                or query.get("receipt_no", [""])[0]
            ).strip()
            report_name = (query.get("name", ["report"])[0] or "report").strip()
            if not receipt_no:
                self.send_error(400, "Missing DART receipt number")
                return
            try:
                report_pdf_response(self, receipt_no, report_name)
            except (HTTPError, URLError, RuntimeError, TimeoutError, OSError) as exc:
                self.send_error(502, f"DART PDF download failed: {exc}")
            return

        if path == "/api/download-memo":
            relative_path = (query.get("path", [""])[0] or "").strip()
            if not relative_path:
                self.send_error(400, "Missing memo path")
                return
            memo_response(self, relative_path)
            return

        if path == "/api/shortlist":
            settings = get_settings(ROOT)
            json_response(self, grouped_shortlist(prepared_candidates(settings)))
            return

        if path == "/api/pipeline-status":
            json_response(self, pipeline_status())
            return

        if path == "/api/monitoring":
            json_response(self, latest_monitoring(ROOT))
            return

        if path == "/api/operations":
            json_response(self, operations_status(ROOT))
            return

        if path == "/api/automation-plan":
            json_response(self, build_automation_plan(ROOT))
            return

        if path == "/api/data-quality":
            settings = get_settings(ROOT)
            candidates = prepared_candidates(settings)
            json_response(self, build_data_quality_summary(candidates))
            return

        if path == "/api/team-ops":
            settings = get_settings(ROOT)
            candidates = prepared_candidates(settings)
            json_response(self, team_ops_status(ROOT, candidates))
            return

        if path == "/api/ic-packages":
            settings = get_settings(ROOT)
            limit_text = (query.get("limit", ["12"])[0] or "12").strip()
            try:
                limit = max(4, min(int(limit_text), 40))
            except ValueError:
                limit = 12
            json_response(self, build_ic_package_summary(prepared_candidates(settings), limit=limit))
            return

        if path == "/api/workflow-options":
            json_response(self, workflow_options())
            return

        if path == "/api/score-audit":
            settings = get_settings(ROOT)
            limit_text = (query.get("limit", ["20"])[0] or "20").strip()
            try:
                limit = max(1, min(int(limit_text), 50))
            except ValueError:
                limit = 20
            json_response(self, build_score_audit(prepared_candidates(settings), limit=limit))
            return

        if path == "/api/score-tuning":
            settings = get_settings(ROOT)
            limit_text = (query.get("limit", ["20"])[0] or "20").strip()
            try:
                limit = max(5, min(int(limit_text), 50))
            except ValueError:
                limit = 20
            json_response(self, build_score_tuning(prepared_candidates(settings), limit=limit))
            return

        if path == "/api/export-shortlist.csv":
            settings = get_settings(ROOT)
            body = shortlist_csv(prepared_candidates(settings))
            bytes_response(self, body, "text/csv; charset=utf-8", "tl_ma_radar_shortlist.csv")
            return

        if path == "/api/export-monitoring.csv":
            body = monitoring_csv(latest_monitoring(ROOT))
            bytes_response(self, body, "text/csv; charset=utf-8", "tl_ma_radar_monitoring.csv")
            return

        if path == "/api/export-pipeline.sqlite":
            settings = get_settings(ROOT)
            body = build_pipeline_sqlite(prepared_candidates(settings))
            bytes_response(self, body, "application/vnd.sqlite3", "tl_ma_radar_pipeline.sqlite")
            return

        if path == "/api/export-deal-cards.docx":
            settings = get_settings(ROOT)
            candidates = prepared_candidates(settings)
            candidates.sort(
                key=lambda item: (
                    -(float(item.get("priority_score") or item.get("shortlist_score") or item["scores"]["total"])),
                    str(item.get("name") or ""),
                )
            )
            report_format = (query.get("format", ["ic"])[0] or "ic").strip().lower()
            body = build_deal_cards_docx(candidates, report_format=report_format)
            bytes_response(
                self,
                body,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "TL_Holdings_MA_Deal_Cards.docx",
            )
            return

        if path == "/api/candidates":
            settings = get_settings(ROOT)
            candidates = prepared_candidates(settings)
            keyword = (query.get("q", [""])[0] or "").strip().lower()
            if keyword:
                candidates = [
                    item
                    for item in candidates
                    if keyword in item["name"].lower()
                    or keyword in item["code"].lower()
                    or keyword in " ".join(item.get("business_keywords", [])).lower()
                ]
            candidates.sort(key=lambda item: item["scores"]["total"], reverse=True)
            json_response(self, {"items": candidates, "count": len(candidates)})
            return

        if path.startswith("/api/candidates/") and path.endswith("/deal-card.docx"):
            code = path.removeprefix("/api/candidates/").removesuffix("/deal-card.docx").strip("/")
            if not re.fullmatch(r"\d{6}", code):
                self.send_error(400, "Invalid candidate code")
                return
            settings = get_settings(ROOT)
            workflows = load_workflows(ROOT)
            news_cache = load_news_cache(ROOT)
            for item in load_candidates(ROOT):
                if str(item.get("code")) == code:
                    candidate = prepare_candidate(item, settings, workflows, news_cache)
                    report_format = (query.get("format", ["ic"])[0] or "ic").strip().lower()
                    body = build_deal_cards_docx(
                        [candidate],
                        title=f"{candidate.get('name', code)} Deal Card Report",
                        report_format=report_format,
                    )
                    bytes_response(
                        self,
                        body,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        f"{safe_download_name(str(candidate.get('name') or code))}_{code}_Deal_Card.docx",
                    )
                    return
            self.send_error(404, "Candidate not found")
            return

        if path.startswith("/api/candidates/"):
            code = path.removeprefix("/api/candidates/").strip()
            if "/" in code:
                self.send_error(404, "Candidate not found")
                return
            settings = get_settings(ROOT)
            workflows = load_workflows(ROOT)
            news_cache = load_news_cache(ROOT)
            for item in load_candidates(ROOT):
                if item["code"] == code:
                    json_response(self, prepare_candidate(item, settings, workflows, news_cache))
                    return
            self.send_error(404, "Candidate not found")
            return

        self.send_error(404, "Not found")

    def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/candidates/") and path.endswith("/workflow"):
            code = path.removeprefix("/api/candidates/").removesuffix("/workflow").strip("/")
            if not re.fullmatch(r"\d{6}", code):
                self.send_error(400, "Invalid candidate code")
                return
            if not any(str(item.get("code")) == code for item in load_candidates(ROOT)):
                self.send_error(404, "Candidate not found")
                return
            try:
                payload = read_json_body(self)
                workflow = update_workflow(ROOT, code, payload)
            except json.JSONDecodeError:
                self.send_error(400, "Invalid JSON body")
                return
            json_response(self, {"status": "ok", "code": code, "workflow": workflow})
            return

        self.send_error(404, "Not found")

    def log_message(self, fmt: str, *args: object) -> None:
        if sys.stdout:
            print(f"{self.address_string()} - {fmt % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TL M&A Radar.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    host = args.host
    port = args.port
    server = ThreadingHTTPServer((host, port), RadarHandler)
    if sys.stdout:
        print(f"TL M&A Radar running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
