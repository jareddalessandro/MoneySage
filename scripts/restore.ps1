# Restore MoneySage from a backup file. This REPLACES all current data.
# Usage (from the project folder):  .\scripts\restore.ps1 backups\moneysage-2026-10-22_1700.dump
param([Parameter(Mandatory = $true)][string]$BackupFile)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path $BackupFile)) { throw "Backup file not found: $BackupFile" }

$answer = Read-Host "This replaces ALL current MoneySage data with $BackupFile. Type 'yes' to continue"
if ($answer -ne 'yes') { Write-Host 'Cancelled.'; exit 1 }

docker compose stop backend
docker compose cp $BackupFile db:/tmp/restore.dump
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner /tmp/restore.dump && rm /tmp/restore.dump'
$restoreExit = $LASTEXITCODE
docker compose start backend

if ($restoreExit -ne 0) { throw 'pg_restore reported errors (see above).' }
Write-Host 'Restore complete.'
