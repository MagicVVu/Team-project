param([ValidateSet('offline','online')][string]$Mode='offline')
$ErrorActionPreference='Stop'
$GarinRoot=(Resolve-Path -LiteralPath $PSScriptRoot).Path
if ($GarinRoot -ne 'D:\Team_Project\Team-project\tests\garin\MuMu更新_20261028_aea6411') { throw 'Build must stay in the new Garin update round' }
$GarinLog=Join-Path $GarinRoot ('evidence\build-'+$Mode+'.log')
if (Test-Path -LiteralPath $GarinLog) { throw 'Existing build log must not be overwritten' }
if (Test-Path 'V:\') { throw 'V drive is already in use' }
$env:JAVA_HOME='E:\Development\SDKs\Java\jdk-21.0.12+8'
$env:ANDROID_HOME='E:\Development\SDKs\Android'
$env:ANDROID_USER_HOME=Join-Path $env:USERPROFILE '.android'
$env:GRADLE_USER_HOME='V:\.runtime\gradle-home'
$env:PATH=(Join-Path $env:JAVA_HOME 'bin')+';'+$env:PATH
$GarinArguments=@('--no-daemon','--console=plain','--stacktrace','--max-workers=2','-Dorg.gradle.java.installations.auto-download=false','-Dorg.gradle.java.installations.paths=E:\Development\SDKs\Java\jdk-21.0.12+8','-Pandroid.builder.sdkDownload=false','-Pandroid.overridePathCheck=true','assembleDebug')
if ($Mode -eq 'offline') {$GarinArguments=@('--offline')+$GarinArguments}
& subst.exe V: $GarinRoot
if ($LASTEXITCODE -ne 0) { throw 'Unable to create temporary ASCII path' }
$GarinPushed=$false
try {
    Push-Location -LiteralPath 'V:\.snapshot\frontend';$GarinPushed=$true
    [ordered]@{working_directory='V:\.snapshot\frontend';mode=$Mode;arguments=$GarinArguments;source_commit='aea6411d868ff30e64ab440239de8bbba7059f09';uses_existing_user_debug_key=$true;installs_app=$false;connects_business_service=$false;calls_models=$false} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $GarinRoot ('evidence\build-'+$Mode+'-command.json')) -Encoding utf8
    & '.\gradlew.bat' @GarinArguments *> $GarinLog
    $GarinExit=$LASTEXITCODE
    [ordered]@{exit_code=$GarinExit;finished_at=(Get-Date).ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $GarinRoot ('evidence\build-'+$Mode+'-result.json')) -Encoding utf8
    Get-Content -LiteralPath $GarinLog -Tail 24
} finally {
    if ($GarinPushed) { Pop-Location }
    & subst.exe V: /D
}
exit $GarinExit
