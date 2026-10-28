# Explicit local credential launcher. No key is passed on the command line.
[CmdletBinding()]
param(
    [switch]$Configure,
    [ValidateSet('Check', 'Smoke')]
    [string]$Action = 'Check',
    [switch]$KeepOpen,
    [switch]$SelfTest
)

$ErrorActionPreference = 'Stop'
$jevAgentRoot = Split-Path -Parent $PSScriptRoot
$jevPrivateDir = Join-Path $PSScriptRoot '.cache\credentials'
$jevKeyFile = Join-Path $jevPrivateDir 'typesafe-api-key.dpapi'
$jevSetupDir = Join-Path $PSScriptRoot '.cache\setup'
$jevStateFile = Join-Path $jevSetupDir 'state.json'
$jevSecureKey = $null
$jevKeyPointer = [IntPtr]::Zero
$jevPlainKey = $null
$jevExitCode = 1
$jevPhase = 'initializing'
$jevPreviousKey = [Environment]::GetEnvironmentVariable('TYPESAFE_API_KEY', 'Process')
$jevPreviousUtf8 = [Environment]::GetEnvironmentVariable('PYTHONUTF8', 'Process')

function Write-JevState([string]$Phase, [bool]$Success, [string]$ErrorCode = '', [string]$ErrorType = '') {
    $jevState = @{
        phase = $Phase
        success = $Success
        error_code = $ErrorCode
        error_type = $ErrorType
        process_id = $PID
        updated_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
        credential_storage = 'Windows DPAPI CurrentUser; encrypted; explicit launcher only'
        business_integration = $false
    }
    $jevState | ConvertTo-Json | Set-Content -LiteralPath $jevStateFile -Encoding UTF8
}

function Read-JevKey {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $jevForm = New-Object System.Windows.Forms.Form
    $jevForm.Text = 'Mewstow Jev - API key (local only)'
    $jevForm.ClientSize = New-Object System.Drawing.Size(560, 170)
    $jevForm.StartPosition = 'CenterScreen'
    $jevForm.FormBorderStyle = 'FixedDialog'
    $jevForm.MaximizeBox = $false
    $jevForm.MinimizeBox = $false
    $jevForm.TopMost = $true
    $jevLabel = New-Object System.Windows.Forms.Label
    $jevLabel.Text = "Paste your TypeSafe API key below (Ctrl+V). Input is hidden.`r`nSaved using Windows user-bound encryption. Synthetic test only; USD 1 budget."
    $jevLabel.Location = New-Object System.Drawing.Point(16, 14)
    $jevLabel.Size = New-Object System.Drawing.Size(530, 44)
    $jevText = New-Object System.Windows.Forms.TextBox
    $jevText.Location = New-Object System.Drawing.Point(16, 66)
    $jevText.Size = New-Object System.Drawing.Size(528, 28)
    $jevText.UseSystemPasswordChar = $true
    $jevText.MaxLength = 4096
    $jevAccept = New-Object System.Windows.Forms.Button
    $jevAccept.Text = 'Save and continue'
    $jevAccept.Location = New-Object System.Drawing.Point(298, 118)
    $jevAccept.Size = New-Object System.Drawing.Size(140, 30)
    $jevAccept.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $jevCancel = New-Object System.Windows.Forms.Button
    $jevCancel.Text = 'Cancel'
    $jevCancel.Location = New-Object System.Drawing.Point(448, 118)
    $jevCancel.Size = New-Object System.Drawing.Size(96, 30)
    $jevCancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $jevForm.Controls.AddRange(@($jevLabel, $jevText, $jevAccept, $jevCancel))
    $jevForm.AcceptButton = $jevAccept
    $jevForm.CancelButton = $jevCancel
    $jevForm.Add_Shown({ [void]$jevText.Focus() })
    try {
        if ($jevForm.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { throw 'INPUT_CANCELLED' }
        $jevInputSecure = New-Object System.Security.SecureString
        foreach ($jevCharacter in $jevText.Text.ToCharArray()) { $jevInputSecure.AppendChar($jevCharacter) }
        $jevInputSecure.MakeReadOnly()
        return $jevInputSecure
    } finally {
        $jevText.Clear()
        $jevForm.Dispose()
    }
}

function Protect-JevKey([Security.SecureString]$Secret) {
    Add-Type -AssemblyName System.Security
    $jevProtectPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Secret)
    $jevProtectBytes = $null
    try {
        $jevProtectText = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($jevProtectPointer).Trim()
        $jevProtectBytes = [Text.Encoding]::UTF8.GetBytes($jevProtectText)
        $jevProtectedBytes = [Security.Cryptography.ProtectedData]::Protect(
            $jevProtectBytes, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)
        return 'JEV-DPAPI-1:' + [Convert]::ToBase64String($jevProtectedBytes)
    } finally {
        $jevProtectText = $null
        if ($null -ne $jevProtectBytes) { [Array]::Clear($jevProtectBytes, 0, $jevProtectBytes.Length) }
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($jevProtectPointer)
    }
}

function Unprotect-JevKey([string]$Ciphertext) {
    Add-Type -AssemblyName System.Security
    if (-not $Ciphertext.StartsWith('JEV-DPAPI-1:')) { throw 'INVALID_LOCAL_KEY_FILE' }
    $jevUnprotectedBytes = $null
    try {
        $jevEncryptedBytes = [Convert]::FromBase64String($Ciphertext.Substring(12))
        $jevUnprotectedBytes = [Security.Cryptography.ProtectedData]::Unprotect(
            $jevEncryptedBytes, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)
        $jevUnprotectedText = [Text.Encoding]::UTF8.GetString($jevUnprotectedBytes)
        $jevLoadedSecure = New-Object Security.SecureString
        foreach ($jevCharacter in $jevUnprotectedText.ToCharArray()) { $jevLoadedSecure.AppendChar($jevCharacter) }
        $jevLoadedSecure.MakeReadOnly()
        return $jevLoadedSecure
    } finally {
        $jevUnprotectedText = $null
        if ($null -ne $jevUnprotectedBytes) { [Array]::Clear($jevUnprotectedBytes, 0, $jevUnprotectedBytes.Length) }
    }
}

if ($SelfTest) {
    $jevFake = New-Object Security.SecureString
    $jevRestored = $null
    $jevSelfTestPointer = [IntPtr]::Zero
    $jevSelfTestFile = Join-Path $jevSetupDir ('self-test-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    try {
        foreach ($jevCharacter in 'sk_synthetic-local-check-only'.ToCharArray()) { $jevFake.AppendChar($jevCharacter) }
        $jevFake.MakeReadOnly()
        [IO.Directory]::CreateDirectory($jevSetupDir) | Out-Null
        $jevSelfTestCipher = Protect-JevKey $jevFake
        [IO.File]::WriteAllText($jevSelfTestFile, $jevSelfTestCipher, [Text.Encoding]::ASCII)
        $jevRestored = Unprotect-JevKey ([IO.File]::ReadAllText($jevSelfTestFile))
        $jevSelfTestPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($jevRestored)
        $jevSelfTestText = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($jevSelfTestPointer)
        if ($jevSelfTestText -cne 'sk_synthetic-local-check-only' -or $jevSelfTestText -cmatch '[\s\x00-\x20\x7f-\uffff]') { throw 'SELF_TEST_MISMATCH' }
        Write-Output 'DPAPI save/load and ASCII key validation self-test passed; no network request.'
    } finally {
        $jevSelfTestText = $null
        if ($jevSelfTestPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($jevSelfTestPointer) }
        $jevFake.Dispose()
        if ($null -ne $jevRestored) { $jevRestored.Dispose() }
        if ([IO.File]::Exists($jevSelfTestFile)) { [IO.File]::Delete($jevSelfTestFile) }
    }
    exit 0
}

try {
    if ($env:OS -ne 'Windows_NT') { throw 'WINDOWS_REQUIRED' }
    New-Item -ItemType Directory -Path $jevSetupDir -Force | Out-Null
    $Host.UI.RawUI.WindowTitle = 'Mewstow Jev - secure local key setup'
    Write-Host 'Mewstow Jev: local synthetic tests only. Cumulative budget: USD 1.'
    Write-Host 'The API key is hidden and never sent to chat or saved as plaintext.'
    if ($Configure) {
        $jevPhase = 'waiting_for_input'
        Write-JevState $jevPhase $false
        $jevSecureKey = Read-JevKey
        if ($jevSecureKey.Length -eq 0) { throw 'EMPTY_KEY' }
    } else {
        $jevPhase = 'loading_local_key'
        if (-not (Test-Path -LiteralPath $jevKeyFile)) { throw 'LOCAL_KEY_NOT_CONFIGURED' }
        $jevSecureKey = Unprotect-JevKey ([IO.File]::ReadAllText($jevKeyFile))
    }
    $jevKeyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($jevSecureKey)
    $jevPlainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($jevKeyPointer).Trim()
    # -cmatch is essential: Unicode case folding of long-s/Kelvin can otherwise
    # make the non-ASCII range match ordinary ASCII 's'/'k' in valid API keys.
    if ([string]::IsNullOrWhiteSpace($jevPlainKey) -or $jevPlainKey -cmatch '[\s\x00-\x20\x7f-\uffff]') { throw 'INVALID_KEY_FORMAT' }
    [Environment]::SetEnvironmentVariable('TYPESAFE_API_KEY', $jevPlainKey, 'Process')
    [Environment]::SetEnvironmentVariable('PYTHONUTF8', '1', 'Process')
    $jevPlainKey = $null
    if ($Configure) {
        $jevPhase = 'saving_encrypted_key'
        New-Item -ItemType Directory -Path $jevPrivateDir -Force | Out-Null
        $jevCiphertext = Protect-JevKey $jevSecureKey
        $jevTempKey = Join-Path $jevPrivateDir ([Guid]::NewGuid().ToString('N') + '.tmp')
        [IO.File]::WriteAllText($jevTempKey, $jevCiphertext, [Text.Encoding]::ASCII)
        Move-Item -LiteralPath $jevTempKey -Destination $jevKeyFile -Force
        $jevCiphertext = $null
    }
    $jevPython = 'D:\python\python3.13.5\python.exe'
    if (-not (Test-Path -LiteralPath $jevPython)) { throw 'EXISTING_PYTHON_NOT_FOUND' }
    Push-Location -LiteralPath $jevAgentRoot
    try {
        $jevPhase = 'checking_configuration'
        Write-JevState $jevPhase $false
        $jevCheck = & $jevPython -m jev check
        if ($LASTEXITCODE -ne 0) { throw 'LOCAL_CHECK_FAILED' }
        $jevCheck | Set-Content -LiteralPath (Join-Path $jevSetupDir 'check.json') -Encoding UTF8
        Write-Host 'Local key is configured. Encrypted storage is bound to this Windows account.'
        if ($Action -eq 'Smoke') {
            $jevPhase = 'running_synthetic_smoke'
            Write-JevState $jevPhase $false
            Write-Host 'Running one synthetic scenario (at most two Jev requests). No automatic retry.'
            $jevSmoke = & $jevPython -m jev decide --provider live --input jev/datasets/example.json
            $jevSmokeExit = $LASTEXITCODE
            $jevSmoke | Set-Content -LiteralPath (Join-Path $jevSetupDir 'live-smoke.json') -Encoding UTF8
            if ($jevSmokeExit -ne 0) {
                $jevPhase = 'smoke_failed'
                Write-JevState $jevPhase $false 'LIVE_SMOKE_FAILED'
                Write-Host 'The key was saved, but the live smoke did not complete. Only sanitized status was saved.'
            } else {
                $jevExitCode = 0
                Write-JevState 'completed' $true
                Write-Host 'Synthetic smoke completed. Sanitized result saved; key was not logged.'
            }
        } else {
            $jevExitCode = 0
            Write-JevState 'completed_check_only' $true
            Write-Host 'Check completed. No model request was sent.'
        }
    } finally {
        Pop-Location
    }
} catch {
    # Do not emit exception records, inputs, environment values or command output.
    $jevErrorCode = 'SETUP_FAILED_AT_' + $jevPhase
    if ($_.Exception.Message -in @('WINDOWS_REQUIRED','EMPTY_KEY','INVALID_KEY_FORMAT','LOCAL_KEY_NOT_CONFIGURED','INVALID_LOCAL_KEY_FILE','EXISTING_PYTHON_NOT_FOUND','LOCAL_CHECK_FAILED','INPUT_CANCELLED')) {
        $jevErrorCode = $_.Exception.Message
    }
    if (Test-Path -LiteralPath $jevSetupDir) { Write-JevState 'setup_failed' $false $jevErrorCode ($_.Exception.GetType().FullName) }
    Write-Host ('Setup stopped: ' + $jevErrorCode + '. No secret was printed.')
} finally {
    [Environment]::SetEnvironmentVariable('TYPESAFE_API_KEY', $jevPreviousKey, 'Process')
    [Environment]::SetEnvironmentVariable('PYTHONUTF8', $jevPreviousUtf8, 'Process')
    if ($jevKeyPointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($jevKeyPointer) }
    if ($null -ne $jevSecureKey) { $jevSecureKey.Dispose() }
    $jevPreviousKey = $null
    $jevPlainKey = $null
    if ($KeepOpen) { $jevCloseInput = Read-Host 'Press Enter to close this window' -AsSecureString; $jevCloseInput.Dispose() }
}
exit $jevExitCode
