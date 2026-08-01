param(
    [Parameter(Mandatory = $true)][string]$DatabaseUrl,
    [Parameter(Mandatory = $true)][string]$OutputDirectory
)

$ErrorActionPreference = "Stop"
$resolvedOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $resolvedOutput | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPath = Join-Path $resolvedOutput "nyansa-$stamp.dump"
$manifestPath = Join-Path $resolvedOutput "nyansa-$stamp.sha256"

if (-not (Get-Command pg_dump -ErrorAction SilentlyContinue)) {
    throw "pg_dump is required and was not found on PATH."
}

& pg_dump --format=custom --no-owner --no-acl --dbname=$DatabaseUrl --file=$backupPath
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed with exit code $LASTEXITCODE." }
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $backupPath).Hash.ToLowerInvariant()
"$hash  $([System.IO.Path]::GetFileName($backupPath))" | Set-Content -LiteralPath $manifestPath -Encoding ascii
Write-Output "Backup: $backupPath"
Write-Output "SHA-256: $hash"
