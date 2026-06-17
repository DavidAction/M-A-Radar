from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_candidates(root: Path) -> list[dict[str, Any]]:
    overrides = _load_overrides(root)
    real_path = root / "tl_ma_radar" / "data" / "real_candidates.json"
    if real_path.exists():
        return _apply_overrides(
            json.loads(real_path.read_text(encoding="utf-8")),
            overrides,
        )
    sample_path = root / "tl_ma_radar" / "data" / "sample_candidates.json"
    return _apply_overrides(
        json.loads(sample_path.read_text(encoding="utf-8")),
        overrides,
    )


def data_source(root: Path) -> str:
    real_path = root / "tl_ma_radar" / "data" / "real_candidates.json"
    if real_path.exists():
        return "real_candidates.json"
    return "sample_candidates.json"


def _load_overrides(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "tl_ma_radar" / "data" / "manual_overrides.json"
    if not path.exists():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {item["code"]: item for item in rows}


def _apply_overrides(rows: list[dict[str, Any]], overrides: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    if not overrides:
        return rows
    merged = []
    seen: set[str] = set()
    for row in rows:
        code = row.get("code")
        override = overrides.get(code)
        if override:
            combined = {**row, **{key: value for key, value in override.items() if key != "preserve_market_data"}}
            if override.get("preserve_market_data", True):
                for key in ("market_cap_krw", "current_price_krw", "volume", "per", "roe"):
                    if key in row:
                        combined[key] = row[key]
            merged.append(combined)
            seen.add(code)
        else:
            merged.append(row)
    for code, override in overrides.items():
        if code not in seen:
            merged.append({key: value for key, value in override.items() if key != "preserve_market_data"})
    return merged
