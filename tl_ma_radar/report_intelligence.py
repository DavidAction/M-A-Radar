from __future__ import annotations

from typing import Any


def _analysis(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("report_analysis")
    return value if isinstance(value, dict) else {}


def _signals(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("deal_signals")
    return value if isinstance(value, dict) else {}


def _has_any(values: list[str], terms: list[str]) -> bool:
    text = " ".join(values)
    return any(term in text for term in terms)


def _finding(
    category: str,
    severity: str,
    title: str,
    evidence: list[str],
    implication: str,
    next_step: str,
) -> dict[str, Any]:
    return {
        "category": category,
        "severity": severity,
        "title": title,
        "evidence": evidence[:5],
        "implication": implication,
        "next_step": next_step,
    }


def _severity_rank(value: str) -> int:
    return {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(value, 0)


def build_report_intelligence(item: dict[str, Any], filings: list[dict[str, Any]]) -> dict[str, Any]:
    analysis = _analysis(item)
    signals = _signals(item)
    flags = [str(flag) for flag in item.get("status_flags") or []]
    audit = [str(value) for value in analysis.get("audit_signals") or []]
    financing = [str(value) for value in analysis.get("financing_signals") or []]
    control = [str(value) for value in analysis.get("control_signals") or []]
    related = [str(value) for value in analysis.get("related_party_signals") or []]
    exit_structure = [str(value) for value in analysis.get("exit_structure_signals") or []]
    customer = [str(value) for value in analysis.get("customer_signals") or []]
    extracts = analysis.get("structured_extracts") or {}
    audit_extract = extracts.get("audit_opinion") or {}
    cb_extract = extracts.get("convertible_bonds") or {}
    related_extract = extracts.get("related_party_transactions") or {}
    shareholder_candidates = extracts.get("largest_shareholder_candidates") or []
    findings: list[dict[str, Any]] = []

    if (
        "계속기업불확실성" in flags
        or _has_any(audit, ["계속기업", "불확실"])
        or audit_extract.get("opinion") in {"계속기업 불확실성", "의견거절", "부적정", "한정"}
    ):
        findings.append(
            _finding(
                "감사/계속기업",
                "critical",
                "계속기업 불확실성 확인 필요",
                [audit_extract.get("opinion")] + audit + flags,
                "인수 후 유상증자 자금이 채무상환과 운영자금으로 흡수될 수 있어 딜 구조 선행조건이 필요합니다.",
                "감사보고서 원문, 현금흐름, 단기차입금 만기, 이후 공시를 묶어 회계법인 검토를 진행합니다.",
            )
        )
    if "관리종목" in flags or "투자주의환기" in flags or "거래정지" in flags:
        findings.append(
            _finding(
                "상장유지/거래",
                "high",
                "관리/환기/거래정지 관련 공시 리스크",
                [flag for flag in flags if flag in {"관리종목", "투자주의환기", "거래정지"}],
                "백기사 기회일 수 있지만 일정 지연, 거래정지 장기화, 투자자 보호 이슈가 생길 수 있습니다.",
                "거래소 지정 사유, 해소 요건, 다음 심사 일정을 DART와 거래소 공시로 확인합니다.",
            )
        )
    if "자본잠식" in flags or _has_any(financing, ["자본잠식", "감자"]):
        findings.append(
            _finding(
                "재무구조",
                "high",
                "자본잠식/감자 가능성",
                financing or flags,
                "300억 유증 전후 자본구조가 크게 바뀌며 기존 주주와 전환증권 보유자 이해관계가 충돌할 수 있습니다.",
                "유증 전 감자 필요성, 감자비율, 완전희석 지분율을 동일 표로 산정합니다.",
            )
        )
    if financing or "CB/BW공시" in flags or "유상증자공시" in flags or cb_extract.get("has_convertible"):
        findings.append(
            _finding(
                "자금조달/희석",
                "high" if "CB/BW공시" in flags else "medium",
                "CB/BW 및 유상증자 오버행",
                financing + list((cb_extract.get("counts") or {}).keys()) + [flag for flag in flags if flag in {"CB/BW공시", "유상증자공시", "감자공시"}],
                "전환가액 조정, 미상환 전환권, 보호예수 조건에 따라 경영권 확보 지분율이 달라집니다.",
                "미상환 CB/BW, 전환가액, 리픽싱, 콜옵션/풋옵션, 투자자별 보유분을 캡테이블에 반영합니다.",
            )
        )
    if control or "최대주주변경" in flags:
        findings.append(
            _finding(
                "지배구조",
                "medium",
                "최대주주/지분 분산 및 경영권 협상 포인트",
                control + [flag for flag in flags if flag == "최대주주변경"],
                "최대주주 지분율과 우호지분 구조에 따라 제3자배정만으로는 경영권 안정성이 달라질 수 있습니다.",
                "최대주주, 특수관계인, 5% 이상 주주, 담보/질권 설정 여부를 확인합니다.",
            )
        )
    if related or "특수관계거래" in flags or related_extract.get("has_related_party"):
        findings.append(
            _finding(
                "특수관계/엑시트 구조",
                "high",
                "관계사/특수관계 거래 검토 필요",
                related + list((related_extract.get("counts") or {}).keys()) + [flag for flag in flags if flag == "특수관계거래"],
                "자회사·관계사·자녀 회사 인수 방식은 공정가치, 이사회 승인, 공시, 세무 리스크가 핵심입니다.",
                "대상 자산의 독립 가치평가, 이해상충 절차, 공시 문안, 세무 검토 메모를 사전에 준비합니다.",
            )
        )
    if customer or "매출채권검증필요" in flags:
        findings.append(
            _finding(
                "영업/매출채권",
                "medium",
                "매출처와 매출채권 실재성 검증",
                customer + [flag for flag in flags if flag == "매출채권검증필요"],
                "본업이 탄탄한 후보인지 판단하려면 주요 매출처, 회수기간, 장기미수 여부가 중요합니다.",
                "상위 매출처 계약서, 매출채권 연령표, 회수 내역, 반품/클레임을 샘플링합니다.",
            )
        )
    if exit_structure:
        findings.append(
            _finding(
                "구조 활용",
                "medium",
                "자회사/관계사/사업양수도 구조 활용 가능성",
                exit_structure,
                "인수 후 추가 자산 편입이나 관계사 거래 구조를 설계할 여지가 있습니다.",
                "편입 대상 회사의 매출, 이익, 특수관계, 공정가치 평가 가능성을 별도 리스트업합니다.",
            )
        )

    if not findings:
        findings.append(
            _finding(
                "기본 확인",
                "low",
                "중대 보고서 신호 미식별",
                [],
                "자동 추출 기준 중대 신호는 제한적이나 원문 검토 전 확정 판단은 피해야 합니다.",
                "최신 사업보고서, 감사보고서, 분기보고서 원문을 샘플링합니다.",
            )
        )

    findings.sort(key=lambda row: _severity_rank(row["severity"]), reverse=True)
    severity = findings[0]["severity"]
    filing_names = [str(row.get("report_nm") or "") for row in filings[:5] if row.get("report_nm")]
    return {
        "severity": severity,
        "finding_count": len(findings),
        "findings": findings[:8],
        "source": {
            "filing_count": len(filings),
            "latest_filings": filing_names,
            "reports_analyzed": analysis.get("reports_analyzed") or [],
            "evidence_strength": analysis.get("evidence_strength"),
            "structured_extracts": {
                "audit_opinion": audit_extract,
                "convertible_bonds": cb_extract,
                "related_party_transactions": related_extract,
                "largest_shareholder_candidates": shareholder_candidates[:5],
            },
        },
        "checklist": [
            "감사의견/계속기업 문단 원문 확인",
            "관리종목/환기/거래정지 지정 및 해소 요건 확인",
            "CB/BW·유상증자·감자 이력과 미상환 잔액 확인",
            "최대주주·특수관계인·담보/질권 지분 확인",
            "특수관계 거래와 관계사 인수 구조의 공정가치 검토",
        ],
        "signals": {
            "deal_window": signals.get("deal_window"),
            "white_knight_need": signals.get("white_knight_need"),
            "control_signals": control,
            "financing_signals": financing,
            "related_party_signals": related,
        },
    }
