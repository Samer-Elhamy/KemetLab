# Start dashboard in background (persists after closing terminal)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Repo

if (-not (Test-Path .\.venv)) {
    python -m venv .venv
    .\.venv\Scripts\pip install -q -r requirements.txt streamlit pandas
}

$logOut = Join-Path $Repo "logs\dashboard_stdout.log"
$logErr = Join-Path $Repo "logs\dashboard_stderr.log"
New-Item -ItemType Directory -Path (Join-Path $Repo "logs") -Force | Out-Null

Get-Process streamlit -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'streamlit run local/dashboard/app.py' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Remove-Item Env:LOCAL_MOCK_LLM -ErrorAction SilentlyContinue
$env:PYTHONPATH = $Repo
$env:PYTHONDONTWRITEBYTECODE = "1"

$py = Join-Path $Repo ".venv\Scripts\python.exe"
Start-Process -FilePath $py `
    -ArgumentList "-m", "streamlit", "run", "local/dashboard/app.py", "--server.headless", "true", "--server.port", "8501", "--server.address", "localhost" `
    -WorkingDirectory $Repo `
    -RedirectStandardOutput $logOut `
    -RedirectStandardError $logErr `
    -WindowStyle Hidden

Start-Sleep -Seconds 5
try {
    $r = Invoke-WebRequest -Uri "http://localhost:8501/_stcore/health" -UseBasicParsing -TimeoutSec 10
    Write-Host "Dashboard OK: http://localhost:8501 (health $($r.StatusCode))" -ForegroundColor Green
} catch {
    Write-Host "Dashboard may still be starting - check $logErr" -ForegroundColor Yellow
}
Write-Host "Logs: $logOut"
