<#
.SYNOPSIS
  Stop the services started by start-all.ps1, and optionally the observability stack.

.EXAMPLE
  .\scripts\stop-all.ps1                 # services only; Grafana keeps its data
  .\scripts\stop-all.ps1 -Observability  # also stop the Docker stack
#>
param([switch]$Observability)

$root = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $root ".run\pids.txt"

if (Test-Path $pidFile) {
    foreach ($id in Get-Content $pidFile) {
        # /T kills the process tree (window -> uv -> python)
        taskkill /PID $id /T /F 2>$null | Out-Null
    }
    Remove-Item $pidFile
    Write-Host "Services stopped." -ForegroundColor Green
} else {
    Write-Host "No .run\pids.txt found; no services to stop."
}

if ($Observability) {
    docker compose -f (Join-Path $root "observability/docker-compose.yml") down
}
