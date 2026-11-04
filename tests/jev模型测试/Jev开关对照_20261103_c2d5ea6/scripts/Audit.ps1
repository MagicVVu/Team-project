$ErrorActionPreference='Stop'
$round=Split-Path -Parent $PSScriptRoot
$repo=Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $round))
$python=Join-Path $repo 'tests\garin\V1_分阶段验收_20261016_a251aa0\.runtime\ai\Scripts\python.exe'
$private=Join-Path $env:LOCALAPPDATA 'GarinAIModelTest'
$old=@{};$pointers=@();$secrets=@()
try {
 foreach($entry in @(@('DEEPSEEK_API_KEY','deepseek-key.dpapi'),@('TYPESAFE_API_KEY','typesafe-key.dpapi'))){
  $old[$entry[0]]=[Environment]::GetEnvironmentVariable($entry[0],'Process')
  $secure=ConvertTo-SecureString -String ([IO.File]::ReadAllText((Join-Path $private $entry[1])).Trim())
  $secrets+=,$secure;$pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure);$pointers+=,$pointer
  [Environment]::SetEnvironmentVariable($entry[0],[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer),'Process')
 }
 & $python (Join-Path $PSScriptRoot 'final_audit.py');$result=$LASTEXITCODE
} finally {
 foreach($key in $old.Keys){[Environment]::SetEnvironmentVariable($key,$old[$key],'Process')}
 foreach($pointer in $pointers){[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)}
 foreach($secure in $secrets){$secure.Dispose()}
}
exit $result
