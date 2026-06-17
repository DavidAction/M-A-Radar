# 다른 노트북/데스크탑에서 실행하는 방법

## 1. 필수 설치

Windows 기준으로 아래 두 가지가 필요합니다.

- Git for Windows
- Python 3.11 이상

Python 설치 시 `Add python.exe to PATH` 옵션을 켜는 것이 좋습니다.

## 2. GitHub에서 받기

```powershell
cd C:\Users\<사용자>\Documents
git clone https://github.com/DavidAction/M-A-Radar.git
cd M-A-Radar
```

GitHub 업로드가 아직 완료되지 않은 경우에는 전달받은 `.bundle` 파일로도 복원할 수 있습니다.

```powershell
git clone tl-ma-radar-handoff-643d655.bundle M-A-Radar
cd M-A-Radar
```

## 3. 최초 실행

```powershell
powershell -ExecutionPolicy Bypass -File .\FIRST_RUN_WINDOWS.ps1
```

이 스크립트가 하는 일:

- Python 가상환경 `.venv` 생성
- 필요한 패키지 설치
- `.env.example`을 `.env`로 복사
- 후보 데이터/뉴스 데이터/DART filing JSON 존재 여부 점검
- 실행 URL 안내

## 4. API 키 입력

새 PC에서 최신 DART/뉴스 갱신까지 하려면 `.env` 파일에 키를 넣습니다.

```text
DART_API_KEY=...
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
```

키가 없어도 기존 커밋에 포함된 후보/뉴스/공시 JSON 기준으로 앱 조회와 Word Report 다운로드는 가능합니다.

## 5. 앱 실행

```powershell
powershell -ExecutionPolicy Bypass -File .\start_radar.ps1
```

브라우저에서 엽니다.

```text
http://127.0.0.1:8766
```

## 6. 같은 네트워크의 다른 컴퓨터에서 보기

앱을 실행하는 PC에서:

```powershell
powershell -ExecutionPolicy Bypass -File .\start_radar.ps1 -Lan
```

다른 PC에서:

```text
http://<앱 실행 PC의 내부 IP>:8766
```

접속이 안 되면 Windows Defender Firewall에서 Python 또는 TCP 8766 포트를 허용합니다.

## 7. 최신 데이터 갱신

빠른 오프라인 재분석:

```powershell
python scripts\run_pipeline.py --mode offline --max-reports 2 --memo-limit 30
```

DART와 뉴스까지 갱신:

```powershell
python scripts\run_pipeline.py --mode full --download-reports latest --news top
```

## 8. Word 보고서 다운로드

앱에서 `Word Report` 버튼을 누르거나 아래 주소를 직접 엽니다.

```text
http://127.0.0.1:8766/api/export-deal-cards.docx
```

회사별 보고서:

```text
http://127.0.0.1:8766/api/candidates/<종목코드>/deal-card.docx
```

예:

```text
http://127.0.0.1:8766/api/candidates/121850/deal-card.docx
```

## 9. GitHub 자동 업데이트

이 PC에서 작업 후 자동으로 GitHub에 올리려면:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_github_remote.ps1 -RemoteUrl https://github.com/DavidAction/M-A-Radar.git -InstallAutoPushHook
```

작업 후 명시적으로 커밋/푸시:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\git_auto_push.ps1 -Message "작업 내용 요약"
```

민감한 API 키는 `.env`에만 두고 GitHub에 올리지 않습니다.

## 10. 새 운영 기능 확인

실행 후 브라우저 첫 화면에서 아래 3개 패널이 보여야 합니다.

- 데이터 신뢰도: 후보 데이터가 투자심의에 바로 쓸 수 있는 수준인지 확인합니다.
- 스코어 튜닝: 상위 20개와 코이즈/나노씨엠에스/아이씨에이치/베셀 벤치마크를 검수합니다.
- IC 패키지: IC 상정 후보, 조건부 후보, 프리-IC 관찰 후보를 보고 다음 액션을 정합니다.
- 팀 운영/이관: GitHub 원격 저장소, 자동 푸시 훅, 데이터 파일, 실행 준비 상태를 확인합니다.

외부 분석이나 외주사 전달용 데이터베이스가 필요하면 아래 주소에서 SQLite 파일을 내려받습니다.

```text
http://127.0.0.1:8766/api/export-pipeline.sqlite
```

투자심의용 Word 보고서는 아래 주소를 사용합니다.

```text
http://127.0.0.1:8766/api/export-deal-cards.docx?format=ic
```
