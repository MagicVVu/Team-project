param([ValidateSet('offline','smoke','formal','report')][string]$Mode='smoke')
$ErrorActionPreference='Stop'
$round=Split-Path -Parent $PSScriptRoot
$repo=Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $round))
$runtime=Join-Path $repo 'tests\garin\V1_分阶段验收_20261016_a251aa0\.runtime\ai\Scripts\python.exe'
if (Test-Path -LiteralPath (Join-Path $round '.runtime\ai\Scripts\python.exe')) { $runtime=Join-Path $round '.runtime\ai\Scripts\python.exe' }
if (-not [string]::IsNullOrWhiteSpace($env:GARIN_AI_PYTHON)) { $runtime=$env:GARIN_AI_PYTHON }
if (-not (Test-Path -LiteralPath $runtime)) { throw 'Python environment missing; configure an isolated Python 3.12/3.13 environment from snapshot requirements.lock.txt.' }
$oldKey=$env:DEEPSEEK_API_KEY
$secure=$null; $bstr=[IntPtr]::Zero
try {
    if ([string]::IsNullOrWhiteSpace($env:DEEPSEEK_API_KEY) -and $Mode -in @('smoke','formal')) {
        $keyPath=Join-Path $env:LOCALAPPDATA 'GarinAIModelTest\deepseek-key.dpapi'
        if (Test-Path -LiteralPath $keyPath) {
            $secure=ConvertTo-SecureString -String ([IO.File]::ReadAllText($keyPath).Trim())
            $bstr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
            $env:DEEPSEEK_API_KEY=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        } else {
            $env:DEEPSEEK_API_KEY=[Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY','User')
        }
    }
    # The source default is frozen. A machine-wide model override must not change the baseline.
    $oldModel=$env:LLM_MODEL
    $env:LLM_MODEL='deepseek-flash'
    if ($Mode -eq 'report') { & $runtime (Join-Path $PSScriptRoot 'summarize.py') }
    else { & $runtime (Join-Path $PSScriptRoot 'run.py') $Mode }
    $result=$LASTEXITCODE
} finally {
    $env:DEEPSEEK_API_KEY=$oldKey
    $env:LLM_MODEL=$oldModel
    if ($bstr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    if ($null -ne $secure) { $secure.Dispose() }
}
exit $result
