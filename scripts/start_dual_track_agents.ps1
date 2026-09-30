# Start production (guided smoke) + meta agent (Qwen dual-tier on experiments repo)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$configPath = "C:\Users\Samer\dashboard_0602_174304\logs\dual_track.json"

if (-not (Test-Path $configPath)) {
    & "$Repo\scripts\bootstrap_dual_track.ps1"
    $configPath = "C:\Users\Samer\dashboard_0602_174304\logs\dual_track.json"
}

$cfg = Get-Content $configPath | ConvertFrom-Json
$ProdRun = $cfg.production_run
$MetaRun = $cfg.meta_run
$ExpRepo = $cfg.experiments_repo

Remove-Item Env:LOCAL_MOCK_LLM -ErrorAction SilentlyContinue

# --- Track A: production smoke (no OpenRouter, no team mode) ---
$prodLog = Join-Path $ProdRun "logs\production_autorun.log"
Remove-Item Env:LOCAL_PEER_REVIEW -ErrorAction SilentlyContinue
$env:LOCAL_TEAM_MODE = "0"
$env:LOCAL_PROPOSE_MODE = "guided"
$env:LOCAL_PEER_REVIEW = "local"

Start-Process -FilePath "$Repo\.venv\Scripts\python.exe" `
    -ArgumentList "$Repo\scripts\run_production_track.py" `
    -WorkingDirectory $Repo `
    -RedirectStandardOutput $prodLog `
    -RedirectStandardError (Join-Path $ProdRun "logs\production_autorun_err.log") `
    -WindowStyle Hidden

Write-Host "Track A (production smoke): started -> $prodLog"

# --- Track B: meta agent on experiments repo (Qwen heavy + light via Ollama) ---
$metaLog = Join-Path $MetaRun "logs\meta_agent.log"
$env:AUTOSCIENTISTS_TARGET_REPO = $ExpRepo
$env:LOCAL_LLM_PROVIDER = "ollama"
$env:LOCAL_PROPOSE_MODE = "llm"
Remove-Item Env:LOCAL_PEER_REVIEW -ErrorAction SilentlyContinue
$env:LOCAL_OLLAMA_HEAVY = if ($env:LOCAL_OLLAMA_HEAVY) { $env:LOCAL_OLLAMA_HEAVY } else { "qwen3.5:0.8b" }
$env:LOCAL_OLLAMA_LIGHT = if ($env:LOCAL_OLLAMA_LIGHT) { $env:LOCAL_OLLAMA_LIGHT } else { "qwen3.5:0.8b" }
$env:LOCAL_OLLAMA_NUM_CTX = "2048"
$env:META_BENCHMARK_SKIP_OLLAMA = if ($env:SKIP_OLLAMA_BENCH) { "1" } else { "1" }
$env:META_GUIDED_ON_LLM_FAIL = "1"

Start-Process -FilePath "$Repo\.venv\Scripts\python.exe" `
    -ArgumentList "$Repo\local\orchestrator\meta_runner.py","--focus-root",$MetaRun,"--max-cycles","0","--target-score","50","--pause","10" `
    -WorkingDirectory $Repo `
    -RedirectStandardOutput $metaLog `
    -RedirectStandardError (Join-Path $MetaRun "logs\meta_agent_err.log") `
    -WindowStyle Hidden

Write-Host "Track B (meta / Qwen): started -> $metaLog"
Write-Host "AUTOSCIENTISTS_TARGET_REPO=$ExpRepo"
Write-Host "Monitor: .\scripts\monitor_dual_track.ps1"
