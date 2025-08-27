param(
  [Parameter(Mandatory)]
  [int]$Funds,
  [Parameter(Mandatory)]
  [int]$Shares,
  [Parameter(Mandatory)]
  [double]$CostBasis,
  [Parameter(Mandatory)]
  [string]$YYMMDD,
  [string]$Ticker = $env:TICKER
)

# Defaults
if (-not $Ticker) { $Ticker = "GME" }
$ErrorActionPreference = "Stop"

# ---- Config ----
$FINNHUB_TOKEN = $env:FINNHUB_TOKEN
if (-not $FINNHUB_TOKEN) {
  throw "FINNHUB_TOKEN not set. `nTry: `$env:FINNHUB_TOKEN='YOUR_KEY'"
}

$BASE = "https://finnhub.io/api/v1"
$SPREAD_MAX_FRAC = [double](${env:SPREAD_MAX_FRAC}   | ForEach-Object { if ($_){$_} else {'0.30'} })
$SPREAD_MAX_ABS  = [double](${env:SPREAD_MAX_ABS}    | ForEach-Object { if ($_){$_} else {'0.30'} })

function Convert-YYMMDDToISO {
  param([string]$s)
  "$('20' + $s.Substring(0,2))-$($s.Substring(2,2))-$($s.Substring(4,2))"
}

function Get-Quote {
  param([string]$Symbol)
  (Invoke-RestMethod -Uri "$BASE/quote" -Body @{ symbol=$Symbol.ToUpper(); token=$FINNHUB_TOKEN } -Method Get).c
}

function Get-OptionChainRaw {
  param([string]$Symbol)
  Invoke-RestMethod -Uri "$BASE/stock/option-chain" -Body @{ symbol=$Symbol.ToUpper(); token=$FINNHUB_TOKEN } -Method Get
}

function Get-Expirations {
  param([string]$Symbol)
  $payload = Get-OptionChainRaw -Symbol $Symbol
  $dates = @()
  foreach ($b in ($payload.data)) {
    if ($b.expirationDate) { $dates += $b.expirationDate }
  }
  $dates | Sort-Object -Unique
}

function Get-ChainForExpiry {
  param([string]$Symbol, [string]$YYMMDD)
  $iso = Convert-YYMMDDToISO $YYMMDD
  $payload = Get-OptionChainRaw -Symbol $Symbol
  $out = [ordered]@{ puts=@(); calls=@() }
  foreach ($b in ($payload.data)) {
    if ($b.expirationDate -eq $iso) {
      $calls = @($b.options.CALL)
      $puts  = @($b.options.PUT)
      $norm = {
        param($raw)
        [ordered]@{
          contractSymbol = $raw.contractName
          strike         = $raw.strike
          lastPrice      = $raw.lastPrice
          bid            = $raw.bid
          ask            = $raw.ask
          volume         = ($raw.volume | ForEach-Object { if ($_){$_} else {0} })
        }
      }
      $out.puts  = $puts  | ForEach-Object { & $norm $_ }
      $out.calls = $calls | ForEach-Object { & $norm $_ }
      break
    }
  }
  [pscustomobject]$out
}

# ---------- Fetch data & fallback ----------
try {
  $chain = Get-ChainForExpiry -Symbol $Ticker -YYMMDD $YYMMDD
  if (($chain.puts.Count -eq 0) -and ($chain.calls.Count -eq 0)) {
    $reqDate = [datetime]::ParseExact($YYMMDD,'yyMMdd',$null)
    $exps = Get-Expirations -Symbol $Ticker
    if ($exps.Count -gt 0) {
      $pairs = $exps | ForEach-Object { [pscustomobject]@{ dt = [datetime]::ParseExact($_,'yyyy-MM-dd',$null); iso=$_ } } | Sort-Object dt
      $chosen = ($pairs | Where-Object { $_.dt -ge $reqDate } | Select-Object -First 1)
      if (-not $chosen) { $chosen = $pairs[-1] }
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
  $spot = [double](Get-Quote -Symbol $Ticker)
} catch {
  Write-Error $_
  exit 1
}

# ---------- Build rows ----------
$rows = @()
$header = [pscustomobject]@{
  Ticker = $Ticker.ToUpper()
  CurrentPrice = if ($spot) { ("$ {0}" -f $spot) } else { "N/A" }
}
$rows += $header
$rows += [pscustomobject]@{ Section="Puts ++++++++++++" }

# Puts
foreach ($p in $chain.puts) {
  $bid = $p.bid; $ask = $p.ask; $strike = $p.strike
  if ($null -eq $bid -or $null -eq $ask -or $null -eq $strike) { continue }
  $avg = [math]::Round( ($bid + $ask) / 2, 2)
  $spread = $ask - $bid
  if ($avg -le 0) { continue }
  if ( ($spread -gt $SPREAD_MAX_ABS) -or ( ($spread / $avg) -gt $SPREAD_MAX_FRAC) ) { continue }

  $qty = if ($strike) { [math]::Ceiling($Funds / ($strike * 100)) } else { 0 }
  $intr = if (($spot -eq $null) -or (($strike - $spot) -lt 0)) { 0 } else { $strike - $spot }
  $extr = [math]::Round($avg - $intr, 2)
  if ($bid -le 0 -or $extr -le 0) { continue }

  $tbb = [math]::Round($avg - ($extr * 0.50), 2)
  $profit = [math]::Round($extr * $qty * 100, 2)
  $trigger = [math]::Round($tbb + ($spread / 2), 2)
  $diff = [math]::Round( ($tbb - $bid) / $bid, 4)

  $rows += [pscustomobject]@{
    Symbol=$p.contractSymbol; Strike=$strike; Last=$p.lastPrice
    Bid=$bid; Ask=$ask; Average=$avg; Volume=$p.volume; Qty=$qty
    ExtValue=$extr; TargetBuyBack=$tbb; Trigger=$trigger
    Differential=$diff; ExpiryProfit=$profit
  }
}

$rows += [pscustomobject]@{ Section="Calls ++++++++++++" }

# Calls
foreach ($c in $chain.calls) {
  $bid = $c.bid; $ask = $c.ask; $strike = $c.strike
  if ($null -eq $bid -or $null -eq $ask -or $null -eq $strike) { continue }
  $avg = [math]::Round( ($bid + $ask) / 2, 2)
  $spread = $ask - $bid
  if ($avg -le 0) { continue }
  if ( ($spread -gt $SPREAD_MAX_ABS) -or ( ($spread / $avg) -gt $SPREAD_MAX_FRAC) ) { continue }

  $qty = if ($Shares) { [math]::Ceiling($Shares / 100) } else { 0 }
  $intr = if (($spot -eq $null) -or (($spot - $strike) -lt 0)) { 0 } else { $spot - $strike }
  $extr = [math]::Round($avg - $intr, 2)
  if ($bid -le 0 -or $extr -le 0) { continue }
  if ($strike -le $CostBasis) { continue }  # cost-basis guard

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

# ---------- Output ----------
# Pretty print: group sections and show rows
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
