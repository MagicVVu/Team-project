param([ValidateSet('all','unit','assemble')][string]$Mode='all')
$ErrorActionPreference='Stop'
$GarinRoot=$PSScriptRoot
$GarinAllowed='D:\Team_Project\Team-project\tests\garin'
if ((Split-Path -Parent (Resolve-Path -LiteralPath $GarinRoot).Path) -ne $GarinAllowed) { throw 'Runner must stay in a new Garin round folder' }
$GarinLabel=if ($Mode -eq 'all') {'android-build'} else {'android-'+$Mode}
if (Test-Path -LiteralPath (Join-Path $GarinRoot ('evidence\'+$GarinLabel+'.log'))) { throw 'Existing evidence is immutable; capture a new round before rerunning' }
if (Test-Path 'V:\') { throw 'V drive is in use; do not alter it' }
& subst.exe V: $GarinRoot
if ($LASTEXITCODE -ne 0) { throw 'Failed to create temporary ASCII path alias' }
$GarinFront='V:\.snapshot\frontend'
$env:JAVA_HOME='E:\Development\SDKs\Java\jdk-21.0.12+8'
$env:ANDROID_HOME='E:\Development\SDKs\Android'
$env:GRADLE_USER_HOME='V:\.runtime\gradle-home'
$env:PATH=(Join-Path $env:JAVA_HOME 'bin')+';'+$env:PATH
Push-Location -LiteralPath $GarinFront
try {
    $GarinArguments=@('--offline','--no-daemon','--console=plain','--stacktrace','-Dorg.gradle.java.installations.auto-download=false','-Dorg.gradle.java.installations.paths=E:\Development\SDKs\Java\jdk-21.0.12+8','-Pandroid.builder.sdkDownload=false','-Pandroid.overridePathCheck=true','-PmagicvvuApiUrl=http://10.0.2.2:18081')
    $GarinArguments+=if ($Mode -eq 'unit') {@('testDebugUnitTest')} elseif ($Mode -eq 'assemble') {@('assembleDebug')} else {@('assembleDebug','testDebugUnitTest','lintDebug')}
    [ordered]@{working_directory=$GarinFront;java_home=$env:JAVA_HOME;android_home=$env:ANDROID_HOME;gradle_user_home=$env:GRADLE_USER_HOME;arguments=$GarinArguments;installs_apk=$false;connects_service=$false} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $GarinRoot ('evidence\'+$GarinLabel+'-command.json')) -Encoding utf8
    & (Join-Path $GarinFront 'gradlew.bat') @GarinArguments *> (Join-Path $GarinRoot ('evidence\'+$GarinLabel+'.log'))
    $GarinExit=$LASTEXITCODE
    Get-Content -LiteralPath (Join-Path $GarinRoot ('evidence\'+$GarinLabel+'.log')) -Tail 25
    exit $GarinExit
} finally { Pop-Location; & subst.exe V: /D }

