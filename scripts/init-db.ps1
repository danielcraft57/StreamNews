# Initialise le schema DB (SQLite local ou Postgres).
# Usage: .\scripts\init-db.ps1 -Local
#        .\scripts\init-db.ps1 -Local -Reset

param(
    [switch]$Local,
    [switch]$Reset
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

. (Join-Path $Root "scripts\load-env.ps1") @PSBoundParameters

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "venv absent. Lance d'abord: .\scripts\install.ps1"
}

if ($Reset) {
    Write-Host "ATTENTION: recreate complete du schema (DROP tables)."
}

if ($env:DATABASE_URL -match "^sqlite") {
    New-Item -ItemType Directory -Force -Path "data" | Out-Null
}

if ($Reset) { $env:STREAMNEWS_RESET_DB = "1" }

$dbUrl = if ($env:DATABASE_URL) { $env:DATABASE_URL -replace '\?.*', '' } else { '?' }
Write-Host "[init-db] env=$($env:STREAMNEWS_ENV) url=$dbUrl"
Write-Host "[init-db] lancement Python..."

Push-Location analyzer
if ($Reset) {
    & $Python -u init_db_cli.py --reset
} else {
    & $Python -u init_db_cli.py
}
if ($LASTEXITCODE -ne 0) { throw "init-db a echoue (code $LASTEXITCODE)" }
Pop-Location

Write-Host "Base initialisee ($($env:STREAMNEWS_ENV))."
