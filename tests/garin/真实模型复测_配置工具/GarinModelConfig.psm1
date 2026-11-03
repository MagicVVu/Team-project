Set-StrictMode -Version Latest
function Get-GarinModelConfigDirectory {
    if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw 'LOCALAPPDATA is unavailable' }
    return (Join-Path $env:LOCALAPPDATA 'GarinAIModelTest')
}
function Get-GarinModelConfigInfo {
    $dir=Get-GarinModelConfigDirectory
    $keyFile=Join-Path $dir 'deepseek-key.dpapi'
    $settingsFile=Join-Path $dir 'model-settings.json'
    $present=(Test-Path -LiteralPath $keyFile) -and (Test-Path -LiteralPath $settingsFile)
    if (-not $present) { return [pscustomobject]@{configured=$false;decryptable=$false;model=$null;model_called=$false;charges_incurred=$false} }
    $secret=$null
    try {
        $settings=Get-Content -LiteralPath $settingsFile -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($settings.provider -ne 'deepseek' -or $settings.model -ne 'deepseek-flash') { throw 'Unexpected provider or model' }
        $encrypted=(Get-Content -LiteralPath $keyFile -Raw -Encoding ASCII).Trim()
        $secret=ConvertTo-SecureString -String $encrypted
        return [pscustomobject]@{configured=$true;decryptable=($secret.Length -gt 0);model=$settings.model;model_called=$false;charges_incurred=$false}
    } catch {
        return [pscustomobject]@{configured=$true;decryptable=$false;model=$null;model_called=$false;charges_incurred=$false}
    } finally { if ($null -ne $secret) { $secret.Dispose() } }
}
Export-ModuleMember -Function Get-GarinModelConfigDirectory,Get-GarinModelConfigInfo
