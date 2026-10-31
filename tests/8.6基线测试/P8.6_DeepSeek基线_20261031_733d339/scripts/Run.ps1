param([ValidateSet('offline','smoke','formal')][string]$Mode='smoke')
$ErrorActionPreference='Stop'
$round=Split-Path -Parent $PSScriptRoot
$repo=Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $round))
$python=Join-Path $repo 'tests\garin\V1_分阶段验收_20261016_a251aa0\.runtime\ai\Scripts\python.exe'
$priorKey=$env:DEEPSEEK_API_KEY;$priorModel=$env:LLM_MODEL;$secure=$null;$bstr=[IntPtr]::Zero
$env:PYTHONIOENCODING='utf-8'
try {
    if ($Mode -ne 'offline' -and [string]::IsNullOrWhiteSpace($env:DEEPSEEK_API_KEY)) {
        $file=Join-Path $env:LOCALAPPDATA 'GarinAIModelTest\deepseek-key.dpapi'
        if (Test-Path -LiteralPath $file) {
            $secure=ConvertTo-SecureString -String ([IO.File]::ReadAllText($file).Trim())
            $bstr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
            $env:DEEPSEEK_API_KEY=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        }
    }
    $env:LLM_MODEL='deepseek-flash'
    & $python (Join-Path $PSScriptRoot 'runner.py') $Mode
    $result=$LASTEXITCODE
} finally {
    $env:DEEPSEEK_API_KEY=$priorKey;$env:LLM_MODEL=$priorModel
    if ($bstr -ne [IntPtr]::Zero) {[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)}
    if ($secure) {$secure.Dispose()}
}
exit $result
