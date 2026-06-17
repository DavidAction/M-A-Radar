# Engineering Handoff

## Product Goal

TL M&A Radar screens undervalued KOSDAQ companies below KRW 30B market cap and ranks candidates that can support TL Holdings' acquisition strategy.

Primary logic:

- find low-market-cap listed companies
- include managed/watch-list names as potential opportunity targets
- evaluate TL/Renes Material synergy
- identify white-knight need, control openness, CB/BW overhang, audit risk, and related-party structure potential
- manage candidates as a deal pipeline
- export IC-ready Word reports

## Main Entry Points

- App server: `app.py`
- UI: `static/index.html`, `static/app.js`, `static/styles.css`
- Candidate data: `tl_ma_radar/data/real_candidates.json`
- Workflows: `tl_ma_radar/data/candidate_workflows.json`
- Daily pipeline: `scripts/run_pipeline.py`

## Key Modules

- `tl_ma_radar/scoring.py`: base candidate scoring
- `tl_ma_radar/shortlist.py`: shortlist grouping and priority score
- `tl_ma_radar/deal_scenario.py`: KRW 30B capital raise and dilution scenario
- `tl_ma_radar/acquisition_judgment.py`: acquisition attractiveness and execution judgment
- `tl_ma_radar/investment_case.py`: IC-style control/synergy/financing/risk investment case
- `tl_ma_radar/report_intelligence.py`: DART report intelligence
- `tl_ma_radar/structured_extractors.py`: specialized extraction logic
- `tl_ma_radar/extraction_audit.py`: extraction confidence and tuning queue
- `tl_ma_radar/pipeline_dashboard.py`: owner/status/due-date pipeline board
- `tl_ma_radar/deal_report.py`: Word deal-card report generation
- `tl_ma_radar/notifier.py`: webhook and SMTP alert delivery

## Important API Endpoints

- `GET /api/candidates`
- `GET /api/candidates/<code>`
- `POST /api/candidates/<code>/workflow`
- `GET /api/shortlist`
- `GET /api/extraction-audit`
- `GET /api/pipeline-dashboard`
- `GET /api/data-quality`
- `POST /api/data-quality/remediate`
- `GET /api/alerts`
- `POST /api/send-alerts`
- `GET /api/export-deal-cards.docx`
- `GET /api/candidates/<code>/ic-summary.docx`

## Development Setup

```powershell
git clone https://github.com/DavidAction/M-A-Radar.git
cd M-A-Radar
copy .env.example .env
powershell -ExecutionPolicy Bypass -File .\FIRST_RUN_WINDOWS.ps1
powershell -ExecutionPolicy Bypass -File .\start_radar.ps1
```

Open:

```text
http://127.0.0.1:8766
```

## Verification

Run these before submitting work:

```powershell
python -m compileall app.py scripts tl_ma_radar
node --check static/app.js
python scripts\send_alert_notifications.py --dry-run --limit 5
powershell -ExecutionPolicy Bypass -File scripts\run_daily_pipeline.ps1 -Mode offline -DryRun
```

For UI changes, open the app and check:

- shortlist pagination
- candidate detail card
- extraction audit panel
- pipeline board panel
- notification status panel
- Word report download

## Current Product Priorities

1. Improve DART source extraction precision for largest shareholder tables, CB/BW terms, audit opinions, and related-party transactions.
2. Add human validation fields for extraction corrections and feed them back into parser tuning.
3. Keep report outputs IC-ready: concise thesis, deal conditions, red flags, and 100-day value plan.
4. Make the cloud refresh path stable before adding heavier AI summarization.

## Vendor Rules

- Do not commit `.env`.
- Do not remove data files unless explicitly approved.
- Preserve existing candidate workflow notes.
- Keep UI dark mode.
- Push every meaningful completed task to GitHub.
