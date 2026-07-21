# Nettoyage fichiers locaux (hors git). Ne touche pas aux .env.
# Usage: .\scripts\clean-local.ps1 [-KeepDb]

param(
    [switch]$KeepDb
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "[clean] caches pytest / mypy / ruff..."
@(".pytest_cache", "analyzer\.pytest_cache", "analyzer\.pytest_tmp", ".mypy_cache", ".ruff_cache") | ForEach-Object {
    if (Test-Path $_) {
        Remove-Item -Recurse -Force $_
        Write-Host "  supprime $_"
    }
}

if (-not $KeepDb) {
    Write-Host "[clean] base SQLite locale..."
    Get-ChildItem "data" -Filter "streamnews.db*" -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            Remove-Item -Force $_.FullName -ErrorAction Stop
            Write-Host "  supprime $($_.Name)"
        } catch {
            Write-Host "  ignore $($_.Name) (fichier verrouille - arrete dev/worker puis relance)"
        }
    }
}

Write-Host "[clean] logs (garde .gitkeep)..."
Get-ChildItem "logs" -Filter "*.log" -ErrorAction SilentlyContinue | ForEach-Object {
    Clear-Content $_.FullName
    Write-Host "  vide $($_.Name)"
}

Write-Host "Nettoyage termine."
