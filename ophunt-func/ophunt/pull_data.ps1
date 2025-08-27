<#
.SYNOPSIS
  Calculate and print option candidates (puts & calls) for a given ticker/expiry.

.DESIGN GOALS
  - **Clear, reproducible inputs** via a parameter block (with types/mandatory flags).
  - **Zero secrets in code**: pull tokens/knobs from environment variables.
  - **Resilience**: if requested expiry has no contracts, automatically pick the nearest available.
  - **Quality filters**: ignore illiquid/wide-spread contracts using tunable thresholds.
  - **Actionable outputs**: compute mid, extrinsic value, target buyback, trigger, and a profit proxy.
  - **Human-readable stdout** suitable for terminal use or HTTP passthrough.

.NOTES
  - Finnhub token must be provided as FINNHUB_TOKEN env var.
  - Spread filters can be tuned with SPREAD_MAX_FRAC (fractional) and SPREAD_MAX_ABS (absolute $).
#>

param(
# Required total **capital** you’re willing to allocate (used to size put contracts).
    [Parameter(Mandatory)]
    [int]$Funds,

# Required **share count** you already own (used to size call contracts).
    [Parameter(Mandatory)]
    [int]$Shares,

# Required **cost basis** per share; used as a guard to avoid writing covered calls below basis.
    [Parameter(Mandatory)]
    [double]$CostBasis,

# Required **expiry** as YYMMDD (e.g., 250926 → 2025-09-26).
    [Parameter(Mandatory)]
    [string]$YYMMDD,

# Optional ticker; defaults to $env:TICKER so you can set it once per session.
    [string]$Ticker = $env:TICKER
)

# ---------- Defaults & strict error behavior ----------
if (-not $Ticker) { $Ticker = "GME" }     # Sensible default for ad-hoc runs.
$ErrorActionPreference = "Stop"           # Fail fast so try/catch surfaces real errors.

# ---------- Config (all secrets & knobs via env) ----------
# Rationale: keep code portable; rotate tokens/knobs without code changes; avoid secret sprawl.
$FINNHUB_TOKEN = $env:FINNHUB_TOKEN
if (-not $FINNHUB_TOKEN) {
    throw "FINNHUB_TOKEN not set. `nTry: `$env:FINNHUB_TOKEN='YOUR_KEY'"
}

$BASE = "https://finnhub.io/api/v1"

# Spread filters:
#  - SPREAD_MAX_FRAC: max allowed (ask-bid)/mid, e.g., 0.30 → 30%
#  - SPREAD_MAX_ABS : max allowed absolute spread in dollars, e.g., 0.30 → $0.30
# These act as liquidity/quality gates; defaults encourage skipping illiquid contracts.
$SPREAD_MAX_FRAC = [double](${env:SPREAD_MAX_FRAC} | ForEach-Object { if ($_){$_} else {'0.30'} })
$SPREAD_MAX_ABS  = [double](${env:SPREAD_MAX_ABS}  | ForEach-Object { if ($_){$_} else {'0.30'} })

# ---------- Helpers ----------
function Convert-YYMMDDToISO {
    param([string]$s)
    # Finnhub returns expirations as YYYY-MM-DD; normalize the YYMMDD input the pull_data script expects.
    "$('20' + $s.Substring(0,2))-$($s.Substring(2,2))-$($s.Substring(4,2))"
}

function Get-Quote {
    param([string]$Symbol)
    # Query Finnhub quote endpoint; `.c` is the current/last price per API spec.
    (Invoke-RestMethod -Uri "$BASE/quote?symbol=$($Symbol.ToUpper())&token=$FINNHUB_TOKEN" -Method Get).c
}

function Get-OptionChainRaw {
    param([string]$Symbol)
    # Pull entire option chain (all expirations). We filter/shape later for separation of concerns.
    Invoke-RestMethod -Uri "$BASE/stock/option-chain?symbol=$($Symbol.ToUpper())&token=$FINNHUB_TOKEN" -Method Get
}

function Get-Expirations {
    param([string]$Symbol)
    # Extract unique expiration dates from the raw payload; sort ascending.
    $payload = Get-OptionChainRaw -Symbol $Symbol
    $dates = @()
    foreach ($b in ($payload.data)) {
        if ($b.expirationDate) { $dates += $b.expirationDate }
    }
    $dates | Sort-Object -Unique
}

function Get-ChainForExpiry {
    param([string]$Symbol, [string]$YYMMDD)
    # Normalize to YYYY-MM-DD to match Finnhub’s expiration format.
    $iso = Convert-YYMMDDToISO $YYMMDD
    $payload = Get-OptionChainRaw -Symbol $Symbol

    # Keep output predictable and column-ordered for pretty printing.
    $out = [ordered]@{ puts=@(); calls=@() }

    foreach ($b in ($payload.data)) {
        if ($b.expirationDate -eq $iso) {
            # Finnhub groups contracts by PUT/CALL; guard against nulls and standardize fields.
            $calls = @($b.options.CALL)
            $puts  = @($b.options.PUT)

            $norm = {
                param($raw)
                # Use ordered hashtable so printed columns are stable.
                [ordered]@{
                    contractSymbol = $raw.contractName
                    strike         = $raw.strike
                    lastPrice      = $raw.lastPrice
                    bid            = $raw.bid
                    ask            = $raw.ask
                    volume         = ($raw.volume | ForEach-Object { if ($_){$_} else {0} }) # default 0 if null
                }
            }

            $out.puts  = $puts  | ForEach-Object { & $norm $_ }
            $out.calls = $calls | ForEach-Object { & $norm $_ }
            break
        }
    }
    [pscustomobject]$out
}

# ---------- Fetch data with graceful fallback ----------
try {
    # Primary attempt: requested expiry.
    $chain = Get-ChainForExpiry -Symbol $Ticker -YYMMDD $YYMMDD

    # If no contracts found, choose the nearest available expiry (>= requested; else last).
    if (($chain.puts.Count -eq 0) -and ($chain.calls.Count -eq 0)) {
        $reqDate = [datetime]::ParseExact($YYMMDD,'yyMMdd',$null)
        $exps = Get-Expirations -Symbol $Ticker

        if ($exps.Count -gt 0) {
            $pairs = $exps | ForEach-Object {
                [pscustomobject]@{ dt = [datetime]::ParseExact($_,'yyyy-MM-dd',$null); iso=$_ }
            } | Sort-Object dt

            # Prefer the first expiry on/after requested; otherwise fall back to the latest.
            $chosen = ($pairs | Where-Object { $_.dt -ge $reqDate } | Select-Object -First 1)
            if (-not $chosen) { $chosen = $pairs[-1] }

            # Re-query using the chosen expiry.
            $alt = "{0:yy}{0:MM}{0:dd}" -f $chosen.dt
            $altChain = Get-ChainForExpiry -Symbol $Ticker -YYMMDD $alt

            if (($altChain.puts.Count -gt 0) -or ($altChain.calls.Count -gt 0)) {
                Write-Host ("No contracts for requested {0:yyyy-MM-dd}. Using nearest: {1}" -f $reqDate, $chosen.iso)
                $chain = $altChain
            } else {
                Write-Host ("No data for requested and nearest {0}. Available: {1}" -f $chosen.iso, ($exps -join ", "))
            }
        } else {
            Write-Host "No expirations available for this ticker."
        }
    }

    # Get spot price once; used for intrinsic/extrinsic calculations.
    $spot = [double](Get-Quote -Symbol $Ticker)
}
catch {
    # Bubble up a single, clear error to callers (e.g., HTTP wrapper) with non-zero exit.
    Write-Error $_
    exit 1
}

# ---------- Build printable rows ----------
$rows = @()

# Header row communicates context; keeps output self-describing when pasted/shared.
$header = [pscustomobject]@{
    Ticker = $Ticker.ToUpper()
    CurrentPrice = if ($spot) { ("$ {0}" -f $spot) } else { "N/A" }
}
$rows += $header
$rows += [pscustomobject]@{ Section="Puts ++++++++++++" }

# ----- PUTS -----
foreach ($p in $chain.puts) {
    $bid = $p.bid; $ask = $p.ask; $strike = $p.strike
    if ($null -eq $bid -or $null -eq $ask -or $null -eq $strike) { continue }     # Skip incomplete quotes.

    # Use mid-price as fair value proxy; consistent with most trading UIs.
    $avg = [math]::Round( ($bid + $ask) / 2, 2)
    $spread = $ask - $bid

    # Quality gates: avoid zero/negative mids and wide spreads (both absolute and relative).
    if ($avg -le 0) { continue }
    if ( ($spread -gt $SPREAD_MAX_ABS) -or ( ($spread / $avg) -gt $SPREAD_MAX_FRAC) ) { continue }

    # Position sizing: how many **contracts** given Funds and strike (100 shares per contract).
    $qty = if ($strike) { [math]::Ceiling($Funds / ($strike * 100)) } else { 0 }

    # Puts: intrinsic = max(strike - spot, 0)
    $intr = if (($spot -eq $null) -or (($strike - $spot) -lt 0)) { 0 } else { $strike - $spot }
    $extr = [math]::Round($avg - $intr, 2)
    if ($bid -le 0 -or $extr -le 0) { continue }  # Skip if no premium or all intrinsic value.

    # Target buyback (TBB): capture ~50% of extrinsic value as a simple profit-taking heuristic.
    $tbb = [math]::Round($avg - ($extr * 0.50), 2)

    # Profit proxy at expiry: extrinsic * qty * 100 (ignores assignment/fees; quick comparability).
    $profit = [math]::Round($extr * $qty * 100, 2)

    # Trigger: place near the mid of [bid, ask] anchored at TBB for alert/limit logic.
    $trigger = [math]::Round($tbb + ($spread / 2), 2)

    # Differential: relative lift vs current bid; helps rank opportunities.
    $diff = [math]::Round( ($tbb - $bid) / $bid, 4)

    $rows += [pscustomobject]@{
        Symbol=$p.contractSymbol; Strike=$strike; Last=$p.lastPrice
        Bid=$bid; Ask=$ask; Average=$avg; Volume=$p.volume; Qty=$qty
        ExtValue=$extr; TargetBuyBack=$tbb; Trigger=$trigger
        Differential=$diff; ExpiryProfit=$profit
    }
}

$rows += [pscustomobject]@{ Section="Calls ++++++++++++" }

# ----- CALLS -----
foreach ($c in $chain.calls) {
    $bid = $c.bid; $ask = $c.ask; $strike = $c.strike
    if ($null -eq $bid -or $null -eq $ask -or $null -eq $strike) { continue }

    $avg = [math]::Round( ($bid + $ask) / 2, 2)
    $spread = $ask - $bid
    if ($avg -le 0) { continue }
    if ( ($spread -gt $SPREAD_MAX_ABS) -or ( ($spread / $avg) -gt $SPREAD_MAX_FRAC) ) { continue }

    # Covered calls sizing: number of 100-share lots you can cover with existing Shares.
    $qty = if ($Shares) { [math]::Ceiling($Shares / 100) } else { 0 }

    # Calls: intrinsic = max(spot - strike, 0)
    $intr = if (($spot -eq $null) -or (($spot - $strike) -lt 0)) { 0 } else { $spot - $strike }
    $extr = [math]::Round($avg - $intr, 2)
    if ($bid -le 0 -or $extr -le 0) { continue }

    # Guardrail: avoid writing calls at/under cost basis (don’t cap gains below basis).
    if ($strike -le $CostBasis) { continue }

    $tbb = [math]::Round($avg - ($extr * 0.50), 2)
    $profit = [math]::Round($extr * $qty * 100, 2)
    $trigger = [math]::Round($tbb + ($spread / 2), 2)
    $diff = [math]::Round( ($tbb - $bid) / $bid, 4)

    $rows += [pscustomobject]@{
        Symbol=$c.contractSymbol; Strike=$strike; Last=$c.lastPrice
        Bid=$bid; Ask=$ask; Average=$avg; Volume=$c.volume; Qty=$qty
        ExtValue=$extr; TargetBuyBack=$tbb; Trigger=$trigger
        Differential=$diff; ExpiryProfit=$profit
    }
}

# ---------- Output (human-readable, stable columns) ----------
# Rationale: we print sections and aligned columns for quick scanning or HTTP passthrough.
$rows | ForEach-Object {
    if ($_.PSObject.Properties.Name -contains "Section") {
        "`n$($_.Section)`n" | Write-Host
    } elseif ($_.PSObject.Properties.Name -contains "Ticker") {
        "Ticker: $($_.Ticker)    Current Price: $($_.CurrentPrice)`n" | Write-Host
    } else {
        "{0,-16} {1,6} {2,8} {3,8} {4,8} {5,8} {6,7} {7,5} {8,10} {9,15} {10,8} {11,12} {12,12}" -f `
      $_.Symbol, $_.Strike, $_.Last, $_.Bid, $_.Ask, $_.Average, $_.Volume, $_.Qty, `
      $_.ExtValue, $_.TargetBuyBack, $_.Trigger, $_.Differential, $_.ExpiryProfit
    }
}
