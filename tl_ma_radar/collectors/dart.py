from __future__ import annotations

import json
import re
import zipfile
from html import unescape
from http.cookiejar import CookieJar
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen
from xml.etree import ElementTree


BASE_URL = "https://opendart.fss.or.kr/api"
DART_VIEWER_URL = "https://dart.fss.or.kr"


def _decode_html(body: bytes) -> str:
    for encoding in ("utf-8", "euc-kr", "cp949"):
        try:
            return body.decode(encoding)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", errors="replace")


def _extract_dcm_no(html: str, receipt_no: str) -> str:
    patterns = [
        rf"openPdfDownload\(\s*['\"]{re.escape(receipt_no)}['\"]\s*,\s*['\"](\d+)['\"]",
        rf"node\d+\[['\"]dcmNo['\"]\]\s*=\s*['\"](\d+)['\"]",
        rf"download/pdf\.do\?rcp_no={re.escape(receipt_no)}&dcm_no=(\d+)",
        r"dcmNo\s*[=:]\s*['\"]?(\d+)",
        r"viewDoc\(\s*['\"]\d+['\"]\s*,\s*['\"](\d+)['\"]",
        r"viewDoc\(\s*['\"]\d+['\"]\s*,\s*['\"]\d+['\"]\s*,\s*['\"](\d+)['\"]",
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    raise RuntimeError("DART PDF document number could not be resolved")


def _extract_pdf_path(html: str, receipt_no: str, dcm_no: str) -> str:
    patterns = [
        rf"href=['\"]([^'\"]*/pdf/download/pdf\.do\?rcp_no={re.escape(receipt_no)}&dcm_no={re.escape(dcm_no)}[^'\"]*)",
        rf"href=['\"]([^'\"]*download/pdf\.do\?rcp_no={re.escape(receipt_no)}&dcm_no={re.escape(dcm_no)}[^'\"]*)",
        rf"(/pdf/download/pdf\.do\?rcp_no={re.escape(receipt_no)}&dcm_no={re.escape(dcm_no)}[^<\s'\"]*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return unescape(match.group(1))
    return f"/pdf/download/pdf.do?{urlencode({'rcp_no': receipt_no, 'dcm_no': dcm_no})}"


def download_filing_pdf(receipt_no: str, output_path: Path, timeout: int = 30) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    main_url = f"{DART_VIEWER_URL}/dsaf001/main.do?{urlencode({'rcpNo': receipt_no})}"
    main_req = Request(main_url, headers={"User-Agent": "TL-MA-Radar/0.1"})
    with opener.open(main_req, timeout=timeout) as response:
        html = _decode_html(response.read())

    dcm_no = _extract_dcm_no(html, receipt_no)
    popup_url = f"{DART_VIEWER_URL}/pdf/download/main.do?{urlencode({'rcp_no': receipt_no, 'dcm_no': dcm_no})}"
    popup_req = Request(
        popup_url,
        headers={
            "User-Agent": "TL-MA-Radar/0.1",
            "Referer": main_url,
        },
    )
    with opener.open(popup_req, timeout=timeout) as response:
        popup_html = _decode_html(response.read())

    pdf_url = urljoin(DART_VIEWER_URL, _extract_pdf_path(popup_html, receipt_no, dcm_no))
    pdf_req = Request(
        pdf_url,
        headers={
            "User-Agent": "TL-MA-Radar/0.1",
            "Referer": popup_url,
        },
    )
    with opener.open(pdf_req, timeout=timeout) as response:
        body = response.read()
    if not body.startswith(b"%PDF"):
        raise RuntimeError("DART PDF download did not return a PDF file")
    output_path.write_bytes(body)
    return output_path


class DartClient:
    def __init__(self, api_key: str, timeout: int = 20) -> None:
        self.api_key = api_key
        self.timeout = timeout

    def _get_json(self, endpoint: str, params: dict[str, str]) -> dict:
        if not self.api_key:
            raise ValueError("DART API key is not configured")
        payload = {"crtfc_key": self.api_key, **params}
        url = f"{BASE_URL}/{endpoint}?{urlencode(payload)}"
        req = Request(url, headers={"User-Agent": "TL-MA-Radar/0.1"})
        with urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def company(self, corp_code: str) -> dict:
        return self._get_json("company.json", {"corp_code": corp_code})

    def filings(self, corp_code: str, begin_date: str, end_date: str) -> dict:
        return self._get_json(
            "list.json",
            {
                "corp_code": corp_code,
                "bgn_de": begin_date,
                "end_de": end_date,
                "page_no": "1",
                "page_count": "100",
            },
        )

    def filings_all(
        self,
        corp_code: str,
        begin_date: str,
        end_date: str,
        pblntf_ty: str | None = None,
        page_count: int = 100,
    ) -> list[dict]:
        rows: list[dict] = []
        page_no = 1
        while True:
            params = {
                "corp_code": corp_code,
                "bgn_de": begin_date,
                "end_de": end_date,
                "page_no": str(page_no),
                "page_count": str(page_count),
                "sort": "date",
                "sort_mth": "desc",
                "last_reprt_at": "N",
            }
            if pblntf_ty:
                params["pblntf_ty"] = pblntf_ty
            payload = self._get_json("list.json", params)
            status = payload.get("status")
            if status == "013":
                return rows
            if status and status != "000":
                raise RuntimeError(f"DART filings error {status}: {payload.get('message')}")
            batch = payload.get("list") or []
            rows.extend(batch)
            total_count = int(payload.get("total_count") or len(rows))
            if len(rows) >= total_count or not batch:
                return rows
            page_no += 1

    def financial_summary(self, corp_code: str, business_year: str, report_code: str = "11011") -> dict:
        return self._get_json(
            "fnlttSinglAcnt.json",
            {
                "corp_code": corp_code,
                "bsns_year": business_year,
                "reprt_code": report_code,
            },
        )

    def download_document(self, receipt_no: str, output_path: Path) -> Path:
        if not self.api_key:
            raise ValueError("DART API key is not configured")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"{BASE_URL}/document.xml?{urlencode({'crtfc_key': self.api_key, 'rcept_no': receipt_no})}"
        req = Request(url, headers={"User-Agent": "TL-MA-Radar/0.1"})
        with urlopen(req, timeout=self.timeout) as response:
            body = response.read()
        if body.startswith(b"{"):
            payload = json.loads(body.decode("utf-8", errors="replace"))
            raise RuntimeError(f"DART document error {payload.get('status')}: {payload.get('message')}")
        output_path.write_bytes(body)
        return output_path

    def corp_codes(self) -> list[dict[str, str]]:
        if not self.api_key:
            raise ValueError("DART API key is not configured")
        url = f"{BASE_URL}/corpCode.xml?{urlencode({'crtfc_key': self.api_key})}"
        req = Request(url, headers={"User-Agent": "TL-MA-Radar/0.1"})
        with urlopen(req, timeout=self.timeout) as response:
            zipped = zipfile.ZipFile(BytesIO(response.read()))
        xml_data = zipped.read(zipped.namelist()[0])
        root = ElementTree.fromstring(xml_data)
        rows = []
        for item in root.findall("list"):
            rows.append(
                {
                    "corp_code": item.findtext("corp_code", ""),
                    "corp_name": item.findtext("corp_name", ""),
                    "stock_code": item.findtext("stock_code", ""),
                    "modify_date": item.findtext("modify_date", ""),
                }
            )
        return rows
