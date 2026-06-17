from __future__ import annotations

import json
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


def _setting(settings: object, name: str, default: object = "") -> object:
    return getattr(settings, name, default)


def _text(value: object) -> str:
    return str(value or "").strip()


def notification_status(root: Path, settings: object) -> dict[str, Any]:
    notification_dir = root / "tl_ma_radar" / "data" / "notifications"
    latest = notification_dir / "latest.json"
    latest_payload: dict[str, Any] | None = None
    if latest.exists():
        try:
            latest_payload = json.loads(latest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            latest_payload = {"status": "invalid_latest_file"}

    webhook_configured = bool(_text(_setting(settings, "alert_webhook_url")))
    smtp_configured = bool(_text(_setting(settings, "smtp_host")) and _text(_setting(settings, "alert_email_to")))
    configured = webhook_configured or smtp_configured
    return {
        "status": "configured" if configured else "not_configured",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "channels": {
            "webhook": webhook_configured,
            "email": smtp_configured,
        },
        "targets": {
            "webhook": _mask_url(_text(_setting(settings, "alert_webhook_url"))),
            "email_to": _text(_setting(settings, "alert_email_to")) or "-",
            "smtp_host": _text(_setting(settings, "smtp_host")) or "-",
        },
        "latest": latest_payload,
        "ready_for_real_send": configured,
        "next_step": (
            "Real alert delivery is enabled. Use /api/send-alerts with dry_run=false or the daily pipeline."
            if configured
            else "Set ALERT_WEBHOOK_URL or SMTP settings in .env/GitHub Secrets, then run scripts/send_alert_notifications.py --dry-run."
        ),
    }


def _mask_url(url: str) -> str:
    if not url:
        return "-"
    if len(url) <= 24:
        return "***"
    return f"{url[:16]}...{url[-8:]}"


def build_alert_message(alert_payload: dict[str, Any], limit: int = 20) -> str:
    summary = alert_payload.get("summary") if isinstance(alert_payload.get("summary"), dict) else {}
    severity = summary.get("severity") if isinstance(summary.get("severity"), dict) else {}
    alerts = [row for row in (alert_payload.get("items") or alert_payload.get("alerts") or []) if isinstance(row, dict)]
    lines = [
        "TL M&A Radar Daily Alerts",
        f"- Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"- Total alerts: {summary.get('total', summary.get('total_alerts', len(alerts)))}",
        f"- Critical: {severity.get('critical', summary.get('critical', 0))} / High: {severity.get('high', summary.get('high', 0))}",
        "",
        "Top alerts",
    ]
    for index, row in enumerate(alerts[:limit], 1):
        lines.append(
            f"{index}. [{row.get('severity', '-')}] {row.get('name', '-')} ({row.get('code', '-')}) "
            f"- {row.get('title') or row.get('message') or '-'}"
        )
    if len(alerts) > limit:
        lines.append(f"...and {len(alerts) - limit} more")
    return "\n".join(lines)


def send_alert_notifications(
    root: Path,
    alert_payload: dict[str, Any],
    settings: object,
    *,
    dry_run: bool = False,
    limit: int = 20,
) -> dict[str, Any]:
    message = build_alert_message(alert_payload, limit=limit)
    channels: list[dict[str, Any]] = []
    webhook_url = _text(_setting(settings, "alert_webhook_url"))
    smtp_host = _text(_setting(settings, "smtp_host"))
    email_to = _text(_setting(settings, "alert_email_to"))

    if webhook_url:
        channels.append(_send_webhook(webhook_url, message, dry_run=dry_run))
    if smtp_host and email_to:
        channels.append(_send_email(settings, message, dry_run=dry_run))
    if not channels:
        channels.append(
            {
                "channel": "preview",
                "status": "not_configured",
                "detail": "Webhook or SMTP settings are not configured.",
                "next_step": "Set ALERT_WEBHOOK_URL or SMTP settings before real delivery.",
            }
        )

    status = "ok" if any(row.get("status") in {"sent", "dry_run"} for row in channels) else "not_configured"
    if any(row.get("status") == "error" for row in channels):
        status = "partial_error"
    result = {
        "status": status,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "channels": channels,
        "preview": message,
    }
    notification_dir = root / "tl_ma_radar" / "data" / "notifications"
    notification_dir.mkdir(parents=True, exist_ok=True)
    (notification_dir / "latest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _send_webhook(url: str, message: str, *, dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return {"channel": "webhook", "status": "dry_run", "target": _mask_url(url)}
    payload = json.dumps({"text": message}, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=payload, headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    try:
        with urlopen(request, timeout=20) as response:
            return {"channel": "webhook", "status": "sent", "target": _mask_url(url), "http_status": response.status}
    except URLError as exc:
        return {"channel": "webhook", "status": "error", "target": _mask_url(url), "error": str(exc)}


def _send_email(settings: object, message: str, *, dry_run: bool) -> dict[str, Any]:
    host = _text(_setting(settings, "smtp_host"))
    port = int(_setting(settings, "smtp_port", 587) or 587)
    email_to = _text(_setting(settings, "alert_email_to"))
    email_from = _text(_setting(settings, "alert_email_from")) or email_to
    username = _text(_setting(settings, "smtp_username"))
    password = _text(_setting(settings, "smtp_password"))
    use_tls = bool(_setting(settings, "smtp_use_tls", True))
    if dry_run:
        return {"channel": "email", "status": "dry_run", "target": email_to, "smtp_host": host}

    msg = EmailMessage()
    msg["Subject"] = "TL M&A Radar Daily Alerts"
    msg["From"] = email_from
    msg["To"] = email_to
    msg.set_content(message)
    try:
        if use_tls:
            context = ssl.create_default_context()
            with smtplib.SMTP(host, port, timeout=25) as server:
                server.starttls(context=context)
                if username and password:
                    server.login(username, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=25) as server:
                if username and password:
                    server.login(username, password)
                server.send_message(msg)
        return {"channel": "email", "status": "sent", "target": email_to, "smtp_host": host}
    except OSError as exc:
        return {"channel": "email", "status": "error", "target": email_to, "smtp_host": host, "error": str(exc)}
