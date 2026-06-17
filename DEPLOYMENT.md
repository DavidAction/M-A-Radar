# TL M&A Radar 운영 배포 가이드

## 1. 권장 운영 방식

항상 켜져 있는 환경은 아래 순서로 권장합니다.

1. Windows 사무실 PC/서버: Scheduled Task로 로그인 시 자동 실행
2. 클라우드 Windows Server: 같은 방식으로 자동 실행, 방화벽에서 8766 허용
3. Linux VPS 또는 NAS: Docker Compose로 `restart: unless-stopped` 운영

투자 검토용 내부 도구이므로 외부 인터넷에 공개할 때는 VPN, 사내망, Cloudflare Access, Basic Auth 리버스 프록시 중 하나를 먼저 붙이는 것을 권장합니다.

## 2. Windows 항상 켜짐 모드

```powershell
git clone https://github.com/DavidAction/M-A-Radar.git
cd M-A-Radar
powershell -ExecutionPolicy Bypass -File .\FIRST_RUN_WINDOWS.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\install_startup_server.ps1 -Lan -StartNow
```

접속 주소:

```text
http://<서버 내부 IP>:8766
```

중지/삭제:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall_startup_server.ps1
```

관리자 권한이 있는 Windows Server에서는 작업 스케줄러 방식도 사용할 수 있습니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_always_on_server.ps1 -Lan -StartNow
```

## 3. Linux VPS / Docker Compose

```bash
git clone https://github.com/DavidAction/M-A-Radar.git
cd M-A-Radar
cp .env.example .env
```

`.env`에 DART/Naver 키를 입력한 뒤:

```bash
docker compose up -d --build
docker compose logs -f radar
```

접속 주소:

```text
http://<서버 IP>:8766
```

데이터 파일은 `./tl_ma_radar/data` 볼륨에 유지됩니다.

## 4. 운영 후 확인할 API

```text
/api/config
/api/candidates
/api/top-review
/api/alerts
/api/export-deal-cards.docx?format=ic
```

## 5. 자동 갱신

Windows에서는 기존 일일 파이프라인 태스크를 함께 설치합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_daily_task.ps1 -At 18:30 -Mode full
```

Linux/Docker에서는 호스트 crontab에서 아래 명령을 매일 실행합니다.

```bash
cd /path/to/M-A-Radar && docker compose exec -T radar python scripts/run_pipeline.py --mode full --download-reports latest --news top
```
