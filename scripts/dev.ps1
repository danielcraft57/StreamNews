# Lance analyzer + worker Celery + web (Windows) avec hot reload.
# Usage: .\scripts\dev.ps1 -Local
#        .\scripts\dev.ps1 -Local -NoReload

param(
    [switch]$Local,
    [switch]$NoReload,
    [switch]$SkipInit
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

if (-not $SkipInit) {
    Write-Host "Init DB ($($env:STREAMNEWS_ENV) / $($env:DATABASE_URL))..."
    & (Join-Path $Root "scripts\init-db.ps1") @PSBoundParameters
}

$concurrency = if ($env:CELERY_CONCURRENCY) { $env:CELERY_CONCURRENCY } else { "2" }
$reload = -not $NoReload

if ($reload) {
    Write-Host "Hot reload actif (analyzer uvicorn --reload, web nodemon, worker watchdog)."
    Write-Host "Fichiers web/public/* : refresh navigateur (pas de restart serveur)."
} else {
    Write-Host "Hot reload desactive (-NoReload)."
}
Write-Host "Demarrage analyzer (8000), worker Celery, web (3000)..."
Write-Host "Ctrl+C pour tout arreter."

$node = (Get-Command node -ErrorAction Stop).Source
$analyzerDir = Join-Path $Root "analyzer"
$webDir = Join-Path $Root "web"
$nodemon = Join-Path $webDir "node_modules\nodemon\bin\nodemon.js"

$procs = @()
try {
    if ($reload) {
        Write-Host "[dev] analyzer (uvicorn --reload)..."
        $procs += Start-Process -FilePath $Python -ArgumentList @(
            "-m", "uvicorn", "main:app",
            "--host", "0.0.0.0", "--port", "8000",
            "--reload", "--reload-dir", $analyzerDir
        ) -WorkingDirectory $analyzerDir -PassThru -NoNewWindow

        Write-Host "[dev] worker Celery (watchdog auto-restart)..."
        $procs += Start-Process -FilePath $Python -ArgumentList @(
            "-m", "watchdog.watchmedo", "auto-restart",
            "--directory", $analyzerDir,
            "--pattern", "*.py",
            "--recursive",
            "--debounce-interval", "2",
            "--",
            $Python, "-m", "celery", "-A", "celery_worker", "worker",
            "--loglevel=info", "--pool=solo", "--concurrency=$concurrency",
            "-Q", "crawl,ingest,default"
        ) -WorkingDirectory $analyzerDir -PassThru -NoNewWindow

        Write-Host "[dev] web (nodemon)..."
        if (-not (Test-Path $nodemon)) {
            throw "nodemon absent. Lance: cd web && npm ci"
        }
        $procs += Start-Process -FilePath $node -ArgumentList $nodemon, "server.js" `
            -WorkingDirectory $webDir -PassThru -NoNewWindow
    } else {
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
    }

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
