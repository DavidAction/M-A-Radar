from __future__ import annotations

from datetime import date, datetime
from typing import Any


CATEGORY_RULES = {
    "자금조달": ["유상증자", "전환사채", "신주인수권부사채", "증권신고서", "증권발행", "청약결과"],
    "지분/경영권": ["최대주주", "대량보유", "임원ㆍ주요주주", "주식양수도", "자기주식처분", "대표이사변경"],
    "거래소/상장유지": ["관리종목", "투자주의환기", "거래정지", "상장폐지", "불성실공시", "상장적격성"],
    "구조조정": ["감자", "자본감소", "회생", "파산", "합병", "분할", "영업양수도"],
}


CHECKLIST = {
    "자금조달": [
        "제3자배정 여부, 배정대상자, 납입 가능성, 발행가 할인율을 확인합니다.",
        "CB/BW의 전환가, 리픽싱, 콜옵션/풋옵션, 전환가능 기간과 물량을 확인합니다.",
        "기존 유증/CB가 실패·정정·연기된 이력이 있는지 확인합니다.",
    ],
    "지분/경영권": [
        "최대주주와 특수관계인 지분, 담보 제공, 최근 장내외 매매를 확인합니다.",
        "5% 보고자와 CB/BW 보유자의 이해관계가 경영권 거래와 연결되는지 확인합니다.",
        "대표이사/이사회 변동과 임시주총 안건을 확인합니다.",
    ],
    "거래소/상장유지": [
        "관리종목/환기/거래정지 사유와 해소 데드라인을 확인합니다.",
        "상장적격성 실질심사, 상장폐지 이의신청, 개선기간 여부를 확인합니다.",
        "불성실공시 벌점과 누적 벌점 리스크를 확인합니다.",
    ],
    "구조조정": [
        "감자·주식병합 후 주식 수, 기준가, 거래재개 일정을 확인합니다.",
        "회생·파산 사건은 종결/기각/취하 여부와 채권자 구조를 확인합니다.",
        "합병·분할·영업양수도는 자금 유출입과 우발채무 승계 여부를 확인합니다.",
    ],
}


def parse_yyyymmdd(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return None


def event_category(report_name: str) -> str | None:
    for category, keywords in CATEGORY_RULES.items():
        if any(keyword in report_name for keyword in keywords):
            return category
    return None


def build_event_digest(filings: list[dict[str, Any]], lookback_days: int = 365) -> dict[str, Any]:
    dates = [parsed for filing in filings if (parsed := parse_yyyymmdd(filing.get("rcept_dt")))]
    as_of = max(dates) if dates else date.today()
    buckets: dict[str, list[dict[str, Any]]] = {category: [] for category in CATEGORY_RULES}
    for filing in filings:
        report_name = (filing.get("report_nm") or "").strip()
        filing_date = parse_yyyymmdd(filing.get("rcept_dt"))
        category = event_category(report_name)
        if not report_name or not filing_date or not category:
            continue
        days_ago = max((as_of - filing_date).days, 0)
        if days_ago > lookback_days:
            continue
        buckets[category].append(
            {
                "rcept_dt": filing.get("rcept_dt"),
                "report_nm": report_name,
                "days_ago": days_ago,
                "rcp_no": filing.get("rcept_no"),
                "flr_nm": filing.get("flr_nm"),
            }
        )
    for rows in buckets.values():
        rows.sort(key=lambda row: row["days_ago"])

    checklist: list[str] = []
    for category, rows in buckets.items():
        if rows:
            checklist.extend(CHECKLIST[category])

    return {
        "as_of": as_of.isoformat(),
        "lookback_days": lookback_days,
        "counts": {category: len(rows) for category, rows in buckets.items()},
        "events": {category: rows[:8] for category, rows in buckets.items()},
        "checklist": list(dict.fromkeys(checklist))[:12],
    }
