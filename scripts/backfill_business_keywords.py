from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "tl_ma_radar" / "data" / "real_candidates.json"
TEXT_ROOT = ROOT / "tl_ma_radar" / "data"


KEYWORD_RULES: dict[str, list[str]] = {
    "석유화학": ["석유화학", "화학제품", "화학 제품", "화학원료", "화학 원료", "합성화학", "petrochemical"],
    "화학유통": ["수입 유통", "원료 유통", "화학제품 유통", "화학제품 도매"],
    "수지/플라스틱": [
        "합성수지",
        "플라스틱",
        "ABS",
        "Acrylonitrile",
        "폴리프로필렌",
        "폴리에틸렌",
        "PET",
        "PP",
        "PE",
    ],
    "용제/첨가제": ["용제", "첨가제", "접착제", "점착제", "코팅액", "레진", "안정제"],
    "필름/코팅": ["필름", "코팅", "광학필름", "보호필름", "박막", "코팅필름", "코팅 필름"],
    "정밀화학/소재": ["정밀화학", "전자재료", "기능성 소재", "화학소재", "복합소재", "고분자소재", "유기재료", "무기재료"],
    "환경/폐수": ["폐수", "폐수처리", "폐기물처리", "대기오염", "수질오염", "환경 인허가"],
    "자원순환": ["자원순환", "재활용", "리사이클", "재생원료", "유가금속 회수"],
    "2차전지": ["2차전지", "이차전지", "양극재", "음극재", "전극재", "리튬", "전구체"],
}


def _load_text(row: dict[str, Any], *, use_full_text: bool = False) -> str:
    pieces = [
        str(row.get("sector") or ""),
        str(row.get("deal_thesis") or ""),
    ]
    analysis = row.get("report_analysis") if isinstance(row.get("report_analysis"), dict) else {}
    snippets = analysis.get("snippets") if isinstance(analysis.get("snippets"), dict) else {}
    for key in ("business", "synergy", "customer"):
        values = snippets.get(key) or []
        if isinstance(values, list):
            pieces.extend(str(value) for value in values[:4])
    text_file = str(analysis.get("text_file") or "").replace("\\", "/")
    if use_full_text and text_file:
        path = (TEXT_ROOT / text_file).resolve()
        try:
            if TEXT_ROOT.resolve() in path.parents and path.exists():
                pieces.append(path.read_text(encoding="utf-8", errors="replace")[:350_000])
        except OSError:
            pass
    return " ".join(pieces)


def _hits(text: str) -> tuple[list[str], dict[str, list[str]]]:
    lowered = text.lower()
    keywords: list[str] = []
    evidence: dict[str, list[str]] = {}
    for label, terms in KEYWORD_RULES.items():
        matched = [term for term in terms if _contains(text, lowered, term)]
        if matched:
            keywords.append(label)
            evidence[label] = matched[:5]
    return keywords, evidence


def _contains(text: str, lowered: str, term: str) -> bool:
    if re.fullmatch(r"[A-Za-z0-9/]+", term) and len(term) <= 4:
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text, flags=re.IGNORECASE) is not None
    return term.lower() in lowered


def _merge(existing: list[Any], added: list[str], limit: int) -> list[str]:
    output: list[str] = []
    for value in [*existing, *added]:
        text = str(value).strip()
        if text and text not in output:
            output.append(text)
        if len(output) >= limit:
            break
    return output


def backfill(
    limit: int | None = None,
    max_keywords: int = 8,
    replace: bool = False,
    use_full_text: bool = False,
) -> dict[str, int]:
    rows = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    changed = 0
    scanned = 0
    keyword_gap_before = sum(1 for row in rows if len(row.get("business_keywords") or []) < 2)
    for row in rows[: limit or len(rows)]:
        scanned += 1
        text = _load_text(row, use_full_text=use_full_text)
        added, evidence = _hits(text)
        if not added and not replace:
            continue
        before = list(row.get("business_keywords") or [])
        merged = added[:max_keywords] if replace else _merge(before, added, max_keywords)
        analysis = row.setdefault("report_analysis", {})
        if not isinstance(analysis, dict):
            analysis = {}
            row["report_analysis"] = analysis
        analysis_before = list(analysis.get("business_keywords") or [])
        analysis_merged = added[:max_keywords] if replace else _merge(analysis_before, added, max_keywords)
        if merged != before or analysis_merged != analysis_before:
            row["business_keywords"] = merged
            analysis["business_keywords"] = analysis_merged
            if evidence:
                analysis["business_keyword_evidence"] = evidence
            else:
                analysis.pop("business_keyword_evidence", None)
            changed += 1
    keyword_gap_after = sum(1 for row in rows if len(row.get("business_keywords") or []) < 2)
    DATA_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "scanned": scanned,
        "changed": changed,
        "keyword_gap_before": keyword_gap_before,
        "keyword_gap_after": keyword_gap_after,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill TL/Renes business keywords from report text.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-keywords", type=int, default=8)
    parser.add_argument("--replace", action="store_true", help="Replace generated keyword lists instead of merging.")
    parser.add_argument(
        "--use-full-text",
        action="store_true",
        help="Also scan full saved DART text. Disabled by default to avoid charter/business-purpose false positives.",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            backfill(
                limit=args.limit,
                max_keywords=args.max_keywords,
                replace=args.replace,
                use_full_text=args.use_full_text,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
