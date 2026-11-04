param([string]$DocumentPath,[string]$PdfPath)
$ErrorActionPreference='Stop'
$base=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))+[IO.Path]::DirectorySeparatorChar
$document=[IO.Path]::GetFullPath($DocumentPath);$pdf=[IO.Path]::GetFullPath($PdfPath)
if(-not $document.StartsWith($base,[StringComparison]::OrdinalIgnoreCase) -or -not $pdf.StartsWith($base,[StringComparison]::OrdinalIgnoreCase)){throw 'Render paths must stay in this Garin round'}
$word=$null;$doc=$null;$owns=$false
try {
 $word=New-Object -ComObject Word.Application
 $owns=($word.Documents.Count -eq 0)
 if(-not $owns){throw 'Renderer did not obtain a fresh empty Word instance'}
 $word.Visible=$false;$word.DisplayAlerts=0
 $doc=$word.Documents.Open($document,$false,$true)
 $doc.Repaginate();Write-Output ('Pages: '+$doc.ComputeStatistics(2))
 $doc.ExportAsFixedFormat($pdf,17)
} finally {
 if($doc){$doc.Close(0);[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($doc)}
 if($word){if($owns){$word.Quit()};[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($word)}
}
