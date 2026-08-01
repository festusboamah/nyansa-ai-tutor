param(
    [Parameter(Mandatory = $true)][string]$DatabaseUrl,
    [Parameter(Mandatory = $true)][string]$BackupPath,
    [Parameter(Mandatory = $true)][ValidateSet("RESTORE")][string]$Confirm
)

$ErrorActionPreference = "Stop"
$resolvedBackup = [System.IO.Path]::GetFullPath($BackupPath)
if (-not (Test-Path -LiteralPath $resolvedBackup -PathType Leaf)) {
    throw "Backup file does not exist: $resolvedBackup"
}
if (-not (Get-Command pg_restore -ErrorAction SilentlyContinue)) {
    throw "pg_restore is required and was not found on PATH."
}

Write-Warning "This replaces objects in the explicitly supplied target database."
& pg_restore --clean --if-exists --no-owner --no-acl --exit-on-error --dbname=$DatabaseUrl $resolvedBackup
if ($LASTEXITCODE -ne 0) { throw "pg_restore failed with exit code $LASTEXITCODE." }
Write-Output "Restore completed from $resolvedBackup"
