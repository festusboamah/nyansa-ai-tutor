param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$BackupRoot = (Join-Path (Split-Path -Parent $PSScriptRoot) "backups")
)

$ErrorActionPreference = "Stop"
$project = (Resolve-Path -LiteralPath $ProjectRoot).Path
$database = Join-Path $project "db.sqlite3"
$media = Join-Path $project "media"

if (-not (Test-Path -LiteralPath $database -PathType Leaf)) {
    throw "Database not found: $database"
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$destination = Join-Path $BackupRoot "nyansa-$timestamp"
$resolvedParent = [IO.Path]::GetFullPath($BackupRoot)
$resolvedDestination = [IO.Path]::GetFullPath($destination)
if (-not $resolvedDestination.StartsWith($resolvedParent + [IO.Path]::DirectorySeparatorChar)) {
    throw "Refusing to create a backup outside the requested backup root."
}

New-Item -ItemType Directory -Force -Path $destination | Out-Null
Copy-Item -LiteralPath $database -Destination (Join-Path $destination "db.sqlite3")
if (Test-Path -LiteralPath $media -PathType Container) {
    Copy-Item -LiteralPath $media -Destination (Join-Path $destination "media") -Recurse
}

$databaseCopy = Join-Path $destination "db.sqlite3"
$mediaFiles = if (Test-Path -LiteralPath (Join-Path $destination "media")) {
    @(Get-ChildItem -LiteralPath (Join-Path $destination "media") -Recurse -File)
} else {
    @()
}
$manifest = [ordered]@{
    created_at = (Get-Date).ToUniversalTime().ToString("o")
    source_project = $project
    database = [ordered]@{
        filename = "db.sqlite3"
        bytes = (Get-Item -LiteralPath $databaseCopy).Length
        sha256 = (Get-FileHash -LiteralPath $databaseCopy -Algorithm SHA256).Hash
    }
    media = [ordered]@{
        included = (Test-Path -LiteralPath (Join-Path $destination "media"))
        file_count = $mediaFiles.Count
        total_bytes = ($mediaFiles | Measure-Object -Property Length -Sum).Sum
    }
}
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $destination "manifest.json") -Encoding UTF8

Write-Output $destination
