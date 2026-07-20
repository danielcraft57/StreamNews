# Lance analyzer + worker Celery + web (Windows).
# Usage: .\scripts\dev.ps1 -Local

param(
    [switch]$Local
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

. (Join-Path $Root "scripts\load-env.ps1") @PSBoundParameters

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "venv absent. Lance d'abord: .\scripts\install.ps1"
}
if (-not (Test-Path "web\node_modules")) {
    throw "node_modules absent. Lance d'abord: .\scripts\install.ps1"
}

Write-Host "Init DB ($($env:STREAMNEWS_ENV) / $($env:DATABASE_URL))..."
& (Join-Path $Root "scripts\init-db.ps1") @PSBoundParameters

$concurrency = if ($env:CELERY_CONCURRENCY) { $env:CELERY_CONCURRENCY } else { "2" }

Write-Host "Demarrage analyzer (8000), worker Celery, web (3000)..."
Write-Host "Ctrl+C pour tout arreter."

$node = (Get-Command node -ErrorAction Stop).Source
$analyzerDir = Join-Path $Root "analyzer"
$webDir = Join-Path $Root "web"

$procs = @()
try {
    Write-Host "[dev] analyzer..."
    $procs += Start-Process -FilePath $Python -ArgumentList "main.py" `
        -WorkingDirectory $analyzerDir -PassThru -NoNewWindow

    Write-Host "[dev] worker Celery (pool=solo)..."
    $procs += Start-Process -FilePath $Python -ArgumentList @(
        "-m", "celery", "-A", "celery_worker", "worker",
        "--loglevel=info", "--pool=solo", "--concurrency=$concurrency",
        "-Q", "crawl,ingest,default"
    ) -WorkingDirectory $analyzerDir -PassThru -NoNewWindow

    Write-Host "[dev] web (node server.js)..."
    $procs += Start-Process -FilePath $node -ArgumentList "server.js" `
        -WorkingDirectory $webDir -PassThru -NoNewWindow

    while ($true) {
        foreach ($p in $procs) {
            if ($p.HasExited) {
                throw "Processus $($p.Id) arrete (code $($p.ExitCode))."
            }
        }
        Start-Sleep -Seconds 2
    }
} finally {
    foreach ($p in $procs) {
        if (-not $p.HasExited) {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
    }
}
