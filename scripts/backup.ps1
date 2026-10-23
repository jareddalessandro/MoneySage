# Back up the MoneySage database to backups\moneysage-YYYY-MM-DD_HHmm.dump
# Usage (from the project folder):  .\scripts\backup.ps1
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

$stamp = Get-Date -Format 'yyyy-MM-dd_HHmm'
$file = "backups\moneysage-$stamp.dump"
New-Item -ItemType Directory -Force backups | Out-Null

# Dump inside the container, then copy out (PowerShell's > would mangle the binary dump).
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/moneysage.dump'
if ($LASTEXITCODE -ne 0) { throw 'pg_dump failed. Is the app running? (docker compose up -d)' }
docker compose cp db:/tmp/moneysage.dump $file
if ($LASTEXITCODE -ne 0) { throw 'Copying the backup out of the container failed.' }
docker compose exec -T db rm /tmp/moneysage.dump

Write-Host "Backup saved to $file"
