param([ValidateSet('check','preflight','smoke','formal','continuation')][string]$Phase='check')
$ErrorActionPreference='Stop'
$round=Split-Path -Parent $PSScriptRoot
$repo=Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $round))
$python=Join-Path $repo 'tests\garin\V1_分阶段验收_20261016_a251aa0\.runtime\ai\Scripts\python.exe'
$private=Join-Path $env:LOCALAPPDATA 'GarinAIModelTest'
if($Phase -eq 'check'){
 foreach($entry in @(@('DeepSeek','deepseek-key.dpapi'),@('TypeSafe','typesafe-key.dpapi'))){[PSCustomObject]@{Provider=$entry[0];EncryptedFilePresent=(Test-Path -LiteralPath (Join-Path $private $entry[1]))}}
 Write-Output 'No model request was made.';exit 0
}
$oldDeep=$env:DEEPSEEK_API_KEY;$oldJev=$env:TYPESAFE_API_KEY;$oldModel=$env:LLM_MODEL;$oldToken=$env:AI_SERVICE_TOKEN
$secrets=@();$pointers=@()
$env:PYTHONIOENCODING='utf-8';$env:PYTHONUTF8='1'
try {
 if($Phase -ne 'preflight'){
  foreach($entry in @(@('DEEPSEEK_API_KEY','deepseek-key.dpapi'),@('TYPESAFE_API_KEY','typesafe-key.dpapi'))){
   $file=Join-Path $private $entry[1]
   if(-not(Test-Path -LiteralPath $file)){throw ('Missing encrypted local credential: '+$entry[0])}
   $secure=ConvertTo-SecureString -String ([IO.File]::ReadAllText($file).Trim())
   $secrets+=,$secure;$pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure);$pointers+=,$pointer
   [Environment]::SetEnvironmentVariable($entry[0],[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer),'Process')
  }
 }
 $env:LLM_MODEL='deepseek-flash'
 if($Phase -eq 'continuation'){& $python (Join-Path $PSScriptRoot 'continuation.py')}
 else {& $python (Join-Path $PSScriptRoot 'ab.py') $Phase}
 $code=$LASTEXITCODE
} finally {
 $env:DEEPSEEK_API_KEY=$oldDeep;$env:TYPESAFE_API_KEY=$oldJev;$env:LLM_MODEL=$oldModel;$env:AI_SERVICE_TOKEN=$oldToken
 foreach($pointer in $pointers){[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)}
 foreach($secure in $secrets){$secure.Dispose()}
}
exit $code
