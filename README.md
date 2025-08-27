# Options Hunting Toolkit

This toolkit uses **Finnhub** for options chain and underlying quote data. No brokerage account is required. The data is filtered and displayed to aid in building a wheel strategy.

## Setup

1) **API key**
```bash
export FINNHUB_TOKEN="YOUR_FINNHUB_KEY"
```

(Optional) default ticker:
```bash
export TICKER="GME"
```

2) **Install dependencies**
```bash
pip install requests tabulate flask
```

---

## CLI Usage

```bash
python3 pull_data.py <funds> <shares> <costBasis> <YYMMDD> [ticker]
```
- `funds` (int) — dollars to size put contracts.  
- `shares` (int) — shares owned (for covered-call sizing).  
- `costBasis` (int) — per-share cost basis (filters calls below basis).  
- `YYMMDD` — expiration date (e.g., `250920` → 2025-09-20).  
- `ticker` (optional) — defaults to `TICKER` env var, else `GME`.

**Examples**
```bash
python3 pull_data.py 50000 1000 20 250920
python3 pull_data.py 75000 2000 18 250906 AMD
```

---

## HTTP Usage (server.py)

You can also run the toolkit as a lightweight web service.

### Start the server
```bash
export FINNHUB_TOKEN="YOUR_KEY"
python3 server.py
```

The server runs on `http://localhost:8000` by default.

### Endpoints

**1. JSON response**  
Returns computed puts/calls as JSON:
```bash
curl "http://localhost:8000/pull?funds=10000&shares=50&costBasis=21&date=250926&ticker=GME"
```

**2. Text table**  
Returns the same formatted table as the CLI:
```bash
curl "http://localhost:8000/pull/table?funds=10000&shares=50&costBasis=21&date=250926&ticker=GME"
```

### Query parameters
- `funds` — dollars to size CSP contracts.  
- `shares` — number of shares owned (for CC sizing).  
- `costBasis` — per-share cost basis.  
- `date` — expiration in `YYMMDD` format.  
- `ticker` — optional, defaults to `GME`.  

---

## Design Philosophy & Assumptions

This tool is built to support a **premium-capture selling strategy** (Wheel). It prioritizes *sell-side* opportunities with clear exit targets and position sizing based on your capital and holdings.

### Strategy at a glance
- **Cash-Secured Puts (CSPs):** collect premium with the willingness to buy shares at the strike.  
- **Covered Calls (CCs):** collect premium against shares you already own, only at strikes **above your cost basis** by default.  
- **Wheel flow:** sell CSPs → if assigned, sell CCs → if called away, repeat.

### What the script computes
- **Average** = (bid + ask) / 2 (mid-price proxy).  
- **Intrinsic value:**  
  - Put: `max(strike − spot, 0)`  
  - Call: `max(spot − strike, 0)`  
- **Extrinsic value** = `Average − Intrinsic`.  
- **Target Buy Back** = `Average − 50% of Extrinsic` (capture ~half the time value).  
- **Trigger** = `Target Buy Back + ½ * (ask − bid)` (nudges toward realistic fills).  
- **Qty sizing:**  
  - Puts: `ceil(funds / (strike * 100))`  
  - Calls: `ceil(shares / 100)`

### Filters (why some rows “disappear”)

**Spread sanity:** contracts with unreliable fills are skipped if their bid/ask spread is too wide.  
A row is skipped when either of the following is true:
- `spread > SPREAD_MAX_ABS` (default $0.30), or
- `spread / average > SPREAD_MAX_FRAC` (default 30%).

You can adjust via environment variables:
```bash
export SPREAD_MAX_ABS=0.25
export SPREAD_MAX_FRAC=0.25
```

- **Liquidity sanity:** requires `bid > 0`.  
- **Time-value focus:** requires `extrinsic > 0`.  
- **Covered calls guard:** by default, only show calls with `strike > costBasis`.  
  - This avoids suggesting calls that realize a **loss** relative to your basis.  
  - If you want to see all calls, remove that guard.

### Inputs you provide (and why)
- **`funds`** → sizes CSP contracts safely (cash-secured).  
- **`shares`** → sizes CC contracts (`shares // 100`).  
- **`costBasis`** → hides CCs below basis (protects from capped-loss exits).  
- **`YYMMDD`** → selects expiry (auto-fallback to nearest available if not found).  
- **`ticker`** → underlying symbol.

### Practical usage tips
- Start by **listing expirations** for a ticker and pick one with healthy liquidity.  
- Use a **realistic cost basis** to avoid filtering out every call.  
- Consider relaxing `extrinsic > 0` if you want to inspect thin markets (not recommended for trading).  
- For CSPs, prefer **OTM strikes** you’d be comfortable owning if assigned.  
- For CCs, choose **OTM strikes above basis** to avoid locking in losses.  
- The `funds` and `shares` values you use should amount to lots of 100. You should use multiples of 100s for this to make sense. That is, the funds should be able to cover the purchase of at least 100 shares so that you can sell at least 1 put, likewise the shares should be able to cover the sale of at least 100 shares so you can sell at least 1 call.

### Safety notes
- Mid-price is an estimate; real fills vary.  
- Premium capture targets are heuristics, not guarantees.  
- This is a research tool—no orders are placed.
