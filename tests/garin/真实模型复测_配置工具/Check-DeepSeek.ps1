param([switch]$SelfTest)
$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSScriptRoot 'GarinModelConfig.psm1') -Force
if ($SelfTest) {
    $plain='garin-synthetic-not-an-api-key'
    $secure=ConvertTo-SecureString $plain -AsPlainText -Force
    $restored=$null
    $ptr=[IntPtr]::Zero
    try {
        $blob=ConvertFrom-SecureString $secure
        $restored=ConvertTo-SecureString $blob
        $ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($restored)
        $passed=([Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) -ceq $plain) -and (-not $blob.Contains($plain))
        [ordered]@{synthetic_dpapi_roundtrip=$passed;persisted_key=$false;model_called=$false;charges_incurred=$false} | ConvertTo-Json
        if (-not $passed) { exit 1 }
    } finally {
        if ($ptr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
        if ($null -ne $restored) { $restored.Dispose() };$secure.Dispose()
    }
} else { Get-GarinModelConfigInfo | ConvertTo-Json }
