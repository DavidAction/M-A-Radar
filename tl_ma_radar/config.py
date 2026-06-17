from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    dart_api_key: str
    naver_client_id: str
    naver_client_secret: str
    capital_raise_krw: int
    target_market: str
    market_cap_limit_krw: int
    app_base_url: str
    alert_webhook_url: str
    alert_email_to: str
    alert_email_from: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_use_tls: bool
    app_username: str
    app_password: str


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _int_value(values: dict[str, str], key: str, default: int) -> int:
    raw = os.getenv(key) or values.get(key)
    if not raw:
        return default
    return int(raw.replace("_", "").replace(",", ""))


def _bool_value(values: dict[str, str], key: str, default: bool) -> bool:
    raw = os.getenv(key) or values.get(key)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def get_settings(root: Path) -> Settings:
    env_values = _parse_env_file(root / ".env")
    return Settings(
        dart_api_key=os.getenv("DART_API_KEY") or env_values.get("DART_API_KEY", ""),
        naver_client_id=os.getenv("NAVER_CLIENT_ID") or env_values.get("NAVER_CLIENT_ID", ""),
        naver_client_secret=os.getenv("NAVER_CLIENT_SECRET") or env_values.get("NAVER_CLIENT_SECRET", ""),
        capital_raise_krw=_int_value(env_values, "CAPITAL_RAISE_KRW", 30_000_000_000),
        target_market=os.getenv("TARGET_MARKET") or env_values.get("TARGET_MARKET", "KOSDAQ"),
        market_cap_limit_krw=_int_value(env_values, "MARKET_CAP_LIMIT_KRW", 30_000_000_000),
        app_base_url=os.getenv("APP_BASE_URL") or env_values.get("APP_BASE_URL", "http://127.0.0.1:8765"),
        alert_webhook_url=os.getenv("ALERT_WEBHOOK_URL") or env_values.get("ALERT_WEBHOOK_URL", ""),
        alert_email_to=os.getenv("ALERT_EMAIL_TO") or env_values.get("ALERT_EMAIL_TO", ""),
        alert_email_from=os.getenv("ALERT_EMAIL_FROM") or env_values.get("ALERT_EMAIL_FROM", ""),
        smtp_host=os.getenv("SMTP_HOST") or env_values.get("SMTP_HOST", ""),
        smtp_port=_int_value(env_values, "SMTP_PORT", 587),
        smtp_username=os.getenv("SMTP_USERNAME") or env_values.get("SMTP_USERNAME", ""),
        smtp_password=os.getenv("SMTP_PASSWORD") or env_values.get("SMTP_PASSWORD", ""),
        smtp_use_tls=_bool_value(env_values, "SMTP_USE_TLS", True),
        app_username=os.getenv("APP_USERNAME") or env_values.get("APP_USERNAME", ""),
        app_password=os.getenv("APP_PASSWORD") or env_values.get("APP_PASSWORD", ""),
    )
