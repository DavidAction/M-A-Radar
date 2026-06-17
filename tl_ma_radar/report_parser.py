from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from lxml import etree

    HAS_LXML = True
except ImportError:
    from xml.etree import ElementTree as etree

    HAS_LXML = False


TL_SYNERGY_TERMS = {
    "석유화학": ["석유화학", "화학제품", "화학 원료"],
    "수지/플라스틱": [
        "합성수지",
        "플라스틱",
        "PET필름",
        "PET 필름",
        "PET 수지",
        "PP필름",
        "PP 수지",
        "PE필름",
        "PE 수지",
        "폴리프로필렌",
        "폴리에틸렌",
    ],
    "용제/첨가제": ["용제", "첨가제", "코팅액"],
    "화학유통": ["화학제품 유통", "원료 유통", "화학제품 도매", "수입 유통"],
}

RENES_SYNERGY_TERMS = {
    "필름/코팅": ["광학필름", "보호필름", "코팅액", "코팅 필름"],
    "정밀화학/소재": ["정밀화학", "전자재료", "유기재료", "무기재료", "화학소재"],
    "환경/폐수": ["공정폐수", "폐수처리", "폐기물처리", "환경 인허가"],
    "자원순환": ["자원순환", "재생원료", "재활용", "유가금속 회수"],
    "2차전지": ["2차전지", "이차전지", "양극재", "양극활물질", "전구체", "리튬", "니켈", "배터리"],
}

RISK_TERMS = {
    "계속기업불확실성": [
        "계속기업 관련 중요한 불확실성",
        "계속기업 존속능력에 유의적 의문",
        "계속기업가정의 불확실성",
        "계속기업 불확실성",
    ],
    "감사의견리스크": ["의견거절", "부적정", "한정의견"],
    "자본잠식": ["자본잠식"],
    "관리종목": ["관리종목"],
    "투자주의환기": ["투자주의환기"],
    "거래정지": ["주권매매거래정지", "거래정지"],
    "상장폐지위험": ["상장폐지"],
    "유상증자공시": ["유상증자"],
    "감자공시": ["무상감자", "자본감소", "감자"],
    "CB/BW공시": ["전환사채", "신주인수권부사채", "CB", "BW"],
    "최대주주변경": ["최대주주 변경", "최대주주변경"],
    "특수관계거래": ["특수관계자", "대주주 등과의 거래", "특수관계인"],
    "매출채권검증필요": ["매출채권", "대손충당금", "장기미수"],
}

AUDIT_TERMS = {
    "적정의견": ["적정의견", "감사의견은 적정"],
    "한정의견": ["한정의견"],
    "부적정/의견거절": ["부적정", "의견거절"],
    "계속기업불확실성": [
        "계속기업 관련 중요한 불확실성",
        "계속기업 존속능력에 유의적 의문",
        "계속기업가정의 불확실성",
        "계속기업 불확실성",
    ],
    "내부회계주의": ["내부회계관리제도", "중요한 취약점", "검토의견"],
}

CONTROL_TERMS = {
    "최대주주변경": ["최대주주 변경", "최대주주변경", "변경 후 최대주주"],
    "경영권양수도": ["경영권 양수도", "경영권양수도", "주식 및 경영권 양수도"],
    "낮은지분/분산": ["소액주주", "5% 이상 주주", "대량보유", "주식등의 대량보유"],
    "담보/질권": ["주식담보", "질권", "담보권"],
}

FINANCING_TERMS = {
    "유상증자": ["유상증자", "제3자배정", "주주배정"],
    "CB/BW": ["전환사채", "신주인수권부사채", "CB", "BW"],
    "감자/자본감소": ["무상감자", "자본감소", "감자"],
    "차입/만기": ["단기차입", "차입금", "만기", "상환"],
    "자본잠식": ["자본잠식"],
}

RELATED_PARTY_TERMS = {
    "특수관계자거래": ["특수관계자", "특수관계인", "대주주 등과의 거래"],
    "종속/관계기업": ["종속기업", "관계기업", "공동기업", "계열회사"],
    "자금대여/채무보증": ["자금대여", "대여금", "채무보증", "지급보증"],
}

CUSTOMER_TERMS = {
    "주요매출처": ["주요 매출처", "주요매출처", "주요 고객", "매출처"],
    "매출채권": ["매출채권", "대손충당금", "장기미수"],
    "수출/납품": ["수출", "납품", "공급계약", "판매경로"],
}

EXIT_STRUCTURE_TERMS = {
    "자회사/종속회사": ["자회사", "종속기업", "종속회사"],
    "관계회사거래": ["관계기업", "특수관계자", "특수관계인"],
    "사업양수도": ["영업양수", "영업양도", "사업양수", "사업양도", "자산양수도"],
    "제3자배정": ["제3자배정", "유상증자"],
}

SNIPPET_TERMS = {
    "business": ["사업의 개요", "주요 제품", "주요제품", "주요 매출처", "판매경로"],
    "shareholder": ["최대주주", "주주에 관한 사항", "5% 이상 주주"],
    "risk": ["계속기업", "관리종목", "상장폐지", "거래정지", "자본잠식"],
    "financing": ["유상증자", "무상감자", "전환사채", "신주인수권부사채"],
    "related_party": ["특수관계자", "대주주 등과의 거래", "이해관계자와의 거래"],
    "synergy": ["필름", "코팅", "소재", "폐수", "자원순환", "이차전지", "2차전지", "화학"],
    "audit": ["감사의견", "계속기업", "내부회계관리제도", "의견거절", "한정의견"],
    "control": ["최대주주 변경", "경영권", "주식담보", "대량보유"],
    "customer": ["주요 매출처", "매출채권", "공급계약", "납품"],
}


@dataclass(frozen=True)
class ParsedReport:
    file_name: str
    text: str


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u00a0", " ")).strip()


def extract_zip_text(zip_path: Path) -> ParsedReport:
    with zipfile.ZipFile(zip_path) as zipped:
        xml_names = [name for name in zipped.namelist() if name.lower().endswith(".xml")]
        if not xml_names:
            return ParsedReport(zip_path.name, "")
        xml_names.sort(key=lambda name: len(zipped.read(name)), reverse=True)
        selected_name = xml_names[0]
        data = zipped.read(selected_name)
    if HAS_LXML:
        parser = etree.XMLParser(recover=True, huge_tree=True)
        root = etree.fromstring(data, parser)
    else:
        try:
            root = etree.fromstring(data)
        except etree.ParseError:
            raw_text = data.decode("utf-8", errors="replace")
            return ParsedReport(zip_path.name, clean_text(re.sub(r"<[^>]+>", " ", raw_text)))
    text_parts: list[str] = []
    for element in root.iter():
        if element.tag in {"TITLE", "P", "TR", "TD", "TH"}:
            value = clean_text(" ".join(element.itertext()))
            if value:
                text_parts.append(value)
    return ParsedReport(zip_path.name, clean_text(" ".join(text_parts)))


def extract_pdf_text(pdf_path: Path) -> ParsedReport:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required for PDF text extraction") from exc

    reader = PdfReader(str(pdf_path))
    text_parts = []
    for page in reader.pages[:80]:
        text_parts.append(page.extract_text() or "")
    return ParsedReport(pdf_path.name, clean_text(" ".join(text_parts)))


def find_hits(text: str, term_groups: dict[str, list[str]]) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    lowered = text.lower()
    for group, terms in term_groups.items():
        found = [term for term in terms if contains_term(text, lowered, term)]
        if found:
            hits[group] = found
    return hits


def contains_term(text: str, lowered_text: str, term: str) -> bool:
    if re.fullmatch(r"[A-Za-z0-9/]+", term) and len(term) <= 3:
        pattern = rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])"
        return re.search(pattern, text, flags=re.IGNORECASE) is not None
    return term.lower() in lowered_text


def flatten_hit_groups(hit_groups: dict[str, list[str]]) -> list[str]:
    return list(hit_groups.keys())


def snippets(text: str, limit_per_group: int = 3, radius: int = 150) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    lowered = text.lower()
    for group, terms in SNIPPET_TERMS.items():
        group_snippets: list[str] = []
        seen: set[str] = set()
        for term in terms:
            start = 0
            term_lower = term.lower()
            while len(group_snippets) < limit_per_group:
                idx = lowered.find(term_lower, start)
                if idx == -1:
                    break
                snippet = clean_text(text[max(0, idx - radius) : idx + radius])
                if snippet not in seen:
                    group_snippets.append(snippet)
                    seen.add(snippet)
                start = idx + len(term)
        if group_snippets:
            result[group] = group_snippets
    return result


def largest_shareholder(text: str) -> dict[str, Any] | None:
    candidates = extract_largest_shareholders(text)
    if candidates:
        best = candidates[0]
        return {
            "name": best.get("name"),
            "ratio": best.get("ratio"),
            "confidence": best.get("confidence"),
            "source": best.get("source"),
        }
    patterns = [
        r"([가-힣A-Za-z0-9().&·]+)\s+최대주주\s+보통주\s+[\d,]+\s+[0-9.]+\s+[\d,]+\s+([0-9]{1,3}(?:\.\d+)?)",
        r"5%\s*이상\s*주주\s+([가-힣A-Za-z0-9().&·]+)\s+[\d,]+\s+([0-9]{1,3}(?:\.\d+)?)",
        r"최대주주[^0-9]{0,80}([가-힣A-Za-z0-9().&·]+)[^0-9]{0,80}([0-9]{1,3}(?:\.\d+)?)\s*%",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1).strip()
            if re.fullmatch(r"[\d.]+", name):
                continue
            ratio = float(match.group(2))
            if 0 <= ratio <= 100:
                return {"name": name, "ratio": ratio / 100}
    return None


def _clean_holder_name(value: str) -> str:
    value = re.sub(r"[\s:：,]+", " ", value or "").strip()
    value = re.sub(r"^(성명|명칭|주주명|구분|변경전|변경후|소유자)\s+", "", value)
    return value.strip(" -·")


def _window(text: str, keyword: str, radius: int = 220) -> list[str]:
    windows = []
    start = 0
    lowered = text.lower()
    needle = keyword.lower()
    while True:
        idx = lowered.find(needle, start)
        if idx == -1:
            break
        windows.append(clean_text(text[max(0, idx - radius) : idx + radius]))
        start = idx + len(keyword)
    return windows


def extract_largest_shareholders(text: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    windows = _window(text, "최대주주", radius=320) + _window(text, "5% 이상", radius=260)
    patterns = [
        r"([가-힣A-Za-z0-9().&·]{2,40})\s+(?:외\s*\d+인\s+)?(?:보통주\s+)?[\d,]{3,}\s+(?:주\s+)?([0-9]{1,3}(?:\.\d+)?)\s*%",
        r"([가-힣A-Za-z0-9().&·]{2,40})\s+[\d,]{3,}\s+([0-9]{1,3}(?:\.\d+)?)\s+(?:최대주주|대표이사|특수관계)",
        r"최대주주[^가-힣A-Za-z0-9]{0,40}([가-힣A-Za-z0-9().&·]{2,40})[^0-9%]{0,100}([0-9]{1,3}(?:\.\d+)?)\s*%",
    ]
    blocked = {"최대주주", "변경", "보고서", "보통주", "합계", "소계", "주주", "성명", "명칭"}
    for source in windows:
        for pattern in patterns:
            for match in re.finditer(pattern, source):
                name = _clean_holder_name(match.group(1))
                if not name or name in blocked or re.fullmatch(r"[\d.]+", name):
                    continue
                ratio = float(match.group(2))
                if not (0 < ratio <= 100):
                    continue
                confidence = 0.72
                if "최대주주" in source:
                    confidence += 0.12
                if "특수관계" in source or "외" in source:
                    confidence += 0.05
                candidates.append(
                    {
                        "name": name,
                        "ratio": ratio / 100,
                        "confidence": round(min(confidence, 0.96), 2),
                        "source": source[:260],
                    }
                )
    deduped: dict[tuple[str, float], dict[str, Any]] = {}
    for candidate in candidates:
        key = (str(candidate["name"]), round(float(candidate["ratio"]), 4))
        if key not in deduped or candidate["confidence"] > deduped[key]["confidence"]:
            deduped[key] = candidate
    return sorted(deduped.values(), key=lambda row: (row["confidence"], row["ratio"]), reverse=True)[:8]


def extract_audit_opinion(text: str) -> dict[str, Any]:
    checks = [
        ("의견거절", "critical", ["의견거절"]),
        ("부적정", "critical", ["부적정"]),
        ("한정", "high", ["한정의견", "한정 의견"]),
        (
            "계속기업 불확실성",
            "high",
            [
                "계속기업 관련 중요한 불확실성",
                "계속기업 존속능력에 유의적 의문",
                "계속기업가정의 불확실성",
                "계속기업 불확실성",
            ],
        ),
        ("적정", "low", ["적정의견", "감사의견은 적정", "적정 의견"]),
    ]
    hits = []
    for label, severity, terms in checks:
        matched = [term for term in terms if term in text]
        if matched:
            hits.append({"opinion": label, "severity": severity, "terms": matched})

    if not hits:
        for source in _window(text, "계속기업", radius=180):
            if any(term in source for term in ["중요한 불확실성", "존속능력", "유의적 의문", "의견거절"]):
                hits.append(
                    {
                        "opinion": "계속기업 불확실성",
                        "severity": "high",
                        "terms": ["계속기업+불확실성 문맥"],
                    }
                )
                break

    opinion = hits[0] if hits else {"opinion": "미확인", "severity": "unknown", "terms": []}
    source_terms = ["감사의견", "계속기업", "의견거절", "한정의견", "부적정", "적정의견"]
    source = []
    for term in source_terms:
        source.extend(_window(text, term, radius=160)[:2])
    return {
        **opinion,
        "confidence": 0.86 if hits else 0.25,
        "source_snippets": source[:5],
    }


def extract_convertible_bonds(text: str) -> dict[str, Any]:
    terms = ["전환사채", "신주인수권부사채", "CB", "BW", "전환가액", "리픽싱", "콜옵션", "풋옵션"]
    counts = {term: len(re.findall(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text, flags=re.IGNORECASE)) if term in {"CB", "BW"} else text.count(term) for term in terms}
    snippets_out = []
    for term in terms:
        snippets_out.extend(_window(text, term, radius=180)[:2])
    amount_patterns = re.findall(r"([0-9,]+(?:\.\d+)?)\s*(억원|백만원|원)\s*(?:규모|상당|발행|의)?\s*(?:전환사채|신주인수권부사채|CB|BW)?", text)
    return {
        "has_convertible": any(counts.values()),
        "counts": {key: value for key, value in counts.items() if value},
        "amount_mentions": [" ".join(match) for match in amount_patterns[:8]],
        "source_snippets": list(dict.fromkeys(snippets_out))[:8],
        "confidence": 0.82 if any(counts.values()) else 0.2,
    }


def extract_related_party_transactions(text: str) -> dict[str, Any]:
    terms = ["특수관계자", "특수관계인", "대주주 등과의 거래", "이해관계자", "관계기업", "종속기업", "자금대여", "채무보증"]
    hits = {term: text.count(term) for term in terms if text.count(term)}
    snippets_out = []
    for term in terms:
        snippets_out.extend(_window(text, term, radius=180)[:2])
    return {
        "has_related_party": bool(hits),
        "counts": hits,
        "source_snippets": list(dict.fromkeys(snippets_out))[:8],
        "confidence": 0.8 if hits else 0.2,
    }


def structured_extracts(text: str) -> dict[str, Any]:
    return {
        "largest_shareholder_candidates": extract_largest_shareholders(text),
        "audit_opinion": extract_audit_opinion(text),
        "convertible_bonds": extract_convertible_bonds(text),
        "related_party_transactions": extract_related_party_transactions(text),
    }


def infer_sector(keywords: list[str]) -> str | None:
    if any(keyword in keywords for keyword in ["환경/폐수", "자원순환"]):
        return "환경/자원순환 후보"
    if "2차전지" in keywords:
        return "2차전지 소재 전환 후보"
    if any(keyword in keywords for keyword in ["필름/코팅", "정밀화학/소재"]):
        return "정밀화학/소재 후보"
    if any(keyword in keywords for keyword in ["석유화학", "수지/플라스틱", "용제/첨가제", "화학유통"]):
        return "화학 유통/소재 후보"
    return None


def signal_counts(text: str, term_groups: dict[str, list[str]]) -> dict[str, int]:
    counts = {}
    lowered = text.lower()
    for group, terms in term_groups.items():
        total = 0
        for term in terms:
            if re.fullmatch(r"[A-Za-z0-9/]+", term) and len(term) <= 3:
                pattern = rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])"
                total += len(re.findall(pattern, text, flags=re.IGNORECASE))
            else:
                total += lowered.count(term.lower())
        if total:
            counts[group] = total
    return counts


def evidence_strength(*hit_groups: dict[str, list[str]], text_chars: int) -> float:
    category_hits = sum(len(group) for group in hit_groups)
    size_score = min(text_chars / 40000 * 35, 35)
    return round(min(category_hits * 8 + size_score, 100), 1)


def analysis_flags(
    audit_hits: dict[str, list[str]],
    financing_hits: dict[str, list[str]],
    control_hits: dict[str, list[str]],
    related_hits: dict[str, list[str]],
) -> list[str]:
    flags = []
    if "계속기업불확실성" in audit_hits:
        flags.append("계속기업불확실성")
    if "한정의견" in audit_hits or "부적정/의견거절" in audit_hits:
        flags.append("감사의견리스크")
    if "자본잠식" in financing_hits:
        flags.append("자본잠식")
    if "감자/자본감소" in financing_hits:
        flags.append("감자공시")
    if "CB/BW" in financing_hits:
        flags.append("CB/BW공시")
    if "유상증자" in financing_hits:
        flags.append("유상증자공시")
    if "최대주주변경" in control_hits:
        flags.append("최대주주변경")
    if related_hits:
        flags.append("특수관계거래")
    return list(dict.fromkeys(flags))


def analyze_text(text: str) -> dict[str, Any]:
    tl_hits = find_hits(text, TL_SYNERGY_TERMS)
    renes_hits = find_hits(text, RENES_SYNERGY_TERMS)
    risk_hits = find_hits(text, RISK_TERMS)
    audit_hits = find_hits(text, AUDIT_TERMS)
    control_hits = find_hits(text, CONTROL_TERMS)
    financing_hits = find_hits(text, FINANCING_TERMS)
    related_hits = find_hits(text, RELATED_PARTY_TERMS)
    customer_hits = find_hits(text, CUSTOMER_TERMS)
    exit_hits = find_hits(text, EXIT_STRUCTURE_TERMS)
    business_keywords = list(dict.fromkeys(flatten_hit_groups(tl_hits) + flatten_hit_groups(renes_hits)))
    shareholder = largest_shareholder(text)
    extracts = structured_extracts(text)
    structured_flags = analysis_flags(audit_hits, financing_hits, control_hits, related_hits)
    return {
        "text_chars": len(text),
        "business_keywords": business_keywords,
        "risk_flags": list(dict.fromkeys(flatten_hit_groups(risk_hits) + structured_flags)),
        "tl_hits": tl_hits,
        "renes_hits": renes_hits,
        "audit_signals": flatten_hit_groups(audit_hits),
        "control_signals": flatten_hit_groups(control_hits),
        "financing_signals": flatten_hit_groups(financing_hits),
        "related_party_signals": flatten_hit_groups(related_hits),
        "customer_signals": flatten_hit_groups(customer_hits),
        "exit_structure_signals": flatten_hit_groups(exit_hits),
        "signal_counts": {
            "audit": signal_counts(text, AUDIT_TERMS),
            "control": signal_counts(text, CONTROL_TERMS),
            "financing": signal_counts(text, FINANCING_TERMS),
            "related_party": signal_counts(text, RELATED_PARTY_TERMS),
            "customer": signal_counts(text, CUSTOMER_TERMS),
        },
        "evidence_strength": evidence_strength(
            tl_hits,
            renes_hits,
            audit_hits,
            control_hits,
            financing_hits,
            related_hits,
            customer_hits,
            text_chars=len(text),
        ),
        "largest_shareholder": shareholder,
        "structured_extracts": extracts,
        "snippets": snippets(text),
        "inferred_sector": infer_sector(business_keywords),
    }
