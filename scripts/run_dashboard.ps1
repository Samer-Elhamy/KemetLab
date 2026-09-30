# AutoScientists local dashboard (Streamlit on http://localhost:8501)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not (Test-Path .\.venv)) {
    python -m venv .venv
}
.\.venv\Scripts\pip install -q streamlit pandas -r requirements.txt

# Fresh Python modules (avoids stale repair_stale_job ImportError)
Get-ChildItem -Path local -Recurse -Filter __pycache__ -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
$env:PYTHONDONTWRITEBYTECODE = "1"

# Real runs: ensure MOCK is off (remove user/system env if set)
Remove-Item Env:LOCAL_MOCK_LLM -ErrorAction SilentlyContinue
# Dashboard reads runs only — do not force cloud LLM (experiments use LOCAL_ONLY)
if (-not $env:LOCAL_LLM_PROVIDER) { $env:LOCAL_LLM_PROVIDER = "ollama" }
# Avoid stale mock params (0.01/32/50); local peer review skips OpenRouter 429 delays
if (-not $env:LOCAL_PROPOSE_MODE) { $env:LOCAL_PROPOSE_MODE = "hybrid" }
if (-not $env:LOCAL_PEER_REVIEW) { $env:LOCAL_PEER_REVIEW = "local" }

# Optional: fast test without Ollama (uncomment next line only for tests)
# $env:LOCAL_MOCK_LLM = "1"
if ($env:LOCAL_MOCK_LLM -eq "1") {
    Write-Host "WARNING: LOCAL_MOCK_LLM=1 — Ollama/qwen disabled (no GPU for LLM)" -ForegroundColor Yellow
}

Write-Host "Dashboard: http://localhost:8501"
Write-Host "Background (persists): .\scripts\start_dashboard.ps1"
Write-Host "GPU check: .\scripts\diagnose_runtime.ps1"
$env:PYTHONPATH = (Get-Location).Path
if ($args -contains "-Background") {
    & "$PSScriptRoot\start_dashboard.ps1"
} else {
    .\.venv\Scripts\streamlit run local/dashboard/app.py --server.headless true
}
