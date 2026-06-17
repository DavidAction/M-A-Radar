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

from tl_ma_radar.config import get_settings  # noqa: E402
from tl_ma_radar.news_analysis import load_news_cache, news_for_code  # noqa: E402
from tl_ma_radar.repository import load_candidates  # noqa: E402
from tl_ma_radar.scoring import score_candidate  # noqa: E402


DATA_PATH = ROOT / "tl_ma_radar" / "data" / "real_candidates.json"
MEMO_DIR = ROOT / "tl_ma_radar" / "data" / "deal_memos"


def load_rows() -> list[dict[str, Any]]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def write_rows(rows: list[dict[str, Any]]) -> None:
    DATA_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def format_won(value: int | float | None) -> str:
    if value is None:
        return "-"
    if abs(value) >= 100_000_000:
        return f"{value / 100_000_000:,.1f}억"
    return f"{value:,.0f}원"


def format_pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"


def safe_filename(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", value).strip("_")


def topic_name(name: str) -> str:
    if not name:
        return name
    last = name[-1]
    code = ord(last)
    if 0xAC00 <= code <= 0xD7A3:
        has_final = (code - 0xAC00) % 28 != 0
        return f"{name}{'은' if has_final else '는'}"
    return f"{name}은(는)"


def top_snippets(analysis: dict[str, Any], limit: int = 4) -> list[str]:
    snippets = analysis.get("snippets") or {}
    result: list[str] = []
    for key in ["business", "synergy", "risk", "financing", "related_party", "shareholder"]:
        for text in snippets.get(key) or []:
            if text and text not in result:
                result.append(text)
            if len(result) >= limit:
                return result
    return result


def risk_points(flags: list[str]) -> list[str]:
    points: list[str] = []
    flag_set = set(flags)
    if {"관리종목", "투자주의환기"} & flag_set:
        points.append("관리종목/환기종목 이슈는 진입 기회이지만 상장유지 요건과 거래정지 가능성을 선확인해야 합니다.")
    if "계속기업불확실성" in flag_set:
        points.append("계속기업 불확실성 문구가 있어 현금흐름, 차입금 만기, 감사인 질의사항을 우선 검증해야 합니다.")
    if "감사의견리스크" in flag_set:
        points.append("감사의견 리스크가 감지되어 감사보고서 주석과 전기 수정사항 확인이 필요합니다.")
    if "CB/BW공시" in flag_set or "CB오버행" in flag_set:
        points.append("전환사채/BW 오버행 가능성이 있어 리픽싱, 전환가능 물량, 콜옵션 보유자를 확인해야 합니다.")
    if "최대주주변경" in flag_set:
        points.append("최대주주 변경 이력이 있어 실제 경영권 매각 의향과 우호지분 구조를 별도 확인해야 합니다.")
    if "특수관계거래" in flag_set:
        points.append("특수관계자 거래가 감지되어 거래가격, 채권 회수 가능성, 사외이사/감사 검토 절차를 확인해야 합니다.")
    if not points:
        points.append("중대 리스크 신호는 제한적이나, 최근 공시와 감사보고서 주석의 우발채무를 확인해야 합니다.")
    return points[:5]


def fit_points(row: dict[str, Any], scored: dict[str, Any]) -> list[str]:
    keywords = row.get("business_keywords") or []
    scores = scored["scores"]
    signals = row.get("deal_signals") or {}
    points = [
        f"시가총액 {format_won(row.get('market_cap_krw'))}로 300억 이하 필터를 통과했고, 저평가 점수는 {scores['undervaluation']}점입니다.",
    ]
    tl_keywords = [kw for kw in keywords if kw in {"석유화학", "수지/플라스틱", "용제/첨가제", "화학유통"}]
    renes_keywords = [kw for kw in keywords if kw in {"필름/코팅", "정밀화학/소재", "환경/폐수", "자원순환", "2차전지"}]
    if tl_keywords:
        points.append(f"티엘홀딩스의 석유화학 수입·유통 축과 연결될 수 있는 키워드가 있습니다: {', '.join(tl_keywords)}.")
    if renes_keywords:
        points.append(f"르네스머테리얼의 가공·소재 납품 축과 맞닿는 보고서 신호가 있습니다: {', '.join(renes_keywords)}.")
    if scores["opportunity"] >= 45:
        points.append("공시/상태 플래그상 백기사 또는 재무구조 개선 니즈가 있을 가능성이 높아 보입니다.")
    if signals:
        points.append(
            f"딜 신호 모델상 백기사 필요도는 {signals.get('white_knight_need')}, "
            f"실행 창은 '{signals.get('deal_window')}'입니다."
        )
    if scores["core_business"] >= 35:
        points.append("매출 또는 영업자산 기반이 확인되어 단순 페이퍼컴퍼니보다 본업 실사 가치가 있습니다.")
    return points[:5]


def diligence_questions(row: dict[str, Any]) -> list[str]:
    flags = set(row.get("status_flags") or [])
    signals = row.get("deal_signals") or {}
    questions = [
        "최대주주와 우호지분이 실제 경영권 매각 또는 제3자 배정 유증에 동의할 가능성이 있는가?",
        "티엘/르네스와 원재료 조달, 가공, 납품, 폐수·자원순환 중 어떤 항목에서 실거래 시너지가 가능한가?",
        "300억 유증 납입 후 자금사용계획이 상장유지, 차입금 상환, 운전자금, 신사업 투자 중 어디에 배분되어야 하는가?",
    ]
    if "CB/BW공시" in flags or "CB오버행" in flags:
        questions.append("CB/BW 전환가능 물량, 리픽싱 조건, 콜옵션 보유자, 전환 후 지분 희석률은 얼마인가?")
    if "계속기업불확실성" in flags or "감사의견리스크" in flags:
        questions.append("감사인이 지적한 계속기업/의견 리스크의 해소 조건과 필요한 현금 규모는 얼마인가?")
    if "특수관계거래" in flags:
        questions.append("특수관계자 채권·채무, 매출, 자금대여 거래가 정상가격과 회수 가능성을 충족하는가?")
    if signals.get("deal_window") == "고위험 선실사":
        questions.append("접촉 전 상장폐지·감사의견·거래정지 리스크를 법무/회계 관점에서 먼저 게이트 체크할 수 있는가?")
    return questions[:6]


def next_actions(row: dict[str, Any]) -> list[str]:
    signals = row.get("deal_signals") or {}
    actions = [
        "최근 사업보고서, 반기/분기보고서, 감사보고서 주석을 원문 기준으로 1차 리뷰합니다.",
        "최대주주 및 주요 CB/BW 보유자 접촉 가능 경로를 확인합니다.",
        "티엘/르네스 구매·영업 담당자 관점에서 실거래 가능한 품목 리스트를 매칭합니다.",
    ]
    if signals.get("deal_window") == "즉시 접촉 후보":
        actions.insert(1, "최근 90일 공시 이벤트를 기준으로 최대주주/재무자문 접촉 가능성을 우선 확인합니다.")
    if signals.get("deal_window") == "고위험 선실사":
        actions.insert(1, "상장유지 가능성, 감사의견, 거래정지 사유를 먼저 통과 조건으로 둡니다.")
    if row.get("dart_enrichment", {}).get("periodic_reports"):
        actions.append("앱의 보고서 다운로드 링크에서 최신 정기보고서 ZIP을 받아 원문 표와 주석을 대조합니다.")
    return actions


def build_memo(row: dict[str, Any], scored: dict[str, Any], rank: int) -> dict[str, Any]:
    analysis = row.get("report_analysis") or {}
    keywords = row.get("business_keywords") or []
    flags = row.get("status_flags") or []
    cap_case = scored["capital_raise_case"]
    signals = row.get("deal_signals") or {}
    news = row.get("news_analysis") or {}
    shareholder = analysis.get("largest_shareholder") or {}
    shareholder_text = "-"
    if shareholder.get("name"):
        shareholder_text = f"{shareholder['name']} {format_pct(shareholder.get('ratio'))}"
    latest = (row.get("dart_enrichment") or {}).get("latest_filing") or {}
    summary = (
        f"{topic_name(row['name'])} 시총 {format_won(row.get('market_cap_krw'))}의 코스닥 후보로 "
        f"현재 레이더 점수 {scored['scores']['total']}점, 판단은 '{scored['recommendation']}'입니다. "
        f"보고서 기반 키워드는 {', '.join(keywords[:6]) or '제한적'}이며, "
        f"300억 유증 시 단순 포스트머니 기준 신규 지분율은 {format_pct(cap_case['implied_new_share_ratio'])}입니다."
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rank": rank,
        "score": scored["scores"]["total"],
        "recommendation": scored["recommendation"],
        "summary": summary,
        "fit_points": fit_points(row, scored),
        "risk_points": risk_points(flags),
        "capital_raise_note": (
            f"신규자금 {format_won(cap_case['new_money_krw'])} 투입 시 단순 신규 지분율은 "
            f"{format_pct(cap_case['implied_new_share_ratio'])}입니다. 실제 구조는 발행가, 할인율, "
            "기존 주주/CB/BW 희석, 제3자배정 적법성 검토 후 다시 산정해야 합니다."
        ),
        "diligence_questions": diligence_questions(row),
        "next_actions": next_actions(row),
        "evidence": {
            "latest_filing": f"{latest.get('rcept_dt', '-')} {latest.get('report_nm', '')}".strip(),
            "largest_shareholder": shareholder_text,
            "keywords": keywords[:10],
            "flags": flags[:10],
            "snippets": top_snippets(analysis),
            "deal_signals": {
                "white_knight_need": signals.get("white_knight_need"),
                "deal_window": signals.get("deal_window"),
                "deal_execution_score": (signals.get("scores") or {}).get("deal_execution_score"),
                "white_knight_need_score": (signals.get("scores") or {}).get("white_knight_need_score"),
            },
            "news": {
                "summary": news.get("summary"),
                "tone": news.get("tone"),
                "article_count": news.get("article_count"),
                "latest_title": ((news.get("articles") or [{}])[0] or {}).get("title"),
            },
        },
    }


def memo_markdown(row: dict[str, Any], memo: dict[str, Any]) -> str:
    def bullet(items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items) or "- -"

    evidence = memo["evidence"]
    snippets = bullet(evidence.get("snippets") or ["보고서 스니펫 없음"])
    news = evidence.get("news") or {}
    return f"""# {row['name']}({row['code']}) 딜 메모 초안

- 순위: {memo['rank']}
- 레이더 판단: {memo['recommendation']}
- 점수: {memo['score']}
- 최신 공시: {evidence.get('latest_filing') or '-'}
- 최대주주 신호: {evidence.get('largest_shareholder') or '-'}
- 백기사/딜 신호: {(evidence.get('deal_signals') or {}).get('white_knight_need') or '-'} / {(evidence.get('deal_signals') or {}).get('deal_window') or '-'}
- 최근 뉴스: {(evidence.get('news') or {}).get('tone') or '-'} / {(evidence.get('news') or {}).get('article_count') or 0}건

## 요약
{memo['summary']}

## 최근 6개월 뉴스
- 톤: {news.get('tone') or '-'}
- 기사 수: {news.get('article_count') or 0}
- 최신 기사: {news.get('latest_title') or '-'}
- 요약: {news.get('summary') or '-'}

## 인수 논거
{bullet(memo['fit_points'])}

## 리스크 체크
{bullet(memo['risk_points'])}

## 300억 유증 가정
{memo['capital_raise_note']}

## 실사 질문
{bullet(memo['diligence_questions'])}

## 다음 액션
{bullet(memo['next_actions'])}

## 보고서 근거 스니펫
{snippets}
"""


def clear_generated_memos() -> None:
    if not MEMO_DIR.exists():
        return
    for path in MEMO_DIR.glob("*.md"):
        if path.is_file():
            path.unlink()


def generate(limit: int) -> None:
    settings = get_settings(ROOT)
    rows = load_rows()
    news_cache = load_news_cache(ROOT)
    merged_rows = []
    for row in load_candidates(ROOT):
        prepared = dict(row)
        prepared["news_analysis"] = news_for_code(news_cache, str(prepared.get("code", "")))
        merged_rows.append(prepared)
    merged_by_code = {row["code"]: row for row in merged_rows}
    scored_by_code = {row["code"]: score_candidate(row, settings) for row in merged_rows}
    ranked = sorted(scored_by_code.values(), key=lambda row: row["scores"]["total"], reverse=True)
    target_codes = {row["code"]: idx for idx, row in enumerate(ranked[:limit], start=1)}
    MEMO_DIR.mkdir(parents=True, exist_ok=True)
    clear_generated_memos()

    updated_rows: list[dict[str, Any]] = []
    for row in rows:
        updated = dict(row)
        updated.pop("deal_memo", None)
        rank = target_codes.get(row["code"])
        if rank:
            scored = scored_by_code[row["code"]]
            source = merged_by_code.get(row["code"], row)
            memo = build_memo(source, scored, rank)
            filename = f"{rank:02d}_{source['code']}_{safe_filename(source['name'])}.md"
            (MEMO_DIR / filename).write_text(memo_markdown(source, memo), encoding="utf-8")
            memo["memo_file"] = f"deal_memos/{filename}"
            updated["deal_memo"] = memo
            print(f"[{rank}/{limit}] {source['code']} {source['name']} -> {filename}")
        updated_rows.append(updated)
    write_rows(updated_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate first-pass acquisition deal memos.")
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    generate(limit=args.limit)


if __name__ == "__main__":
    main()
