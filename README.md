# TL M&A Radar

코스닥 시가총액 300억 원 이하 기업 중 티엘홀딩스와 르네스머테리얼의 1단계 핵심 네트워크 관점에서 인수 후보를 탐색, 스코어링, 추적, 보고서화하는 로컬 M&A 레이더입니다.

## 목적

- 코스닥 중심 저시총 상장사 후보 발굴
- 관리종목/투자주의환기종목을 리스크가 아닌 기회군으로 별도 포함
- 본업 안정성, 저평가, 지배구조, 자금조달 압박, 백기사 필요도, TL/르네스 시너지 평가
- DART 공시, 사업보고서/감사보고서, 최근 6개월 뉴스, 후보 상태/메모/액션을 하나의 딜 파이프라인으로 관리
- 후보별 딜카드와 전체 후보 딜카드 패키지를 Word 보고서로 다운로드

## 현재 구성

- Backend: Python 표준 라이브러리 기반 HTTP 서버
- Frontend: 정적 HTML/CSS/JavaScript 다크모드 UI
- Data: `tl_ma_radar/data/real_candidates.json` 중심 로컬 데이터셋
- News: Naver Search API 우선, Google News RSS 보조
- Disclosure: OpenDART API 기반 공시/보고서 수집
- Report: DOCX OOXML 직접 생성 방식, 별도 Word 의존성 없이 다운로드 가능

## 빠른 실행

```powershell
cd <repo>\tl-ma-radar
powershell -ExecutionPolicy Bypass -File .\FIRST_RUN_WINDOWS.ps1
powershell -ExecutionPolicy Bypass -File .\start_radar.ps1
```

브라우저에서 `http://127.0.0.1:8766`을 엽니다.

다른 노트북/데스크탑에서 처음 실행하는 자세한 절차는 `OTHER_PC_SETUP.md`를 참고합니다.

같은 내부 네트워크의 다른 컴퓨터에서 보려면 실행 PC에서 아래처럼 시작합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\start_radar.ps1 -Lan
```

다른 컴퓨터에서는 실행 PC의 내부 IP를 사용해 `http://<실행PC-IP>:8766`으로 접속합니다. Windows 방화벽에서 Python 또는 포트 8766 허용이 필요할 수 있습니다.

## 환경변수

실제 키는 `.env`에 넣고 GitHub에는 올리지 않습니다. `.env.example`을 복사해서 사용합니다.

```text
DART_API_KEY=
NAVER_CLIENT_ID=
NAVER_CLIENT_SECRET=
CAPITAL_RAISE_KRW=30000000000
TARGET_MARKET=KOSDAQ
MARKET_CAP_LIMIT_KRW=30000000000
```

## 데이터 갱신

기존 수집 데이터와 공시 분석을 기준으로 빠르게 재분석합니다.

```powershell
python scripts\run_pipeline.py --mode offline --max-reports 2 --memo-limit 30
```

DART, 후보 데이터, 뉴스까지 함께 갱신합니다.

```powershell
python scripts\run_pipeline.py --mode full --begin 20250101 --end 20260617 --download-reports latest --news top
```

전체 후보 뉴스까지 폭넓게 갱신합니다.

```powershell
python scripts\run_pipeline.py --mode full --begin 20250101 --end 20260617 --download-reports latest --news all
```

뉴스만 다시 수집할 때는 아래 명령을 사용합니다.

```powershell
python scripts\collect_news.py --months 6 --max-articles 30
```

특정 회사만 다시 수집할 수도 있습니다.

```powershell
python scripts\collect_news.py --code 121850 --code 247660
```

## 보고서 다운로드

앱 상단 숏리스트 영역의 `Word Report` 버튼은 전체 후보 딜카드 패키지를 내려받습니다.

- 전체 딜카드 보고서: `/api/export-deal-cards.docx`
- 단일 회사 딜카드 보고서: `/api/candidates/<종목코드>/deal-card.docx`
- 숏리스트 CSV: `/api/export-shortlist.csv`
- 변화 모니터링 CSV: `/api/export-monitoring.csv`

Word 보고서는 글로벌 컨설팅펌 스타일의 의사결정 브리프 구조를 따릅니다.

- Cover / Executive Summary
- 후보별 스코어카드
- 투자 논거
- 리스크 및 확인 사항
- 보고서/뉴스 근거
- 최근 뉴스 헤드라인
- 실사 질문

HWP가 필요한 경우 한컴오피스에서 DOCX를 열어 HWP로 저장하는 방식이 현재 가장 안정적입니다. 앱은 우선 Word DOCX를 표준 산출물로 제공합니다.

## 후보 상태 관리

상세 화면에서 후보별로 아래 정보를 저장할 수 있습니다.

- 상태: 미검토, 관심, 제외, 추적, 접촉, 실사중
- 연락 상태: 미접촉, 접촉준비, 접촉완료, 자료요청, 미팅예정, 보류
- 담당자
- 다음 액션
- 검토 기한
- 메모

저장 데이터는 `tl_ma_radar/data/candidate_workflow.json`에 기록됩니다.

## GitHub 인수인계

이 저장소는 `.env`, 로그, 브라우저 프로필, DART 원문 PDF/HTML 캐시를 커밋하지 않도록 설정되어 있습니다. 외주사 또는 Claude Code가 이어받을 때는 아래 순서가 가장 안전합니다.

1. GitHub에서 빈 저장소를 만듭니다.
2. 이 폴더에서 원격 저장소를 연결합니다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_github_remote.ps1 -RemoteUrl https://github.com/<owner>/<repo>.git -InstallAutoPushHook -Push
```

3. 이후 작업마다 아래 명령을 실행하면 변경사항을 커밋하고 GitHub로 푸시합니다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\git_auto_push.ps1 -Message "작업 내용 요약"
```

`-InstallAutoPushHook`을 사용하면 로컬에서 `git commit`이 발생할 때마다 post-commit 훅이 자동으로 `git push`를 실행합니다. Codex 작업 후에는 위 `git_auto_push.ps1`을 쓰는 방식이 가장 명시적이고 안전합니다.

## 외부 개발자 체크리스트

- `.env.example`을 `.env`로 복사하고 DART/Naver 키를 입력
- `setup_windows.ps1` 실행
- `start_radar.ps1`로 로컬 서버 확인
- `/api/config`, `/api/candidates`, `/api/shortlist` 응답 확인
- `/api/export-deal-cards.docx` 다운로드 확인
- `python -m compileall app.py tl_ma_radar scripts` 실행
- `node --check static\app.js` 실행

## 주요 폴더

- `app.py`: 로컬 HTTP API 서버
- `static/`: 다크모드 프론트엔드
- `tl_ma_radar/`: 스코어링, 공시/뉴스 분석, 딜 시그널, 보고서 생성 모듈
- `tl_ma_radar/data/`: 후보/뉴스/워크플로우/모니터링 데이터
- `scripts/`: 수집, 분석, 자동실행, GitHub 인수인계 스크립트

## 주의사항

본 서비스는 후보 탐색과 딜 검토를 위한 내부 의사결정 보조 도구입니다. 인수, 유상증자, 백기사 구조, 특수관계 거래, 공시 의무, 자본시장법 이슈는 반드시 회계법인, 법무법인, 투자은행 자문과 함께 별도 검토해야 합니다.

## 2026-06 운영 고도화 기능

이번 버전에는 외주사나 Claude Code가 바로 이어서 작업할 수 있도록 아래 운영 레이어가 추가되었습니다.

- 데이터 신뢰도: 후보별 DART 공시 최신성, 뉴스 표본/최신성, 보고서 근거, 사업 키워드, 파이프라인 상태를 100점 기준으로 점검합니다.
- 스코어 튜닝: 코이즈, 나노씨엠에스, 아이씨에이치, 베셀을 벤치마크로 고정하고 상위 20개 후보의 과대평가/과소평가 가능성을 검수합니다.
- 파이프라인 이력: 후보 상태, 연락 상태, 담당자, 기한, 다음 액션, 메모 변경 이력이 자동 저장됩니다.
- Word 보고서: 전체/개별 딜카드에 Investment Committee Lens, 데이터 신뢰도, 파이프라인 상태, 변경 이력이 반영됩니다.
- IC 패키지: 후보별 IC 상정 여부, 300억 유증 딜 구조, 실사 워크플랜, 리스크 완화, 100일 계획을 자동 생성합니다.
- DART 원문 인텔리전스: 감사/계속기업, 관리/환기, 자본잠식, CB/BW, 특수관계, 매출채권 리스크를 구조화합니다.
- 뉴스 이벤트 타임라인: 최대주주/경영권, 유상증자/CB/BW, 감사/상장유지, 소송, 공급계약, 실적, 시너지 이벤트로 분류합니다.
- 300억 딜 시나리오: 단순 신규 지분율과 CB/BW 오버행을 반영한 보수적 지분율, 경영권 확보 가능성을 함께 보여줍니다.
- AI형 투자 메모: 외부 AI API 없이 현재 데이터 기반 투자 메모, 반론, 법무/회계 요청서 초안을 생성합니다.
- 팀 이관: `/api/team-ops`에서 GitHub 연결, 자동 푸시 훅, 데이터 파일, 다른 PC 실행 준비 상태를 점검합니다.
- SQLite Export: `/api/export-pipeline.sqlite`로 후보/뉴스/워크플로 데이터를 외부 분석툴에 넘길 수 있습니다.

주요 API:

```text
/api/data-quality
/api/score-tuning?limit=20
/api/ic-packages?limit=12
/api/automation-plan
/api/team-ops
/api/export-pipeline.sqlite
/api/export-deal-cards.docx?format=ic
/api/candidates/121850/deal-card.docx?format=ic
```

다른 PC에서 쓰는 기본 절차:

```powershell
git clone https://github.com/DavidAction/M-A-Radar.git
cd M-A-Radar
powershell -ExecutionPolicy Bypass -File .\FIRST_RUN_WINDOWS.ps1
powershell -ExecutionPolicy Bypass -File .\start_radar.ps1
```

새 PC에서 최신 DART/뉴스 수집까지 하려면 `.env`에 `DART_API_KEY`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`을 입력한 뒤 실행합니다.
