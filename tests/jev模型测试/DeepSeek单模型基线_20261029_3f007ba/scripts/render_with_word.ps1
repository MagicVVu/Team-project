param([Parameter(Mandatory=$true)][string]$DocumentPath,[Parameter(Mandatory=$true)][string]$PdfPath)
$ErrorActionPreference='Stop'
$round=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))+[IO.Path]::DirectorySeparatorChar
$document=[IO.Path]::GetFullPath($DocumentPath);$pdf=[IO.Path]::GetFullPath($PdfPath)
if (-not $document.StartsWith($round,[StringComparison]::OrdinalIgnoreCase) -or -not $pdf.StartsWith($round,[StringComparison]::OrdinalIgnoreCase)) { throw 'Paths must stay in the current Garin round' }
$word=$null;$doc=$null
try {
    $word=New-Object -ComObject Word.Application
    $word.Visible=$false;$word.DisplayAlerts=0
    $doc=$word.Documents.Open($document,$false,$true)
    $doc.Repaginate();Write-Output ('Pages: '+$doc.ComputeStatistics(2))
    $doc.ExportAsFixedFormat($pdf,17)
} finally {
    if ($null -ne $doc) { $doc.Close(0);[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($doc) }
    if ($null -ne $word) { $word.Quit();[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) }
}
