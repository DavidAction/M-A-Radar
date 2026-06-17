from __future__ import annotations

from datetime import datetime
from html import escape
from io import BytesIO
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile


PAGE_WIDTH_DXA = 12240
PAGE_HEIGHT_DXA = 15840
MARGIN_DXA = 1440
BODY_WIDTH_DXA = PAGE_WIDTH_DXA - (MARGIN_DXA * 2)
FONT_ASCII = "Calibri"
FONT_EAST_ASIA = "Malgun Gothic"


def _xml(value: object) -> str:
    text = str(value if value is not None else "")
    text = " ".join(text.replace("\r", " ").replace("\n", " ").split())
    return escape(text, quote=True)


def _clip(value: object, limit: int = 280) -> str:
    text = " ".join(str(value if value is not None else "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _fmt_won(value: object) -> str:
    if value is None:
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if abs(number) >= 100_000_000:
        return f"{number / 100_000_000:,.1f}억"
    return f"{number:,.0f}원"


def _fmt_pct(value: object) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "-"


def _fmt_score(value: object) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return str(value)


def _join(values: list[Any] | tuple[Any, ...] | None, limit: int = 4, empty: str = "-") -> str:
    clean = [str(value) for value in (values or []) if value]
    if not clean:
        return empty
    shown = clean[:limit]
    suffix = f" 외 {len(clean) - limit}" if len(clean) > limit else ""
    return ", ".join(shown) + suffix


def _news(item: dict[str, Any]) -> dict[str, Any]:
    news = item.get("news_analysis")
    return news if isinstance(news, dict) else {}


def _analysis(item: dict[str, Any]) -> dict[str, Any]:
    analysis = item.get("report_analysis")
    return analysis if isinstance(analysis, dict) else {}


def _signals(item: dict[str, Any]) -> dict[str, Any]:
    signals = item.get("deal_signals")
    return signals if isinstance(signals, dict) else {}


def _judgment(item: dict[str, Any]) -> dict[str, Any]:
    judgment = item.get("acquisition_judgment")
    return judgment if isinstance(judgment, dict) else {}


class Docx:
    def __init__(self) -> None:
        self.blocks: list[str] = []

    def paragraph(
        self,
        text: object = "",
        *,
        style: str | None = None,
        color: str | None = None,
        bold: bool = False,
        size: int | None = None,
        align: str | None = None,
        before: int | None = None,
        after: int | None = None,
    ) -> None:
        p_pr = []
        if style:
            p_pr.append(f'<w:pStyle w:val="{style}"/>')
        if align:
            p_pr.append(f'<w:jc w:val="{align}"/>')
        spacing = []
        if before is not None:
            spacing.append(f'w:before="{before}"')
        if after is not None:
            spacing.append(f'w:after="{after}"')
        if spacing:
            p_pr.append(f'<w:spacing {" ".join(spacing)}/>')
        r_pr = [
            f'<w:rFonts w:ascii="{FONT_ASCII}" w:hAnsi="{FONT_ASCII}" w:eastAsia="{FONT_EAST_ASIA}" w:cs="{FONT_ASCII}"/>'
        ]
        if bold:
            r_pr.append("<w:b/>")
        if color:
            r_pr.append(f'<w:color w:val="{color}"/>')
        if size:
            r_pr.append(f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>')
        self.blocks.append(
            "<w:p>"
            + (f"<w:pPr>{''.join(p_pr)}</w:pPr>" if p_pr else "")
            + f"<w:r><w:rPr>{''.join(r_pr)}</w:rPr><w:t xml:space=\"preserve\">{_xml(text)}</w:t></w:r>"
            + "</w:p>"
        )

    def bullet(self, text: object) -> None:
        r_fonts = (
            f'<w:rFonts w:ascii="{FONT_ASCII}" w:hAnsi="{FONT_ASCII}" '
            f'w:eastAsia="{FONT_EAST_ASIA}" w:cs="{FONT_ASCII}"/>'
        )
        self.blocks.append(
            "<w:p>"
            "<w:pPr>"
            '<w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr>'
            '<w:spacing w:after="160" w:line="280" w:lineRule="auto"/>'
            '<w:ind w:left="720" w:hanging="360"/>'
            "</w:pPr>"
            f"<w:r><w:rPr>{r_fonts}<w:sz w:val=\"20\"/><w:szCs w:val=\"20\"/></w:rPr>"
            f'<w:t xml:space="preserve">{_xml(_clip(text, 260))}</w:t></w:r>'
            "</w:p>"
        )

    def page_break(self) -> None:
        self.blocks.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

    def table(
        self,
        rows: list[list[object]],
        *,
        widths: list[int] | None = None,
        header: bool = True,
        compact: bool = False,
    ) -> None:
        if not rows:
            return
        column_count = max(len(row) for row in rows)
        if widths is None:
            widths = [BODY_WIDTH_DXA // column_count] * column_count
        grid = "".join(f'<w:gridCol w:w="{width}"/>' for width in widths)
        body_rows = []
        for row_index, row in enumerate(rows):
            cells = []
            for col_index in range(column_count):
                text = row[col_index] if col_index < len(row) else ""
                width = widths[col_index] if col_index < len(widths) else widths[-1]
                fill = "13232E" if header and row_index == 0 else "FFFFFF"
                color = "FFFFFF" if header and row_index == 0 else "1F2937"
                bold = header and row_index == 0
                font_size = 17 if compact else 18
                cells.append(
                    "<w:tc>"
                    f'<w:tcPr><w:tcW w:w="{width}" w:type="dxa"/><w:shd w:fill="{fill}"/>'
                    '<w:tcMar><w:top w:w="110" w:type="dxa"/><w:left w:w="110" w:type="dxa"/>'
                    '<w:bottom w:w="110" w:type="dxa"/><w:right w:w="110" w:type="dxa"/></w:tcMar>'
                    "</w:tcPr>"
                    "<w:p><w:pPr><w:spacing w:after=\"40\"/></w:pPr>"
                    "<w:r><w:rPr>"
                    f'<w:rFonts w:ascii="{FONT_ASCII}" w:hAnsi="{FONT_ASCII}" w:eastAsia="{FONT_EAST_ASIA}" w:cs="{FONT_ASCII}"/>'
                    + ("<w:b/>" if bold else "")
                    + f'<w:color w:val="{color}"/><w:sz w:val="{font_size}"/><w:szCs w:val="{font_size}"/>'
                    f'</w:rPr><w:t xml:space="preserve">{_xml(_clip(text, 420))}</w:t></w:r></w:p>'
                    "</w:tc>"
                )
            body_rows.append("<w:tr>" + "".join(cells) + "</w:tr>")
        self.blocks.append(
            "<w:tbl>"
            "<w:tblPr>"
            f'<w:tblW w:w="{BODY_WIDTH_DXA}" w:type="dxa"/>'
            '<w:tblInd w:w="120" w:type="dxa"/>'
            '<w:tblBorders><w:top w:val="single" w:sz="4" w:color="D8DEE9"/>'
            '<w:left w:val="single" w:sz="4" w:color="D8DEE9"/>'
            '<w:bottom w:val="single" w:sz="4" w:color="D8DEE9"/>'
            '<w:right w:val="single" w:sz="4" w:color="D8DEE9"/>'
            '<w:insideH w:val="single" w:sz="4" w:color="E5E7EB"/>'
            '<w:insideV w:val="single" w:sz="4" w:color="E5E7EB"/></w:tblBorders>'
            '<w:tblCellMar><w:top w:w="80" w:type="dxa"/><w:left w:w="80" w:type="dxa"/>'
            '<w:bottom w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar>'
            "</w:tblPr>"
            f"<w:tblGrid>{grid}</w:tblGrid>"
            + "".join(body_rows)
            + "</w:tbl>"
        )

    def build(self) -> bytes:
        document_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" '
            'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
            'xmlns:o="urn:schemas-microsoft-com:office:office" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
            'xmlns:v="urn:schemas-microsoft-com:vml" '
            'xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" '
            'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
            'xmlns:w10="urn:schemas-microsoft-com:office:word" '
            'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
            'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" '
            'xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk" '
            'xmlns:wne="http://schemas.microsoft.com/office/word/2006/wordml" '
            'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
            'mc:Ignorable="w14 wp14">'
            "<w:body>"
            + "".join(self.blocks)
            + f'<w:sectPr><w:pgSz w:w="{PAGE_WIDTH_DXA}" w:h="{PAGE_HEIGHT_DXA}"/>'
            f'<w:pgMar w:top="{MARGIN_DXA}" w:right="{MARGIN_DXA}" w:bottom="{MARGIN_DXA}" w:left="{MARGIN_DXA}" '
            'w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
            "</w:body></w:document>"
        )
        buffer = BytesIO()
        with ZipFile(buffer, "w", ZIP_DEFLATED) as docx:
            docx.writestr("[Content_Types].xml", CONTENT_TYPES)
            docx.writestr("_rels/.rels", ROOT_RELS)
            docx.writestr("docProps/core.xml", CORE_PROPS)
            docx.writestr("docProps/app.xml", APP_PROPS)
            docx.writestr("word/_rels/document.xml.rels", DOCUMENT_RELS)
            docx.writestr("word/styles.xml", STYLES_XML)
            docx.writestr("word/numbering.xml", NUMBERING_XML)
            docx.writestr("word/settings.xml", SETTINGS_XML)
            docx.writestr("word/document.xml", document_xml)
        return buffer.getvalue()


def _summary_table(candidates: list[dict[str, Any]]) -> list[list[object]]:
    rows: list[list[object]] = [["Rank", "회사", "점수", "판단", "시총", "딜 실행 창", "핵심 논거"]]
    for index, item in enumerate(candidates[:30], 1):
        signals = _signals(item)
        rows.append(
            [
                index,
                f"{item.get('name', '-')} ({item.get('code', '-')})",
                _fmt_score(item.get("shortlist_score") or (item.get("scores") or {}).get("total")),
                item.get("recommendation") or "-",
                _fmt_won(item.get("market_cap_krw")),
                signals.get("deal_window") or "-",
                _clip(item.get("deal_thesis") or (_judgment(item).get("summary") or "-"), 120),
            ]
        )
    return rows


def _candidate_section(doc: Docx, item: dict[str, Any], index: int) -> None:
    scores = item.get("scores") or {}
    analysis = _analysis(item)
    signals = _signals(item)
    signal_scores = signals.get("scores") or {}
    judgment = _judgment(item)
    cap_case = item.get("capital_raise_case") or {}
    news = _news(item)
    shareholder = analysis.get("largest_shareholder") or {}
    shareholder_text = (
        f"{shareholder.get('name', '-')}, {_fmt_pct(shareholder.get('ratio'))}" if shareholder else "-"
    )

    doc.paragraph(
        f"{index:03d}. {item.get('name', '-')} ({item.get('code', '-')})",
        style="Heading1",
        color="13232E",
        bold=True,
        size=28,
        before=240,
        after=120,
    )
    doc.paragraph(
        _clip(judgment.get("summary") or item.get("deal_thesis") or "자동 분석 요약이 필요합니다.", 420),
        style="BodyLead",
        color="374151",
        size=20,
        after=160,
    )
    doc.table(
        [
            ["항목", "값", "항목", "값"],
            ["숏리스트 점수", _fmt_score(item.get("shortlist_score") or scores.get("total")), "판단", item.get("recommendation") or "-"],
            ["시가총액", _fmt_won(item.get("market_cap_krw")), "매출", _fmt_won(item.get("revenue_krw"))],
            ["영업손익", _fmt_won(item.get("operating_profit_krw")), "유증 후 신규지분", _fmt_pct(cap_case.get("implied_new_share_ratio"))],
            ["최대주주", shareholder_text, "딜 실행 창", signals.get("deal_window") or "-"],
            ["백기사 필요도", signals.get("white_knight_need") or "-", "딜 실행 가능성", _fmt_score(signal_scores.get("deal_execution_score"))],
        ],
        widths=[2100, 2580, 2100, 2580],
        compact=True,
    )
    doc.paragraph("투자 논거", style="Heading2", color="0F766E", bold=True, size=24, before=220, after=80)
    for point in (judgment.get("fit_points") or [])[:5]:
        doc.bullet(point)
    if not (judgment.get("fit_points") or []):
        doc.bullet(item.get("deal_thesis") or "추가 투자 논거 확인 필요")

    doc.paragraph("리스크 및 확인 사항", style="Heading2", color="B42318", bold=True, size=24, before=160, after=80)
    for risk in (judgment.get("blockers") or [])[:5]:
        doc.bullet(risk)

    doc.paragraph("보고서/뉴스 근거", style="Heading2", color="13232E", bold=True, size=24, before=160, after=80)
    doc.table(
        [
            ["구분", "핵심 내용"],
            ["사업 키워드", _join(analysis.get("business_keywords"), 6)],
            ["감사/회계 신호", _join(analysis.get("audit_signals"), 5)],
            ["자금조달 신호", _join(analysis.get("financing_signals"), 5)],
            ["경영권/지분 신호", _join(analysis.get("control_signals"), 5)],
            ["뉴스 톤", f"{news.get('tone') or '미수집'} / 기사 {news.get('article_count', 0)}건"],
            ["최신 공시", ((item.get("dart_enrichment") or {}).get("latest_filing") or {}).get("report_nm") or "-"],
        ],
        widths=[2200, 7160],
        compact=True,
    )

    articles = news.get("articles") or []
    if articles:
        doc.paragraph("최근 뉴스 헤드라인", style="Heading3", color="13232E", bold=True, size=21, before=140, after=70)
        for article in articles[:3]:
            doc.bullet(f"{article.get('published_at', '-')[:10]} | {article.get('title', '-')}")

    doc.paragraph("실사 질문", style="Heading2", color="13232E", bold=True, size=24, before=160, after=80)
    focus = judgment.get("diligence_focus") or item.get("key_diligence") or []
    for question in focus[:6]:
        doc.bullet(question)


def build_deal_cards_docx(candidates: list[dict[str, Any]], *, title: str = "TL Holdings M&A Deal Card Report") -> bytes:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    ordered = sorted(
        candidates,
        key=lambda item: (
            -(float(item.get("priority_score") or item.get("shortlist_score") or (item.get("scores") or {}).get("total") or 0)),
            item.get("name") or "",
        ),
    )
    doc = Docx()
    doc.paragraph(title, style="Title", color="13232E", bold=True, size=40, after=120)
    doc.paragraph("KOSDAQ sub-30B market-cap target screening and acquisition execution brief", color="0F766E", size=22, after=180)
    doc.paragraph(
        f"Prepared for TL Holdings | Generated {generated_at} | Candidates {len(ordered)}",
        color="6B7280",
        size=19,
        after=360,
    )
    doc.paragraph(
        "본 문서는 TL홀딩스와 르네스머테리얼의 1단계 핵심 시너지 네트워크를 기준으로 저평가 상장사, 경영권 협상 가능성, "
        "백기사 필요도, 300억 유상증자 후 구조 활용 가능성, 공시/뉴스 리스크를 통합 검토한 딜카드 보고서입니다.",
        style="BodyLead",
        size=21,
        color="374151",
        after=260,
    )
    doc.paragraph("Executive Summary", style="Heading1", color="13232E", bold=True, size=30, before=120, after=100)
    doc.table(_summary_table(ordered), widths=[650, 2100, 900, 1250, 1200, 1500, 1760], compact=True)
    doc.page_break()
    for index, item in enumerate(ordered, 1):
        _candidate_section(doc, item, index)
        if index != len(ordered):
            doc.page_break()
    return doc.build()


CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

DOCUMENT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
</Relationships>"""

CORE_PROPS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:dcterms="http://purl.org/dc/terms/"
  xmlns:dcmitype="http://purl.org/dc/dcmitype/"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>TL Holdings M&amp;A Deal Card Report</dc:title>
  <dc:creator>TL M&amp;A Radar</dc:creator>
  <cp:lastModifiedBy>TL M&amp;A Radar</cp:lastModifiedBy>
</cp:coreProperties>"""

APP_PROPS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
  xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>TL M&amp;A Radar</Application>
</Properties>"""

SETTINGS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:zoom w:percent="100"/>
  <w:defaultTabStop w:val="720"/>
</w:settings>"""

NUMBERING_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:abstractNum w:abstractNumId="1">
    <w:multiLevelType w:val="hybridMultilevel"/>
    <w:lvl w:ilvl="0">
      <w:start w:val="1"/>
      <w:numFmt w:val="bullet"/>
      <w:lvlText w:val="•"/>
      <w:lvlJc w:val="left"/>
      <w:pPr>
        <w:tabs><w:tab w:val="num" w:pos="720"/></w:tabs>
        <w:ind w:left="720" w:hanging="360"/>
        <w:spacing w:after="160" w:line="280" w:lineRule="auto"/>
      </w:pPr>
      <w:rPr>
        <w:rFonts w:ascii="Symbol" w:hAnsi="Symbol" w:hint="default"/>
      </w:rPr>
    </w:lvl>
  </w:abstractNum>
  <w:num w:numId="1">
    <w:abstractNumId w:val="1"/>
  </w:num>
</w:numbering>"""

STYLES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:qFormat/>
    <w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Malgun Gothic" w:cs="Calibri"/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr><w:spacing w:before="0" w:after="120"/></w:pPr>
    <w:rPr><w:b/><w:color w:val="13232E"/><w:sz w:val="40"/><w:szCs w:val="40"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr><w:keepNext/><w:spacing w:before="260" w:after="120"/></w:pPr>
    <w:rPr><w:b/><w:color w:val="13232E"/><w:sz w:val="32"/><w:szCs w:val="32"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr><w:keepNext/><w:spacing w:before="180" w:after="80"/></w:pPr>
    <w:rPr><w:b/><w:color w:val="0F766E"/><w:sz w:val="26"/><w:szCs w:val="26"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading3">
    <w:name w:val="heading 3"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:pPr><w:keepNext/><w:spacing w:before="120" w:after="60"/></w:pPr>
    <w:rPr><w:b/><w:color w:val="374151"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="BodyLead">
    <w:name w:val="Body Lead"/>
    <w:basedOn w:val="Normal"/>
    <w:pPr><w:spacing w:after="160" w:line="300" w:lineRule="auto"/></w:pPr>
    <w:rPr><w:color w:val="374151"/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr>
  </w:style>
</w:styles>"""
