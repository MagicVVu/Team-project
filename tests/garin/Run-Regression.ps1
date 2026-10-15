param(
    [string]$ProjectRoot = 'D:\Team_Project\Team-project',
    [string]$PythonExe = 'python'
)
$ErrorActionPreference = 'Stop'
$GarinRoot = $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
Push-Location -LiteralPath $GarinRoot
try {
    & $PythonExe -m venv (Join-Path $GarinRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw '创建测试虚拟环境失败' }
    $GarinPython = Join-Path $GarinRoot '.venv\Scripts\python.exe'
    & $GarinPython -m pip install -r (Join-Path $ProjectRoot 'agent\requirements.lock.txt') tzdata
    if ($LASTEXITCODE -ne 0) { throw '测试依赖安装失败' }
    # Source is read-only. All cache/test writes occur in this isolated copy.
    & $GarinPython (Join-Path $GarinRoot 'prepare.py') --source $ProjectRoot
    if ($LASTEXITCODE -ne 0) { throw '复制测试源码失败' }
    & $GarinPython (Join-Path $GarinRoot 'run_all.py')
    $GarinExit = $LASTEXITCODE
    Write-Host ('测试结束，退出码 ' + $GarinExit + '；逐项证据在本目录 runs 下。1 表示失败或未覆盖，不是通过。')
    exit $GarinExit
} finally {
    Pop-Location
}
