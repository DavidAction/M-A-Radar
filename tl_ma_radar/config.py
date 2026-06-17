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


def get_settings(root: Path) -> Settings:
    env_values = _parse_env_file(root / ".env")
    return Settings(
        dart_api_key=os.getenv("DART_API_KEY") or env_values.get("DART_API_KEY", ""),
        naver_client_id=os.getenv("NAVER_CLIENT_ID") or env_values.get("NAVER_CLIENT_ID", ""),
        naver_client_secret=os.getenv("NAVER_CLIENT_SECRET") or env_values.get("NAVER_CLIENT_SECRET", ""),
        capital_raise_krw=_int_value(env_values, "CAPITAL_RAISE_KRW", 30_000_000_000),
        target_market=os.getenv("TARGET_MARKET") or env_values.get("TARGET_MARKET", "KOSDAQ"),
        market_cap_limit_krw=_int_value(env_values, "MARKET_CAP_LIMIT_KRW", 30_000_000_000),
    )
