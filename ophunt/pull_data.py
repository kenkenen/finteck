import math
import sys
from datetime import datetime
from tabulate import tabulate
import os

if len(sys.argv) < 5:
    print("Usage: python3 pull_data.py <funds> <shares> <costBasis> <YYMMDD> [ticker]")
    sys.exit(1)

funds = int(sys.argv[1])
shares = int(sys.argv[2])
costBasis = int(sys.argv[3])
date = datetime.strptime(sys.argv[4], "%y%m%d")
ticker = sys.argv[5] if len(sys.argv) > 5 else os.environ.get("TICKER", "GME")

# ---- Spread sanity thresholds (configurable via env) ----
# Contracts with unreliable fills are skipped if their bid/ask spread is too wide.
# A row is skipped when either of the following is true:
#   spread > SPREAD_MAX_ABS    (default $0.30)
#   spread / average > SPREAD_MAX_FRAC (default 30%)
SPREAD_MAX_FRAC = float(os.environ.get("SPREAD_MAX_FRAC", "0.30"))  # 30% of mid
SPREAD_MAX_ABS  = float(os.environ.get("SPREAD_MAX_ABS",  "0.30"))  # $0.30 absolute

from adapters.finnhub import get_chain_finnhub, get_quote_finnhub, get_expirations_finnhub

# Fetch chain & underlying price
chain = get_chain_finnhub(ticker, sys.argv[4])  # {"puts": [...], "calls": [...]}

# If no options returned for the requested date, auto-select the nearest available expiry
if (not chain.get("puts")) and (not chain.get("calls")):
    requested_dt = date
    expirations = get_expirations_finnhub(ticker) or []
    if expirations:
        from datetime import datetime as _dt
        exp_dts = [(_dt.strptime(e, "%Y-%m-%d"), e) for e in expirations]
        # pick the first expiry on/after the requested date; else the nearest before
        on_or_after = [e for e in exp_dts if e[0] >= requested_dt]
        chosen = (on_or_after[0][1] if on_or_after else exp_dts[-1][1])
        # Convert chosen YYYY-MM-DD back to YYMMDD to reuse the same function
        yy = chosen[2:4]; mm = chosen[5:7]; dd = chosen[8:10]
        alt_yymmdd = f"{yy}{mm}{dd}"
        alt_chain = get_chain_finnhub(ticker, alt_yymmdd)
        if alt_chain.get("puts") or alt_chain.get("calls"):
            print(f"No contracts found for requested expiry {date.strftime('%Y-%m-%d')}. "
                  f"Using nearest available expiry: {chosen}")
            chain = alt_chain
        else:
            print(f"No contracts found for requested expiry {date.strftime('%Y-%m-%d')} "
                  f"and no data for nearest available expiry {chosen}. "
                  f"Available expiries: {', '.join(expirations)}")
    else:
        print("No expirations available from Finnhub for this ticker.")

options = [chain]
try:
    currentPrice = float(get_quote_finnhub(ticker))
except Exception:
    currentPrice = None

def ophunt_local(funds, shares, costBasis, current_price, options):
    header_price = f"$ {current_price}" if current_price is not None else "N/A"
    options_data = [
        ["Ticker", ticker.upper(), "Current Price:", header_price],
        ["Symbol", "Strike", "Last", "Bid", "Ask", "Average", "Volume", "Qty",
         "Ext Value", "Target Buy Back", "Trigger", "Differential", "Expiry Profit"],
        ["Puts  ++++++++++++"]
    ]

    # Puts
    for put in options[0].get('puts', []):
        symbol = put.get('contractSymbol')
        strike = put.get('strike')
        last_price = put.get('lastPrice')
        bid = put.get('bid')
        ask = put.get('ask')
        if bid is None or ask is None or strike is None:
            continue
        average = round((bid + ask) / 2, 2)
        spread = (ask - bid)
        # --- Spread sanity filter (puts)
        if average <= 0:
            continue
        if (spread > SPREAD_MAX_ABS) or ((spread / average) > SPREAD_MAX_FRAC):
            continue

        volume = put.get('volume', 0)
        qty = math.ceil(funds / (strike * 100)) if strike else 0
        int_value = 0 if (current_price is None or (strike - current_price) < 0) else (strike - current_price)
        ext_value = round(average - int_value, 2)
        target_buy_back = round((average - (ext_value * 0.50)), 2)
        profit = round(ext_value * qty * 100, 2)
        trigger = round(target_buy_back + (spread / 2), 2)
        if bid > 0 and ext_value > 0:
            diff_from_bid = round((target_buy_back - bid) / bid, 4)
            options_data.append([
                symbol, f"$ {strike}", f"$ {last_price}", f"$ {bid}", f"$ {ask}", f"$ {average}",
                volume, qty, f"$ {ext_value}", f"$ {target_buy_back}", f"$ {trigger}", diff_from_bid, f"$ {profit}"
            ])

    options_data.append(["Calls ++++++++++++"])

    # Calls
    for call in options[0].get('calls', []):
        symbol = call.get('contractSymbol')
        strike = call.get('strike')
        last_price = call.get('lastPrice')
        bid = call.get('bid')
        ask = call.get('ask')
        if bid is None or ask is None or strike is None:
            continue
        average = round((bid + ask) / 2, 2)
        spread = (ask - bid)
        # --- Spread sanity filter (calls)
        if average <= 0:
            continue
        if (spread > SPREAD_MAX_ABS) or ((spread / average) > SPREAD_MAX_FRAC):
            continue

        volume = call.get('volume', 0)
        qty = math.ceil(shares / 100) if shares else 0
        int_value = 0 if (current_price is None or (current_price - strike) < 0) else (current_price - strike)
        ext_value = round(average - int_value, 2)
        target_buy_back = round((average - (ext_value * 0.50)), 2)
        profit = round(ext_value * qty * 100, 2)
        trigger = round(target_buy_back + (spread / 2), 2)
        if bid > 0 and ext_value > 0 and (costBasis is None or strike > costBasis):
            diff_from_bid = round((target_buy_back - bid) / bid, 4)
            options_data.append([
                symbol, f"$ {strike}", f"$ {last_price}", f"$ {bid}", f"$ {ask}", f"$ {average}",
                volume, qty, f"$ {ext_value}", f"$ {target_buy_back}", f"$ {trigger}", diff_from_bid, f"$ {profit}"
            ])

    print("Results: ")
    print(tabulate(options_data))

ophunt_local(funds, shares, costBasis, currentPrice, options)
