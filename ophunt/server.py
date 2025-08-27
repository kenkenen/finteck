# server.py
import os
import math
from datetime import datetime
from flask import Flask, request, jsonify, Response
from tabulate import tabulate

# ---- Config (same defaults as CLI) ----
SPREAD_MAX_FRAC = float(os.environ.get("SPREAD_MAX_FRAC", "0.30"))  # 30% of mid
SPREAD_MAX_ABS  = float(os.environ.get("SPREAD_MAX_ABS",  "0.30"))  # $0.30
DEFAULT_TICKER  = os.environ.get("TICKER", "GME")

# Import your Finnhub adapter (already in your repo)
from adapters.finnhub import (
    get_chain_finnhub,
    get_quote_finnhub,
    get_expirations_finnhub,
)

app = Flask(__name__)

def _compute_chain(funds:int, shares:int, costBasis:float, yymmdd:str, ticker:str):
    """
    Core logic: fetch chain/quote, auto-fallback to nearest expiry,
    apply spread sanity + your extrinsic/target/trigger math, and
    return (meta, rows_puts, rows_calls, messages)
    """
    # Fetch chain for requested expiry
    chain = get_chain_finnhub(ticker, yymmdd)

    # Fallback to nearest available expiry if empty
    msg = None
    if (not chain.get("puts")) and (not chain.get("calls")):
        requested_dt = datetime.strptime(yymmdd, "%y%m%d")
        expirations = get_expirations_finnhub(ticker) or []
        if expirations:
            exp_dts = [(datetime.strptime(e, "%Y-%m-%d"), e) for e in expirations]
            on_or_after = [e for e in exp_dts if e[0] >= requested_dt]
            chosen = (on_or_after[0][1] if on_or_after else exp_dts[-1][1])
            yy = chosen[2:4]; mm = chosen[5:7]; dd = chosen[8:10]
            alt_yymmdd = f"{yy}{mm}{dd}"
            alt_chain = get_chain_finnhub(ticker, alt_yymmdd)
            if alt_chain.get("puts") or alt_chain.get("calls"):
                msg = f"No contracts for {ticker} {requested_dt:%Y-%m-%d}. Using nearest: {chosen}"
                chain = alt_chain
            else:
                msg = (f"{ticker}: no data for requested and nearest {chosen}. "
                       f"Available expiries: {', '.join(expirations)}")

    # Quote
    try:
        current_price = float(get_quote_finnhub(ticker))
    except Exception:
        current_price = None

    # Build rows (same math as pull_data.py)
    puts_rows, calls_rows = [], []

    # Puts
    for put in chain.get("puts", []):
        symbol = put.get("contractSymbol")
        strike = put.get("strike")
        last_price = put.get("lastPrice")
        bid = put.get("bid"); ask = put.get("ask")
        if bid is None or ask is None or strike is None:
            continue
        average = round((bid + ask) / 2, 2)
        spread = ask - bid

        # Spread sanity
        if average <= 0:
            continue
        if (spread > SPREAD_MAX_ABS) or ((spread / average) > SPREAD_MAX_FRAC):
            continue

        volume = put.get("volume", 0)
        qty = math.ceil(funds / (strike * 100)) if strike else 0
        intrinsic = 0 if (current_price is None or (strike - current_price) < 0) else (strike - current_price)
        extrinsic = round(average - intrinsic, 2)
        target_buy_back = round(average - (extrinsic * 0.50), 2)
        profit = round(extrinsic * qty * 100, 2)
        trigger = round(target_buy_back + (spread / 2), 2)
        if bid > 0 and extrinsic > 0:
            diff_from_bid = round((target_buy_back - bid) / bid, 4)
            puts_rows.append({
                "symbol": symbol,
                "strike": strike,
                "last": last_price,
                "bid": bid, "ask": ask, "average": average,
                "volume": volume, "qty": qty,
                "ext_value": extrinsic,
                "target_buy_back": target_buy_back,
                "trigger": trigger,
                "differential": diff_from_bid,
                "expiry_profit": profit
            })

    # Calls
    for call in chain.get("calls", []):
        symbol = call.get("contractSymbol")
        strike = call.get("strike")
        last_price = call.get("lastPrice")
        bid = call.get("bid"); ask = call.get("ask")
        if bid is None or ask is None or strike is None:
            continue
        average = round((bid + ask) / 2, 2)
        spread = ask - bid

        # Spread sanity
        if average <= 0:
            continue
        if (spread > SPREAD_MAX_ABS) or ((spread / average) > SPREAD_MAX_FRAC):
            continue

        volume = call.get("volume", 0)
        qty = math.ceil(shares / 100) if shares else 0
        intrinsic = 0 if (current_price is None or (current_price - strike) < 0) else (current_price - strike)
        extrinsic = round(average - intrinsic, 2)
        target_buy_back = round(average - (extrinsic * 0.50), 2)
        profit = round(extrinsic * qty * 100, 2)
        trigger = round(target_buy_back + (spread / 2), 2)
        # cost-basis guard
        if bid > 0 and extrinsic > 0 and (costBasis is None or strike > costBasis):
            diff_from_bid = round((target_buy_back - bid) / bid, 4)
            calls_rows.append({
                "symbol": symbol,
                "strike": strike,
                "last": last_price,
                "bid": bid, "ask": ask, "average": average,
                "volume": volume, "qty": qty,
                "ext_value": extrinsic,
                "target_buy_back": target_buy_back,
                "trigger": trigger,
                "differential": diff_from_bid,
                "expiry_profit": profit
            })

    meta = {
        "ticker": ticker.upper(),
        "current_price": current_price,
        "message": msg
    }
    return meta, puts_rows, calls_rows

@app.get("/pull")
def pull_json():
    """
    GET /pull?funds=10000&shares=50&costBasis=21&date=250926&ticker=GME
    Returns JSON with puts/calls rows and header.
    """
    try:
        funds = int(request.args.get("funds", "0"))
        shares = int(request.args.get("shares", "0"))
        costBasis = float(request.args.get("costBasis", "0"))
        yymmdd = request.args.get("date")
        ticker = request.args.get("ticker", DEFAULT_TICKER)
        if not yymmdd:
            return jsonify(error="Missing 'date' (YYMMDD)."), 400
        meta, puts_rows, calls_rows = _compute_chain(funds, shares, costBasis, yymmdd, ticker)
        return jsonify(meta=meta, puts=puts_rows, calls=calls_rows)
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.get("/pull/table")
def pull_table():
    """
    GET /pull/table?funds=...&shares=...&costBasis=...&date=YYMMDD&ticker=GME
    Returns a plain-text table like the CLI.
    """
    try:
        funds = int(request.args.get("funds", "0"))
        shares = int(request.args.get("shares", "0"))
        costBasis = float(request.args.get("costBasis", "0"))
        yymmdd = request.args.get("date")
        ticker = request.args.get("ticker", DEFAULT_TICKER)
        if not yymmdd:
            return Response("Missing 'date' (YYMMDD).", status=400, mimetype="text/plain")

        meta, puts_rows, calls_rows = _compute_chain(funds, shares, costBasis, yymmdd, ticker)
        header = [
            ["Ticker", meta["ticker"], "Current Price:", f"$ {meta['current_price']}" if meta['current_price'] is not None else "N/A"],
            ["Symbol", "Strike", "Last", "Bid", "Ask", "Average", "Volume", "Qty",
             "Ext Value", "Target Buy Back", "Trigger", "Differential", "Expiry Profit"],
            ["Puts  ++++++++++++"]
        ]
        # map dict rows to display rows (puts)
        for r in puts_rows:
            header.append([
                r["symbol"], f"$ {r['strike']}", f"$ {r['last']}", f"$ {r['bid']}", f"$ {r['ask']}", f"$ {r['average']}",
                r["volume"], r["qty"], f"$ {r['ext_value']}", f"$ {r['target_buy_back']}",
                f"$ {r['trigger']}", r["differential"], f"$ {r['expiry_profit']}"
            ])
        header.append(["Calls ++++++++++++"])
        # calls
        for r in calls_rows:
            header.append([
                r["symbol"], f"$ {r['strike']}", f"$ {r['last']}", f"$ {r['bid']}", f"$ {r['ask']}", f"$ {r['average']}",
                r["volume"], r["qty"], f"$ {r['ext_value']}", f"$ {r['target_buy_back']}",
                f"$ {r['trigger']}", r["differential"], f"$ {r['expiry_profit']}"
            ])

        # prepend any message (e.g., nearest expiry)
        msg = meta.get("message")
        table_text = ("# " + msg + "\n" if msg else "") + tabulate(header)
        return Response(table_text, mimetype="text/plain")
    except Exception as e:
        return Response(str(e), status=500, mimetype="text/plain")

if __name__ == "__main__":
    # For local testing only. Use a real WSGI/ASGI server in prod.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
