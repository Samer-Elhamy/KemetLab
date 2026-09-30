# Verify experiments clone runs fully local (3 guided FSM cycles)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ExpRepo = "C:\Users\Samer\AutoScientists-Local-Experiments"
$RunDir = "C:\Users\Samer\experiments_verify_0603"
Set-Location $Repo

if (-not (Test-Path (Join-Path $ExpRepo "MISSION_COMPLETE.json"))) {
    Write-Host "WARNING: MISSION_COMPLETE.json missing - run meta mission first" -ForegroundColor Yellow
}

Get-Content (Join-Path $ExpRepo "local\config\local_only.env") | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.+)$') {
        Set-Item -Path ("Env:" + $matches[1].Trim()) -Value $matches[2].Trim()
    }
}
Remove-Item Env:LOCAL_MOCK_LLM -ErrorAction SilentlyContinue
Remove-Item Env:OPENROUTER_API_KEY -ErrorAction SilentlyContinue
$env:PYTHONPATH = $ExpRepo + ";" + $Repo

if (-not (Test-Path $RunDir)) {
    & (Join-Path $Repo ".venv\Scripts\python.exe") (Join-Path $Repo "scripts\bootstrap_experiments_verify_run.py")
}

$logDir = Join-Path $RunDir "logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$log = Join-Path $logDir "verify_mission.log"
Write-Host "Run dir: $RunDir"
Write-Host "Log: $log"

$py = Join-Path $Repo ".venv\Scripts\python.exe"
$script = Join-Path $Repo "scripts\run_experiments_verify_mission.py"
& $py $script --focus-root $RunDir --cycles 3 2>&1 | Tee-Object -FilePath $log

Write-Host ""
Write-Host "Open dashboard: http://localhost:8501 (tab Now)" -ForegroundColor Cyan
