$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$qaRoot = (Get-Location).Path
$qaProcess = Get-CimInstance Win32_Process | Where-Object {
    $_.ExecutablePath -eq "$qaRoot\.venv\Scripts\python.exe" -and $_.CommandLine -match 'run\.py'
}
foreach ($qaParent in $qaProcess) {
    $qaChildren = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $qaParent.ProcessId -and $_.CommandLine -match 'run\.py' }
    foreach ($qaChild in $qaChildren) { Stop-Process -Id $qaChild.ProcessId -ErrorAction SilentlyContinue }
    Stop-Process -Id $qaParent.ProcessId -ErrorAction SilentlyContinue
}
$qaStarted = Start-Process -FilePath '.venv/Scripts/python.exe' -ArgumentList 'run.py' -WorkingDirectory $qaRoot -WindowStyle Hidden -RedirectStandardOutput 'data/server.stdout.log' -RedirectStandardError 'data/server.stderr.log' -PassThru
$qaStarted.Id | Set-Content -LiteralPath 'data/server.pid'
Write-Output "Local QA server launcher: $($qaStarted.Id)"
& ./.venv/Scripts/python.exe -m scripts.wait_ready
if ($LASTEXITCODE -ne 0) { throw 'The local server did not pass readiness. See the diagnostics above.' }
