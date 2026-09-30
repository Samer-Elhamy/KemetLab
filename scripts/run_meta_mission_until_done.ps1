# Run meta mission until MISSION_COMPLETE.json (local-only experiments ready)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Repo

Remove-Item Env:LOCAL_MOCK_LLM -ErrorAction SilentlyContinue
$env:AUTOSCIENTISTS_TARGET_REPO = "C:\Users\Samer\AutoScientists-Local-Experiments"
$env:META_RUN_DIR = "C:\Users\Samer\meta_qwen_local_0603"
$env:LOCAL_ONLY = "1"
$env:LOCAL_LLM_PROVIDER = "ollama"
$env:META_BENCHMARK_SKIP_OLLAMA = "1"
$env:META_TARGET_SCORE = "80"

$log = "C:\Users\Samer\meta_qwen_local_0603\logs\meta_mission.log"
Write-Host "Mission log: $log"
Write-Host "Will not stop until MISSION_COMPLETE.json exists"

& "$Repo\.venv\Scripts\python.exe" "$Repo\scripts\run_meta_mission_until_done.py" 2>&1 | Tee-Object -FilePath $log
