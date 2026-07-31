param(
    [Parameter(Mandatory = $true)][string]$InputPdf,
    [Parameter(Mandatory = $true)][string]$OutputDirectory
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime] | Out-Null

$asTaskMethods = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' }
$asTaskGeneric = $asTaskMethods | Where-Object {
    $_.IsGenericMethod -and $_.GetGenericArguments().Count -eq 1 -and $_.GetParameters().Count -eq 1
} | Select-Object -First 1
$asTaskAction = $asTaskMethods | Where-Object {
    -not $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction'
} | Select-Object -First 1

function Await-Result($Operation, [Type]$ResultType) {
    $method = $asTaskGeneric.MakeGenericMethod($ResultType)
    $task = $method.Invoke($null, @($Operation))
    $task.Wait()
    return $task.Result
}

function Await-Action($Operation) {
    $task = $asTaskAction.Invoke($null, @($Operation))
    $task.Wait()
}

$resolvedPdf = (Resolve-Path -LiteralPath $InputPdf).Path
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$storageFile = Await-Result ([Windows.Storage.StorageFile]::GetFileFromPathAsync($resolvedPdf)) ([Windows.Storage.StorageFile])
$pdf = Await-Result ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($storageFile)) ([Windows.Data.Pdf.PdfDocument])

for ($index = 0; $index -lt $pdf.PageCount; $index++) {
    $page = $pdf.GetPage($index)
    $randomStream = [Windows.Storage.Streams.InMemoryRandomAccessStream]::new()
    try {
        Await-Action ($page.RenderToStreamAsync($randomStream))
        $randomStream.Seek(0)
        $dotNetStream = [System.IO.WindowsRuntimeStreamExtensions]::AsStreamForRead($randomStream)
        $outputPath = Join-Path $OutputDirectory ("page-{0:D2}.png" -f ($index + 1))
        $fileStream = [System.IO.File]::Create($outputPath)
        try { $dotNetStream.CopyTo($fileStream) } finally { $fileStream.Dispose(); $dotNetStream.Dispose() }
    } finally {
        $randomStream.Dispose()
        $page.Dispose()
    }
}

Write-Output "Rendered $($pdf.PageCount) pages to $OutputDirectory"
