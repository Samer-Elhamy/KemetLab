# Launch AutoScientists poker cycles — Kaggle GPU only (no local train)
$ErrorActionPreference = "Stop"
Set-Location "C:\Users\Samer\AutoScientists-Local"

$env:AUTOSCIENTISTS_EXEC_MODE = "kaggle"
$env:AUTOSCIENTISTS_NO_LOCAL_FALLBACK = "1"
$env:AUTOSCIENTISTS_COMPETITION = "detect-suspicious-value-transfers-in-poker"
$env:AUTOSCIENTISTS_KAGGLE_TIMEOUT = "7200"
$env:LOCAL_TEAM_MODE = "0"
$env:LOCAL_LLM_PROVIDER = "gemini"
$env:LOCAL_MOCK_LLM = "0"
Remove-Item Env:LOCAL_MOCK_LLM -ErrorAction SilentlyContinue

$RunName = "poker_kaggle_" + (Get-Date -Format "MMdd_HHmm")
$LogDir = "C:\Users\Samer\AutoScientists-Local\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "$RunName.log"

Write-Host "RunName=$RunName"
Write-Host "Log=$LogFile"
Write-Host "Competition=$env:AUTOSCIENTISTS_COMPETITION"
Write-Host "ExecMode=$env:AUTOSCIENTISTS_EXEC_MODE (no local fallback)"

& ".\.venv\Scripts\python.exe" launch.py $RunName --task task-poker --runtime local --run --cycles 2 *>&1 |
  Tee-Object -FilePath $LogFile

exit $LASTEXITCODE
