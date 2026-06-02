# AutoScientists local dashboard (Streamlit on http://localhost:8501)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

if (-not (Test-Path .\.venv)) {
    python -m venv .venv
}
.\.venv\Scripts\pip install -q streamlit pandas -r requirements.txt

Write-Host "Dashboard: http://localhost:8501"
.\.venv\Scripts\streamlit run local/dashboard/app.py --server.headless true
