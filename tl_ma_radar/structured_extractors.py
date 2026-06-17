from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExtractHit:
    label: str
    count: int
    snippets: list[str]


def _normalize(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "")
    return text.strip()


def _compact_snippet(text: str, start: int, end: int, window: int = 140) -> str:
    left = max(0, start - window)
    right = min(len(text), end + window)
    return _normalize(text[left:right])[:320]


def _term_hits(text: str, terms: list[str], *, max_snippets: int = 4) -> list[ExtractHit]:
    rows: list[ExtractHit] = []
    for term in terms:
        matches = list(re.finditer(re.escape(term), text, flags=re.IGNORECASE))
        if not matches:
            continue
        rows.append(
            ExtractHit(
                label=term,
                count=len(matches),
                snippets=[_compact_snippet(text, match.start(), match.end()) for match in matches[:max_snippets]],
            )
        )
    return sorted(rows, key=lambda row: (-row.count, row.label))


def _counts(hits: list[ExtractHit]) -> dict[str, int]:
    return {hit.label: hit.count for hit in hits}


def _snippets(hits: list[ExtractHit], limit: int = 6) -> list[str]:
    output: list[str] = []
    for hit in hits:
        for snippet in hit.snippets:
            if snippet and snippet not in output:
                output.append(snippet)
            if len(output) >= limit:
                return output
    return output


def _severity_from_counts(total: int, high_terms: int = 0) -> str:
    if high_terms >= 1:
        return "critical"
    if total >= 8:
        return "high"
    if total >= 3:
        return "medium"
    if total >= 1:
        return "low"
    return "none"


def extract_largest_shareholders(text: str, *, limit: int = 8) -> list[dict[str, Any]]:
    normalized = _normalize(text)
    if not normalized:
        return []
    anchor_pattern = re.compile(r"(최대주주|주요주주|대량보유|5%\s*이상|소유주식|보유주식)", re.IGNORECASE)
    name_ratio_pattern = re.compile(
        r"([가-힣A-Za-z0-9&().·ㆍ\s]{2,40})\s*(?:외\s*\d+\s*인)?\s*(?:보유|소유|지분|지분율|비율|주식수)?\s*[:：]?\s*([0-9]{1,2}(?:\.[0-9]+)?)\s*%",
        re.IGNORECASE,
    )
    blocked_names = {
        "전환",
        "합계",
        "계",
        "기타",
        "소계",
        "당사",
        "최대주주",
        "주요주주",
        "특수관계인",
        "발행주식",
    }
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, float]] = set()
    for anchor in anchor_pattern.finditer(normalized):
        segment = normalized[max(0, anchor.start() - 400) : min(len(normalized), anchor.end() + 1600)]
        for match in name_ratio_pattern.finditer(segment):
            raw_name = re.sub(r"\s+", " ", match.group(1)).strip(" .,-·ㆍ:：")
            name = re.sub(r"^(및|또는|성명|명칭|주주명|구분)\s+", "", raw_name).strip()
            if not name or len(name) < 2 or name in blocked_names:
                continue
            if any(block in name for block in ("자본금", "발행", "비율", "변동", "보고", "총수")):
                continue
            try:
                ratio = float(match.group(2))
            except ValueError:
                continue
            if ratio <= 0 or ratio > 100:
                continue
            key = (name, ratio)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(
                {
                    "name": name[:40],
                    "ratio": ratio,
                    "evidence": _compact_snippet(segment, match.start(), match.end(), window=110),
                }
            )
    candidates.sort(key=lambda row: float(row.get("ratio") or 0), reverse=True)
    return candidates[:limit]


def largest_shareholder(text: str) -> dict[str, Any] | None:
    candidates = extract_largest_shareholders(text, limit=1)
    return candidates[0] if candidates else None


def extract_audit_opinion(text: str) -> dict[str, Any]:
    normalized = _normalize(text)
    terms = [
        "적정의견",
        "한정의견",
        "부적정의견",
        "의견거절",
        "계속기업 불확실성",
        "계속기업으로서의 존속능력",
        "내부회계관리제도",
        "중요한 불확실성",
    ]
    hits = _term_hits(normalized, terms)
    count_map = _counts(hits)
    opinion = ""
    severity = "none"
    for label, level in [
        ("의견거절", "critical"),
        ("부적정의견", "critical"),
        ("한정의견", "high"),
        ("계속기업 불확실성", "high"),
        ("중요한 불확실성", "medium"),
        ("적정의견", "low"),
    ]:
        if count_map.get(label):
            opinion = label
            severity = level
            break
    if not opinion and hits:
        opinion = hits[0].label
        severity = _severity_from_counts(sum(count_map.values()))
    return {
        "opinion": opinion,
        "severity": severity,
        "counts": count_map,
        "snippets": _snippets(hits),
    }


def extract_convertible_bonds(text: str) -> dict[str, Any]:
    normalized = _normalize(text)
    terms = [
        "전환사채",
        "신주인수권부사채",
        "교환사채",
        "CB",
        "BW",
        "전환가액",
        "전환청구",
        "행사가액",
        "리픽싱",
        "콜옵션",
        "풋옵션",
        "사채권자",
    ]
    hits = _term_hits(normalized, terms)
    count_map = _counts(hits)
    total = sum(count_map.values())
    has_convertible = any(count_map.get(term, 0) for term in ("전환사채", "신주인수권부사채", "CB", "BW"))
    pending_terms = {"전환청구", "전환가액", "행사가액", "리픽싱", "콜옵션", "풋옵션"}
    return {
        "has_convertible": bool(has_convertible),
        "severity": _severity_from_counts(total, high_terms=sum(1 for term in pending_terms if count_map.get(term))),
        "counts": count_map,
        "snippets": _snippets(hits),
    }


def extract_related_party_transactions(text: str) -> dict[str, Any]:
    normalized = _normalize(text)
    terms = [
        "특수관계자",
        "특수관계인",
        "관계기업",
        "종속기업",
        "관계회사",
        "최대주주",
        "임원",
        "대여금",
        "차입금",
        "채무보증",
        "담보제공",
        "지급보증",
        "매출채권",
        "매입채무",
        "거래내역",
    ]
    hits = _term_hits(normalized, terms)
    count_map = _counts(hits)
    total = sum(count_map.values())
    high_terms = sum(1 for term in ("대여금", "채무보증", "담보제공", "지급보증") if count_map.get(term))
    return {
        "has_related_party": total > 0,
        "severity": _severity_from_counts(total, high_terms=high_terms),
        "counts": count_map,
        "snippets": _snippets(hits),
    }


def extract_control_signals(text: str) -> dict[str, Any]:
    normalized = _normalize(text)
    terms = [
        "최대주주 변경",
        "경영권",
        "의결권",
        "주식등의 대량보유",
        "담보",
        "질권",
        "공동보유",
        "특별관계자",
        "소유상황",
    ]
    hits = _term_hits(normalized, terms)
    return {
        "counts": _counts(hits),
        "snippets": _snippets(hits),
    }


def structured_extracts(text: str) -> dict[str, Any]:
    normalized = _normalize(text)
    audit = extract_audit_opinion(normalized)
    cb = extract_convertible_bonds(normalized)
    related = extract_related_party_transactions(normalized)
    shareholders = extract_largest_shareholders(normalized)
    control = extract_control_signals(normalized)
    top_terms = Counter()
    for section in (audit, cb, related, control):
        top_terms.update(section.get("counts") or {})
    return {
        "audit_opinion": audit,
        "convertible_bonds": cb,
        "related_party_transactions": related,
        "largest_shareholder_candidates": shareholders,
        "control_signals": control,
        "top_terms": dict(top_terms.most_common(12)),
    }
