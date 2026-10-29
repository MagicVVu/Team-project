$ErrorActionPreference='Stop'
$round=Split-Path -Parent $PSScriptRoot
$repo=Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $round))
$python=Join-Path $repo 'tests\garin\V1_分阶段验收_20261016_a251aa0\.runtime\ai\Scripts\python.exe'
$oldKey=$env:DEEPSEEK_API_KEY;$secure=$null;$bstr=[IntPtr]::Zero
try {
    $path=Join-Path $env:LOCALAPPDATA 'GarinAIModelTest\deepseek-key.dpapi'
    if ([string]::IsNullOrWhiteSpace($env:DEEPSEEK_API_KEY) -and (Test-Path -LiteralPath $path)) {
        $secure=ConvertTo-SecureString -String ([IO.File]::ReadAllText($path).Trim())
        $bstr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        $env:DEEPSEEK_API_KEY=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    }
    & $python (Join-Path $PSScriptRoot 'audit_delivery.py')
    $result=$LASTEXITCODE
} finally {
    $env:DEEPSEEK_API_KEY=$oldKey
    if ($bstr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    if ($null -ne $secure) { $secure.Dispose() }
}
exit $result
