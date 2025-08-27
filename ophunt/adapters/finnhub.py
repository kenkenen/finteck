import os
import requests

# Finnhub base URL and API key (must be set in your shell)
BASE = "https://finnhub.io/api/v1"
KEY = os.environ.get("FINNHUB_TOKEN")
if not KEY:
    raise KeyError("FINNHUB_TOKEN not set. Export your Finnhub API key:  export FINNHUB_TOKEN=...")

# -----------------------------
# Helpers
# -----------------------------

def _expiry_from_yymmdd(yymmdd: str) -> str:
    """
    Convert 'YYMMDD' to 'YYYY-MM-DD' for Finnhub's expiration matching.
    e.g., '250920' -> '2025-09-20'
    """
    return f"20{yymmdd[:2]}-{yymmdd[2:4]}-{yymmdd[4:6]}"

def _normalize_contract_finnhub(raw: dict) -> dict:
    """
    Normalize a Finnhub option contract into the exact shape the rest of the app expects.
    Finnhub fields we rely on:
      - contractName, strike, lastPrice, bid, ask, volume
    """
    return {
        "contractSymbol": raw.get("contractName"),
        "strike":         raw.get("strike"),
        "lastPrice":      raw.get("lastPrice"),
        "bid":            raw.get("bid"),
        "ask":            raw.get("ask"),
        "volume":         raw.get("volume", 0),
    }

# -----------------------------
# Public API
# -----------------------------

def get_quote_finnhub(ticker: str) -> float | None:
    """
    Get the most recent underlying price for `ticker` from /quote.
    Finnhub returns 'c' as the current price.
    """
    r = requests.get(
        f"{BASE}/quote",
        params={"symbol": ticker.upper(), "token": KEY},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("c")

def get_expirations_finnhub(ticker: str) -> list[str]:
    """
    Return a sorted list of available expiration dates (YYYY-MM-DD) for the given ticker.
    Finnhub’s /stock/option-chain groups contracts by expiration; each block includes 'expirationDate'.
    """
    r = requests.get(
        f"{BASE}/stock/option-chain",
        params={"symbol": ticker.upper(), "token": KEY},
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()

    expirations = sorted({
        block["expirationDate"]
        for block in (payload.get("data") or [])
        if "expirationDate" in block
    })
    return expirations

def get_chain_finnhub(ticker: str, yymmdd: str) -> dict:
    """
    Return the option chain for a specific expiration as:
        { "puts": [ ... ], "calls": [ ... ] }
    Assumes Finnhub’s structure:
      data: [
        {
          "expirationDate": "YYYY-MM-DD",
          "options": {
            "CALL": [ {contractName, strike, lastPrice, bid, ask, volume, ...}, ... ],
            "PUT":  [ { ... }, ... ]
          }
        }, ...
      ]
    """
    # Fetch full option-chain listing for the ticker
    r = requests.get(
        f"{BASE}/stock/option-chain",
        params={"symbol": ticker.upper(), "token": KEY},
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()

    target_exp = _expiry_from_yymmdd(yymmdd)
    out = {"puts": [], "calls": []}

    # Find the block for the requested expiration and normalize its contracts
    for block in (payload.get("data") or []):
        if block.get("expirationDate") != target_exp:
            continue
        opts = block.get("options") or {}
        calls = opts.get("CALL") or []
        puts  = opts.get("PUT")  or []
        out["calls"] = [_normalize_contract_finnhub(c) for c in calls]
        out["puts"]  = [_normalize_contract_finnhub(p) for p in puts]
        break

    return out
