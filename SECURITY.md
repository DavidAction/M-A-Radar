# Security and Data Handling

## Secret Policy

Never commit real API keys or SMTP passwords.

Local secrets belong in `.env`, which is ignored by Git.

Production secrets belong in:

- GitHub Actions secrets
- cloud hosting environment variables
- a managed secret store

## Current Sensitive Values

The system can use:

- `DART_API_KEY`
- `NAVER_CLIENT_ID`
- `NAVER_CLIENT_SECRET`
- `ALERT_WEBHOOK_URL`
- SMTP credentials

Rotate any key that was pasted into chat or shared with a vendor.

## Repository Data

The repository may contain generated M&A candidate data, DART metadata, scoring results, and workflow notes.

Before sharing with external vendors, review:

- `tl_ma_radar/data/real_candidates.json`
- `tl_ma_radar/data/candidate_workflows.json`
- `tl_ma_radar/data/quality_reports`
- `tl_ma_radar/data/pipeline_runs`

Do not include private deal notes unless the vendor is authorized.

## Access Control

Recommended GitHub settings:

- private repository
- branch protection on `main`
- required PR review for external vendors
- no direct write access for temporary contractors
- use deploy keys or fine-scoped tokens only when needed

## Alert Channels

Webhook URLs often contain embedded secrets.

Treat `ALERT_WEBHOOK_URL` like a password. Do not paste it into issues, commits, screenshots, or vendor documents.

## Operational Checks

Run before handoff:

```powershell
python -m compileall app.py scripts tl_ma_radar
node --check static/app.js
python scripts\send_alert_notifications.py --dry-run --limit 5
```

Confirm `.env` is not staged:

```powershell
git status --short
git check-ignore .env
```
