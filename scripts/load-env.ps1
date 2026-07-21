# Charge .env.local (mode local) ou .env (prod / defaut).
# Usage: . .\scripts\load-env.ps1 -Local

param(
    [switch]$Local
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$UseLocal = $Local -or ($env:STREAMNEWS_ENV -eq "local")

if ($UseLocal) {
    $EnvFile = ".env.local"
    if (-not (Test-Path $EnvFile)) {
        if (Test-Path ".env.local.example") {
            Copy-Item ".env.local.example" $EnvFile
            Write-Host "Fichier .env.local cree depuis .env.local.example"
        } else {
            throw "Fichier .env.local manquant. Copie .env.local.example vers .env.local."
        }
    }
} else {
    $EnvFile = ".env"
    if (-not (Test-Path $EnvFile)) {
        if (Test-Path ".env.example") {
            Copy-Item ".env.example" $EnvFile
            Write-Host "Fichier .env cree depuis .env.example"
        } else {
            throw "Fichier .env manquant."
        }
    }
}

Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) { return }
    $eq = $line.IndexOf("=")
    if ($eq -lt 1) { return }
    $name = $line.Substring(0, $eq).Trim()
    $value = $line.Substring($eq + 1).Trim()
    if (
        ($value.StartsWith('"') -and $value.EndsWith('"')) -or
        ($value.StartsWith("'") -and $value.EndsWith("'"))
    ) {
        $value = $value.Substring(1, $value.Length - 2)
    }
    Set-Item -Path "Env:$name" -Value $value
}

Write-Host "Env charge: $EnvFile (STREAMNEWS_ENV=$($env:STREAMNEWS_ENV))"

if (-not $UseLocal) {
    $pw = $env:POSTGRES_PASSWORD
    $url = $env:DATABASE_URL
    if (($pw -eq "CHANGE_ME") -or ($url -match "CHANGE_ME")) {
        Write-Host "ATTENTION: Postgres non configure (CHANGE_ME dans .env)."
    }
}
