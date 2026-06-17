# Cloud Operations Guide

This guide is for running TL M&A Radar as an always-on service instead of a local-only desktop app.

## Recommended Production Shape

Use a small cloud VM or container service with persistent storage.

- App: Python HTTP server from `app.py`
- Data refresh: `scripts/run_pipeline.py`
- Scheduler: GitHub Actions or cloud cron
- Secrets: environment variables, never committed `.env`
- Persistent data: `tl_ma_radar/data`

## Required Secrets

Set these as GitHub Actions secrets or hosting platform secrets.

```text
DART_API_KEY
NAVER_CLIENT_ID
NAVER_CLIENT_SECRET
ALERT_WEBHOOK_URL
ALERT_EMAIL_TO
ALERT_EMAIL_FROM
SMTP_HOST
SMTP_PORT
SMTP_USERNAME
SMTP_PASSWORD
SMTP_USE_TLS
APP_USERNAME
APP_PASSWORD
```

Only the first three are required for data collection. Alert secrets are optional.
`APP_USERNAME` and `APP_PASSWORD` are optional for local use, but should be set for any internet-facing deployment.

## GitHub Actions Daily Refresh

The repository includes `.github/workflows/daily-refresh.yml`.

It runs daily at `09:30 UTC`, which is `18:30 KST`, and can also be triggered manually from the GitHub Actions tab.

What it does:

- refresh KOSDAQ candidates
- pull DART filings and latest report artifacts
- save report text/PDF where available
- collect recent news
- backfill business keywords from report text
- seed top 30 workflow owners/actions/deadlines
- seed top 30 extraction feedback review state
- regenerate monitoring and quality reports
- export the Top30 calibration report
- send alert notifications when a channel is configured
- commit refreshed data artifacts back to GitHub

## Docker Run

```bash
docker build -t tl-ma-radar .
docker run --rm -p 8765:8765 --env-file .env tl-ma-radar
```

Open:

```text
http://localhost:8765
```

For a VM, run it behind Nginx/Caddy and expose HTTPS.

## Render / Railway / Fly.io

Use these generic settings:

- Build command: `pip install -r requirements.txt`
- Start command: `python app.py --host 0.0.0.0 --port $PORT`
- Disk: attach persistent storage to `tl_ma_radar/data` if the platform supports it
- Environment: add all secrets from `.env.example`

If the platform does not support persistent disk, use GitHub Actions as the refresh writer and let the app serve the committed dataset.

## VM Systemd Example

```ini
[Unit]
Description=TL MA Radar
After=network.target

[Service]
WorkingDirectory=/opt/M-A-Radar
EnvironmentFile=/opt/M-A-Radar/.env
ExecStart=/usr/bin/python3 app.py --host 0.0.0.0 --port 8765
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

## Health Checks

Check these URLs after deploy:

- `/api/config`
- `/api/candidates`
- `/api/extraction-audit`
- `/api/pipeline-dashboard`
- `/api/notification-status`
- `/api/calibration?limit=30`

If `APP_USERNAME` and `APP_PASSWORD` are set, the browser will prompt for a login before serving the UI and API.

## Alert Delivery

Webhook payload is:

```json
{"text": "TL M&A Radar Daily Alerts..."}
```

SMTP uses a plain-text email with the same alert summary.

Use `/api/send-alerts` with `{"dry_run": true}` before enabling real delivery.

Real delivery checklist:

1. Add either `ALERT_WEBHOOK_URL` or the SMTP variables to GitHub Secrets or the server `.env`.
2. Run a local preview:

```bash
python scripts/send_alert_notifications.py --dry-run --limit 5
```

3. Confirm `/api/notification-status` returns `ready_for_real_send: true`.
4. Trigger a real send from the deployed server:

```bash
curl -X POST "$APP_BASE_URL/api/send-alerts" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": false, "limit": 10}'
```

5. Check `tl_ma_radar/data/notifications/latest.json` for the delivery result.
