"""Helpers around the Pocket Option asset universe.

The asset list comes straight from the unofficial ``pocketoptionapi_async``
package so the names we scan/trade match what the platform expects. When that
package is unavailable (e.g. minimal install) we fall back to a small built-in
list so the demo mode and tests still work.
"""

from __future__ import annotations

_FALLBACK_ASSETS: dict[str, int] = {
    "EURUSD": 1,
    "GBPUSD": 56,
    "USDJPY": 63,
    "AUDUSD": 40,
    "USDCAD": 61,
    "EURUSD_otc": 66,
    "GBPUSD_otc": 86,
    "USDJPY_otc": 93,
    "AUDUSD_otc": 71,
    "USDCAD_otc": 91,
    "EURJPY_otc": 75,
    "BTCUSD_otc": 484,
}

try:  # pragma: no cover - depends on optional dependency
    from pocketoptionapi_async import ASSETS as _PO_ASSETS

    ASSETS: dict[str, int] = dict(_PO_ASSETS)
except Exception:  # pragma: no cover
    ASSETS = dict(_FALLBACK_ASSETS)


def is_known_asset(asset: str) -> bool:
    return asset in ASSETS


def is_otc(asset: str) -> bool:
    return asset.endswith("_otc")


def list_assets(otc_only: bool = False, real_only: bool = False) -> list[str]:
    names = sorted(ASSETS.keys())
    if otc_only:
        return [a for a in names if is_otc(a)]
    if real_only:
        return [a for a in names if not is_otc(a)]
    return names


def normalize(asset: str) -> str:
    """Best-effort normalisation of user input to a known asset name."""
    if asset in ASSETS:
        return asset
    cleaned = asset.strip().upper().replace("/", "").replace("-", "").replace(" ", "")
    # Try exact, then with _otc suffix.
    for candidate in (cleaned, f"{cleaned}_otc"):
        for known in ASSETS:
            if known.upper() == candidate.upper():
                return known
    return asset
