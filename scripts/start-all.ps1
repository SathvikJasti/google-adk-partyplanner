<#
.SYNOPSIS
  Start the observability stack and all four services, each in its own process/port.

.EXAMPLE
  .\scripts\start-all.ps1                  # stack + services, each in its own window
  .\scripts\start-all.ps1 -Background      # services hidden, logs in .run\*.log
  .\scripts\start-all.ps1 -NoObservability # services only
#>
param(
    [switch]$Background,
    [switch]$NoObservability
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$runDir = Join-Path $root ".run"
New-Item -ItemType Directory -Force $runDir | Out-Null
$pidFile = Join-Path $runDir "pids.txt"

if (Test-Path $pidFile) {
    Write-Host "Services may already be running (found .run\pids.txt). Run .\scripts\stop-all.ps1 first." -ForegroundColor Yellow
    exit 1
}

if (-not $NoObservability) {
    Write-Host "Starting observability stack (Docker)..." -ForegroundColor Cyan
    # docker prints progress on stderr; don't let PowerShell treat that as fatal.
    $ErrorActionPreference = "Continue"
    docker compose -f observability/docker-compose.yml up -d
    $ErrorActionPreference = "Stop"
    if ($LASTEXITCODE -ne 0) { throw "docker compose failed. Is Docker Desktop running?" }
}

# Dependencies first: the party planner calls the other three.
$services = @(
    @{ Name = "mcp_server";       Module = "mcp_server";       Health = "http://127.0.0.1:8002/health" },
    @{ Name = "budget_agent";     Module = "budget_agent";     Health = "http://127.0.0.1:8001/health" },
    @{ Name = "compliance_agent"; Module = "compliance_agent"; Health = "http://127.0.0.1:8003/health" },
    @{ Name = "party_planner";    Module = "agents";           Health = "http://127.0.0.1:8000/list-apps" }
)

function Wait-Healthy($svc, $timeoutSec = 60) {
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            Invoke-WebRequest $svc.Health -UseBasicParsing -TimeoutSec 2 | Out-Null
            return $true
        } catch { Start-Sleep -Milliseconds 500 }
    }
    return $false
}

foreach ($svc in $services) {
    Write-Host ("Starting {0,-17} (python -m {1})" -f $svc.Name, $svc.Module) -ForegroundColor Cyan
    if ($Background) {
        $p = Start-Process -FilePath "uv" -ArgumentList "run", "python", "-m", $svc.Module `
            -RedirectStandardOutput (Join-Path $runDir "$($svc.Name).out.log") `
            -RedirectStandardError  (Join-Path $runDir "$($svc.Name).log") `
            -WindowStyle Hidden -PassThru
    } else {
        $title = "`$Host.UI.RawUI.WindowTitle = '$($svc.Name)'"
        $p = Start-Process -FilePath "powershell" -PassThru -ArgumentList "-NoExit", "-Command",
            "$title; Set-Location '$root'; uv run python -m $($svc.Module)"
    }
    Add-Content $pidFile "$($p.Id)"
    if (-not (Wait-Healthy $svc)) {
        Write-Host "  $($svc.Name) did not become healthy at $($svc.Health)" -ForegroundColor Red
        exit 1
    }
    Write-Host "  healthy" -ForegroundColor Green
}

Write-Host ""
Write-Host "Party planner (ADK web UI): http://localhost:8000" -ForegroundColor Green
if (-not $NoObservability) {
    Write-Host "Grafana:                    http://localhost:3000  (Dashboards > Party Planner)" -ForegroundColor Green
}
Write-Host "Stop everything with:       .\scripts\stop-all.ps1"
