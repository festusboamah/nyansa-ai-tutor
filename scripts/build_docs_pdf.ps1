param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$OutputPath = (Join-Path (Split-Path -Parent $PSScriptRoot) "output\pdf\Nyansa-Project-Documentation.pdf")
)

$ErrorActionPreference = "Stop"

function Encode-Inline([string]$Text) {
    $encoded = [System.Net.WebUtility]::HtmlEncode($Text)
    $encoded = [regex]::Replace($encoded, '\[([^\]]+)\]\(([^)]+)\)', '<a href="$2">$1</a>')
    $encoded = [regex]::Replace($encoded, '`([^`]+)`', '<code>$1</code>')
    $encoded = [regex]::Replace($encoded, '\*\*([^*]+)\*\*', '<strong>$1</strong>')
    $encoded = [regex]::Replace($encoded, '(?<!\*)\*([^*]+)\*(?!\*)', '<em>$1</em>')
    return $encoded
}

function Convert-Markdown([string]$Markdown, [string]$DocumentId) {
    $Markdown = $Markdown.Replace([char]0x2014, '-').Replace([char]0x2013, '-')
    $Markdown = $Markdown.Replace([char]0x2011, '-').Replace([string][char]0x2192, '->')
    $Markdown = $Markdown.Replace([char]0x2018, "'").Replace([char]0x2019, "'")
    $Markdown = $Markdown.Replace([char]0x201C, '"').Replace([char]0x201D, '"')
    $Markdown = $Markdown.Replace([char]0x251C, '+').Replace([char]0x2514, '+')
    $Markdown = $Markdown.Replace([char]0x2500, '-').Replace([char]0x2502, '|')
    $lines = $Markdown -split "`r?`n"
    $html = New-Object System.Text.StringBuilder
    $paragraph = New-Object System.Collections.Generic.List[string]
    $listType = $null
    $inCode = $false
    $codeLines = New-Object System.Collections.Generic.List[string]
    $firstHeading = $true

    function Flush-Paragraph {
        if ($paragraph.Count -gt 0) {
            $joined = ($paragraph -join ' ').Trim()
            if ($joined) { [void]$html.AppendLine("<p>$(Encode-Inline $joined)</p>") }
            $paragraph.Clear()
        }
    }

    function Close-List {
        if ($listType) {
            [void]$html.AppendLine("</$listType>")
            Set-Variable -Name listType -Value $null -Scope 1
        }
    }

    for ($i = 0; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]

        if ($line -match '^```') {
            Flush-Paragraph
            Close-List
            if ($inCode) {
                $code = [System.Net.WebUtility]::HtmlEncode($codeLines -join "`n")
                [void]$html.AppendLine("<pre><code>$code</code></pre>")
                $codeLines.Clear()
                $inCode = $false
            } else {
                $inCode = $true
            }
            continue
        }

        if ($inCode) {
            $codeLines.Add($line)
            continue
        }

        if ($line -match '^\|.*\|\s*$' -and $i + 1 -lt $lines.Count -and $lines[$i + 1] -match '^\|(?:\s*:?-+:?\s*\|)+\s*$') {
            Flush-Paragraph
            Close-List
            $headers = $line.Trim('|').Split('|') | ForEach-Object { $_.Trim() }
            $i += 2
            [void]$html.AppendLine('<table><thead><tr>')
            foreach ($header in $headers) { [void]$html.AppendLine("<th>$(Encode-Inline $header)</th>") }
            [void]$html.AppendLine('</tr></thead><tbody>')
            while ($i -lt $lines.Count -and $lines[$i] -match '^\|.*\|\s*$') {
                $cells = $lines[$i].Trim('|').Split('|') | ForEach-Object { $_.Trim() }
                [void]$html.AppendLine('<tr>')
                foreach ($cell in $cells) { [void]$html.AppendLine("<td>$(Encode-Inline $cell)</td>") }
                [void]$html.AppendLine('</tr>')
                $i++
            }
            [void]$html.AppendLine('</tbody></table>')
            $i--
            continue
        }

        if ($line -match '^(#{1,4})\s+(.+)$') {
            Flush-Paragraph
            Close-List
            $level = $Matches[1].Length
            $title = $Matches[2]
            $slug = (($title.ToLowerInvariant() -replace '[^a-z0-9]+','-').Trim('-'))
            if ($firstHeading -and $level -eq 1) {
                [void]$html.AppendLine("<h1 id=`"$DocumentId`" class=`"section-title`">$(Encode-Inline $title)</h1>")
                $firstHeading = $false
            } else {
                [void]$html.AppendLine("<h$level id=`"$DocumentId-$slug`">$(Encode-Inline $title)</h$level>")
            }
            continue
        }

        if ($line -match '^>\s*(.*)$') {
            Flush-Paragraph
            Close-List
            [void]$html.AppendLine("<blockquote>$(Encode-Inline $Matches[1])</blockquote>")
            continue
        }

        if ($line -match '^[-*]\s+(.+)$') {
            Flush-Paragraph
            if ($listType -ne 'ul') { Close-List; [void]$html.AppendLine('<ul>'); $listType = 'ul' }
            [void]$html.AppendLine("<li>$(Encode-Inline $Matches[1])</li>")
            continue
        }

        if ($line -match '^\d+\.\s+(.+)$') {
            Flush-Paragraph
            if ($listType -ne 'ol') { Close-List; [void]$html.AppendLine('<ol>'); $listType = 'ol' }
            [void]$html.AppendLine("<li>$(Encode-Inline $Matches[1])</li>")
            continue
        }

        if ($line.Trim() -eq '') {
            Flush-Paragraph
            Close-List
            continue
        }

        if ($line.Trim() -eq '---') {
            Flush-Paragraph
            Close-List
            [void]$html.AppendLine('<hr>')
            continue
        }

        $paragraph.Add($line.Trim())
    }

    Flush-Paragraph
    Close-List
    return $html.ToString()
}

$documentFiles = @(
    @{ Path = "product-vision.md"; Id = "vision" },
    @{ Path = "product-requirements.md"; Id = "requirements" },
    @{ Path = "architecture.md"; Id = "architecture" },
    @{ Path = "domain-model.md"; Id = "domain-model" },
    @{ Path = "security-and-tenancy.md"; Id = "security" },
    @{ Path = "delivery-roadmap.md"; Id = "roadmap" },
    @{ Path = "engineering-workflow.md"; Id = "workflow" },
    @{ Path = "decisions\README.md"; Id = "decisions" }
)

$htmlParts = New-Object System.Collections.Generic.List[string]
foreach ($document in $documentFiles) {
    $source = Join-Path (Join-Path $ProjectRoot "docs") $document.Path
    $htmlParts.Add((Convert-Markdown (Get-Content -Raw -Encoding UTF8 -LiteralPath $source) $document.Id))
}

$tempDir = Join-Path $ProjectRoot "tmp\pdfs"
$outputDir = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $tempDir, $outputDir | Out-Null
$htmlPath = Join-Path $tempDir "nyansa-project-documentation.html"

$styles = @'
@page { size: A4; margin: 20mm 17mm 18mm; @bottom-center { content: "Nyansa Project Documentation  |  " counter(page); color: #667085; font: 8.5pt Arial, sans-serif; } }
@page:first { @bottom-center { content: none; } }
* { box-sizing: border-box; }
body { margin: 0; color: #172033; background: white; font: 10.2pt/1.52 Arial, sans-serif; }
.cover { page-break-after: always; height: 297mm; display: flex; flex-direction: column; justify-content: center; padding: 22mm 28mm; background: linear-gradient(145deg, #071c4d 0%, #0a377c 62%, #0d72c7 100%); color: white; margin: -20mm -17mm -18mm; }
.brand { font-size: 12pt; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; color: #82d7ff; }
.cover h1 { max-width: 150mm; margin: 22mm 0 7mm; color: white; font-size: 35pt; line-height: 1.08; letter-spacing: -0.03em; }
.cover .subtitle { max-width: 145mm; font-size: 16pt; line-height: 1.4; color: #d9edff; }
.cover .principle { margin-top: 25mm; padding-left: 6mm; border-left: 2.5mm solid #46c2ff; max-width: 132mm; font-size: 12pt; }
.cover .meta { margin-top: auto; font-size: 9.5pt; color: #c3daf3; }
.toc { page-break-after: always; }
.toc h1 { margin-top: 8mm; }
.toc ol { margin-top: 10mm; }
.toc li { margin: 4mm 0; font-size: 11pt; }
.toc a { text-decoration: none; color: #0a4c91; }
h1, h2, h3, h4 { color: #092e65; font-weight: 700; page-break-after: avoid; }
h1.section-title { page-break-before: always; margin: 0 0 10mm; padding: 0 0 4mm; border-bottom: 1.5mm solid #0d72c7; font-size: 24pt; letter-spacing: -0.02em; }
h2 { margin: 8mm 0 3mm; font-size: 16pt; }
h3 { margin: 6mm 0 2mm; font-size: 12.5pt; color: #174f88; }
h4 { margin: 5mm 0 2mm; font-size: 10.5pt; text-transform: uppercase; letter-spacing: .03em; }
p { margin: 0 0 3.2mm; orphans: 3; widows: 3; }
ul, ol { margin: 1mm 0 4mm 6mm; padding-left: 5mm; }
li { margin: 0 0 1.7mm; padding-left: 1.5mm; }
strong { color: #0b315f; }
blockquote { margin: 5mm 0; padding: 4mm 5mm; border-left: 1.5mm solid #24a8e0; background: #edf8ff; color: #123d67; font-size: 11pt; font-weight: 600; page-break-inside: avoid; }
code { font: 9pt Consolas, monospace; color: #8c2f39; background: #f3f5f7; padding: .3mm 1mm; border-radius: 1mm; }
pre { margin: 4mm 0; padding: 4mm; background: #101828; color: #e7eef7; border-radius: 2mm; white-space: pre-wrap; page-break-inside: avoid; }
pre code { color: inherit; background: transparent; padding: 0; }
table { width: 100%; margin: 4mm 0 6mm; border-collapse: collapse; font-size: 8.8pt; page-break-inside: auto; }
thead { display: table-header-group; }
tr { page-break-inside: avoid; }
th { padding: 2.5mm 2.8mm; color: white; background: #0a4c91; text-align: left; vertical-align: middle; }
td { padding: 2.5mm 2.8mm; border-bottom: .25mm solid #d7e1eb; vertical-align: top; }
tbody tr:nth-child(even) { background: #f6f9fc; }
hr { border: 0; border-top: .3mm solid #c9d6e4; margin: 7mm 0; }
a { color: #0869ad; }
.callout { margin: 8mm 0; padding: 5mm; background: #fff7df; border: .3mm solid #f0c85c; border-radius: 2mm; }
'@

$body = $htmlParts -join "`n"
$generatedDate = Get-Date -Format "MMMM d, yyyy"
$htmlDocument = @"
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Nyansa Project Documentation</title><style>$styles</style></head>
<body>
<section class="cover">
  <div class="brand">NYANSA</div>
  <h1>Project Documentation</h1>
  <div class="subtitle">From AI Tutoring Platform to a Multi-Tenant School Management System</div>
  <div class="principle"><strong style="color:white">Wrap, don't replace.</strong><br>The AI-powered academic engine remains at the center of the platform.</div>
  <div class="meta">Product and engineering blueprint<br>Prepared for implementation | $generatedDate</div>
</section>
<section class="toc">
  <h1>Contents</h1>
  <ol>
    <li><a href="#vision">Product Vision</a></li>
    <li><a href="#requirements">Product Requirements</a></li>
    <li><a href="#architecture">System Architecture</a></li>
    <li><a href="#domain-model">Domain Model</a></li>
    <li><a href="#security">Security and Data Isolation</a></li>
    <li><a href="#roadmap">Delivery Roadmap</a></li>
    <li><a href="#workflow">Engineering Workflow</a></li>
    <li><a href="#decisions">Architecture Decision Records</a></li>
  </ol>
  <div class="callout"><strong>Status:</strong> This handbook defines the intended target system. It does not claim that roadmap features are already implemented.</div>
</section>
$body
</body>
</html>
"@

[System.IO.File]::WriteAllText($htmlPath, $htmlDocument, [System.Text.UTF8Encoding]::new($false))

$chromeCandidates = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
)
$chrome = $chromeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $chrome) { throw "Chrome or Edge was not found." }

$profile = Join-Path $tempDir "chrome-profile"
New-Item -ItemType Directory -Force -Path $profile | Out-Null
$fileUrl = ([System.Uri]$htmlPath).AbsoluteUri
& $chrome --headless=new --disable-gpu --no-pdf-header-footer --allow-file-access-from-files --user-data-dir="$profile" --print-to-pdf="$OutputPath" $fileUrl
if (-not (Test-Path -LiteralPath $OutputPath) -or (Get-Item -LiteralPath $OutputPath).Length -eq 0) {
    throw "PDF generation failed."
}

Write-Output $OutputPath
