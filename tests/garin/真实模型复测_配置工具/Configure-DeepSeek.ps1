$ErrorActionPreference='Stop'
Import-Module (Join-Path $PSScriptRoot 'GarinModelConfig.psm1') -Force
$secret=$null
try {
    Write-Host 'Garin 真实模型测试配置'
    Write-Host '本工具只保存本机加密配置，不调用模型、不扣费、不修改团队源码。'
    Write-Host '模型：deepseek-flash。密钥不要发给聊天窗口或GitHub。'
    $dir=Get-GarinModelConfigDirectory
    $keyFile=Join-Path $dir 'deepseek-key.dpapi'
    if (Test-Path -LiteralPath $keyFile) {
        $answer=Read-Host '已存在本机配置，输入 YES 才替换，否则退出'
        if ($answer -cne 'YES') { Write-Host '原配置保留。'; exit 0 }
    }
    $secret=Read-Host '请粘贴你自己的DeepSeek API Key后按回车（内容隐藏）' -AsSecureString
    if ($secret.Length -eq 0) { Write-Host '没有输入密钥，未保存。'; exit 1 }
    $encrypted=ConvertFrom-SecureString -SecureString $secret
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
    [IO.File]::WriteAllText($keyFile,$encrypted,[Text.Encoding]::ASCII)
    $settings=[ordered]@{provider='deepseek';model='deepseek-flash';created_at=(Get-Date).ToString('o');storage='Windows DPAPI current user';budget_approved=$false;api_validated=$false}
    $settings | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dir 'model-settings.json') -Encoding UTF8
    $info=Get-GarinModelConfigInfo
    if (-not $info.decryptable) { throw 'Local encryption check failed' }
    Write-Host ''
    Write-Host '本机配置已保存，加密读回检查通过。'
    Write-Host ('存放目录：'+$dir+'（仓库外，不要复制到Git）')
    Write-Host '尚未验证密钥是否有效或账户是否有余额，因为本工具不连接网络。'
    Write-Host '下一步：告诉Codex“密钥已配置”，并明确本轮费用上限，例如1元。'
} catch {
    Write-Host '配置未完成。请检查当前用户目录是否可写；不要发送密钥内容或截图。'
    exit 1
} finally { if ($null -ne $secret) { $secret.Dispose() } }
