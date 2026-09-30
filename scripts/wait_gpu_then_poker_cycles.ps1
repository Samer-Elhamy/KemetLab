# Wait for a free Kaggle GPU slot, then run AutoScientists poker cycles (cloud only).
$ErrorActionPreference = "Continue"
Set-Location "C:\Users\Samer\AutoScientists-Local"

$env:AUTOSCIENTISTS_EXEC_MODE = "kaggle"
$env:AUTOSCIENTISTS_NO_LOCAL_FALLBACK = "1"
$env:AUTOSCIENTISTS_COMPETITION = "detect-suspicious-value-transfers-in-poker"
$env:AUTOSCIENTISTS_KAGGLE_TIMEOUT = "7200"
$env:AUTOSCIENTISTS_SEED_VAL_LOSS = "0.18"
$env:AUTOSCIENTISTS_KAGGLE_GPU = "1"
$env:LOCAL_TEAM_MODE = "0"
$env:LOCAL_LLM_PROVIDER = "gemini"

$Kaggle = "C:\Users\Samer\kaggle\.venv\Scripts\kaggle.exe"
$LogDir = "C:\Users\Samer\AutoScientists-Local\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = Get-Date -Format "MMdd_HHmm"
$LogFile = Join-Path $LogDir ("poker_gpu_waiter_" + $Stamp + ".log")
$FocusRoot = "C:\Users\Samer\poker_kaggle_0921_0001"
$FsmLog = Join-Path $LogDir ("poker_fsm_resume_" + $Stamp + ".log")

function Write-Log([string]$msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "o"), $msg
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

Write-Log "GPU waiter started. focus=$FocusRoot log=$LogFile"

$watch = @(
    "samerelhamy/poker-quad-apex-v7",
    "samerelhamy/poker-baseline-repro-v1",
    "samerelhamy/poker-autoscientists-champion-v4"
)

while ($true) {
    $running = 0
    foreach ($k in $watch) {
        $out = & $Kaggle kernels status $k 2>&1 | Out-String
        if ($out -match "RUNNING") { $running++ }
        $flat = ($out.Trim() -replace "\s+", " ")
        Write-Log ("status " + $k + ": " + $flat)
    }
    Write-Log ("watched_running=" + $running + " (GPU batch limit typically 2)")

    if ($running -lt 2) {
        Write-Log "GPU slot likely free - launching FSM cycles on existing focus root"
        break
    }
    Start-Sleep -Seconds 45
}

& ".\.venv\Scripts\python.exe" "local\orchestrator\runner.py" --focus-root $FocusRoot --max-cycles 2 --cycle-start 3 *>&1 |
    Tee-Object -FilePath $FsmLog

$code = $LASTEXITCODE
Write-Log ("FSM resume exit=" + $code)
exit $code
