# Install deps Windows (venv Python + npm).
# Usage: .\scripts\install.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Fichier .env cree depuis .env.example"
}
if (-not (Test-Path ".env.local")) {
    Copy-Item ".env.local.example" ".env.local"
    Write-Host "Fichier .env.local cree depuis .env.local.example"
}

New-Item -ItemType Directory -Force -Path "data" | Out-Null

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Pip = Join-Path $Root ".venv\Scripts\pip.exe"

& $Python -m pip install --upgrade pip

$reqFile = Join-Path $Root "analyzer\requirements.txt"
& $Pip install -r $reqFile
if ($LASTEXITCODE -ne 0) {
    Write-Host "Install pinne echoue (Windows + Python 3.13)."
    Write-Host "Mode local SQLite: deps essentielles sans versions figees..."
    & $Pip install aiosqlite fastapi uvicorn requests beautifulsoup4 lxml feedparser `
        redis celery aiohttp urllib3 pydantic sqlalchemy alembic python-multipart trafilatura bleach
    if ($LASTEXITCODE -ne 0) { throw "Echec installation des dependances Python." }
}

Push-Location web
npm ci
Pop-Location

Write-Host "Install OK."
Write-Host "  Local (SQLite + Redis node14) : .\scripts\init-db.ps1 -Local; .\scripts\dev.ps1 -Local"
Write-Host "  Prod-like (.env Postgres)     : edite .env (remplace CHANGE_ME), puis init-db + dev"
if ((Get-Content ".env" -Raw) -match "CHANGE_ME") {
    Write-Host "ATTENTION: .env contient encore CHANGE_ME - a remplacer avant un usage Postgres."
}
