using namespace System.Net

param($Request, $TriggerMetadata)

# ----------------------------
# Helpers
# ----------------------------

# Read JSON body if present
$body = $null
if ($Request.Body) {
    try {
        $rawBody = Get-Content -Raw -InputObject $Request.Body
        if ($rawBody -and $rawBody.Trim().Length -gt 0) {
            $body = $rawBody | ConvertFrom-Json -ErrorAction Stop
        }
    } catch {
        # ignore malformed JSON; we'll just read from query params
    }
}

function Get-Param([string]$name, $default = $null) {
    if ($Request.Query.$name) { return $Request.Query.$name }
    if ($body -and ($body.PSObject.Properties.Name -contains $name)) { return $body.$name }
    return $default
}

# ----------------------------
# Parameters (HTTP -> script)
# ----------------------------

# Map HTTP inputs to your pull_data.ps1 parameters
$limit     = [int](Get-Param 'limit'     10000)
$chunkSize = [int](Get-Param 'chunkSize' 50)
$dte       = [int](Get-Param 'dte'       21)
$dateCode  =      (Get-Param 'dateCode'  '250926')
$symbol    =      (Get-Param 'symbol'    'GME')

# Output format: json (default) | txt | text | raw
$format    = (Get-Param 'format' 'json')

# Finnhub token is expected in env:
# - Locally:   local.settings.json -> Values.FINNHUB_TOKEN
# - In Azure:  Function App Settings -> FINNHUB_TOKEN
$env:FINNHUB_TOKEN = $env:FINNHUB_TOKEN

# ----------------------------
# Execute user script
# ----------------------------

Push-Location $PSScriptRoot  # = this function folder (ophunt/)
try {
    $scriptPath = Join-Path $PSScriptRoot 'pull_data.ps1'
    if (-not (Test-Path -LiteralPath $scriptPath)) {
        throw "pull_data.ps1 not found at $scriptPath"
    }

    # Invoke your script; capture stdout/stderr
    $raw = & $scriptPath $limit $chunkSize $dte $dateCode $symbol 2>&1

    # If caller asked for plain text, return as-is
    if ($format -in @('txt','text','raw')) {
        $plain = ($raw | Out-String)
        Push-OutputBinding -Name Response -Value ([HttpResponseContext]@{
            StatusCode = [HttpStatusCode]::OK
            Body       = $plain
            Headers    = @{
                "Content-Type" = "text/plain; charset=utf-8"
                # Uncomment if you need CORS in browser:
                # "Access-Control-Allow-Origin" = "*"
            }
        })
        return
    }

    # Try to parse the script output as JSON (if your script already emits JSON)
    $json = $null
    try { $json = $raw | ConvertFrom-Json -ErrorAction Stop } catch {}

    if ($null -ne $json) {
        # Pass-through JSON
        $bodyOut = $json | ConvertTo-Json -Depth 10
        Push-OutputBinding -Name Response -Value ([HttpResponseContext]@{
            StatusCode = [HttpStatusCode]::OK
            Body       = $bodyOut
            Headers    = @{
                "Content-Type" = "application/json"
                # "Access-Control-Allow-Origin" = "*"
            }
        })
    }
    else {
        # Fallback wrapper JSON
        $payload = [pscustomobject]@{
            ok        = $true
            symbol    = $symbol
            limit     = $limit
            chunkSize = $chunkSize
            dte       = $dte
            dateCode  = $dateCode
            output    = ($raw | Out-String)
        }
        $bodyOut = $payload | ConvertTo-Json -Depth 10
        Push-OutputBinding -Name Response -Value ([HttpResponseContext]@{
            StatusCode = [HttpStatusCode]::OK
            Body       = $bodyOut
            Headers    = @{
                "Content-Type" = "application/json"
                # "Access-Control-Allow-Origin" = "*"
            }
        })
    }
}
catch {
    $err = $_ | Out-String
    $resp = @{ ok = $false; error = $err } | ConvertTo-Json -Depth 5
    Push-OutputBinding -Name Response -Value ([HttpResponseContext]@{
        StatusCode = [HttpStatusCode]::InternalServerError
        Body       = $resp
        Headers    = @{
            "Content-Type" = "application/json"
            # "Access-Control-Allow-Origin" = "*"
        }
    })
}
finally {
    Pop-Location
}
