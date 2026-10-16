param([string]$SshHost = 'magicvvu')
$ErrorActionPreference = 'Stop'
# Bind only to this computer. Emulator connects through 10.0.2.2.
$listeners = Get-NetTCPConnection -State Listen -LocalPort 18080,18081 -ErrorAction SilentlyContinue
if ($listeners) {
    Write-Output 'Port 18080 or 18081 is already in use. Check the existing tunnel before starting another.'
    exit 1
}
$sshArgs = @('-N','-o','BatchMode=yes','-o','ExitOnForwardFailure=yes','-o','ServerAliveInterval=30','-o','ServerAliveCountMax=3',
    '-L','127.0.0.1:18080:127.0.0.1:8000','-L','127.0.0.1:18081:127.0.0.1:18081',$SshHost)
$process = Start-Process -FilePath ssh.exe -ArgumentList $sshArgs -WindowStyle Hidden -PassThru
$pidFolder = Join-Path $PSScriptRoot '../.gradle'
New-Item -ItemType Directory -Path $pidFolder -Force | Out-Null
[IO.File]::WriteAllText((Join-Path $pidFolder 'cloud-tunnel.pid'), [string]$process.Id)
Write-Output "SSH tunnel started (PID $($process.Id)). App address: http://10.0.2.2:18080"
Write-Output 'Stop it with Stop-Process -Id <PID> when no longer needed.'
