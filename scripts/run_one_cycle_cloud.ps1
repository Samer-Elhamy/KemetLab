# One FSM cycle via cloud LLM (OpenRouter -> Gemini fallback), no Ollama
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Remove-Item Env:LOCAL_MOCK_LLM -ErrorAction SilentlyContinue
$env:LOCAL_TEAM_MODE = "0"
$env:LOCAL_LLM_PROVIDER = "openrouter"
$env:OPENROUTER_MODEL_HEAVY = "meta-llama/llama-3.3-70b-instruct:free"
$env:OPENROUTER_MODEL_LIGHT = "meta-llama/llama-3.3-70b-instruct:free"

$hermes = Join-Path $env:USERPROFILE ".hermes\.env"
if (Test-Path $hermes) {
    Get-Content $hermes | ForEach-Object {
        if ($_ -match '^\s*(OPENROUTER_API_KEY|GOOGLE_API_KEY)=(.+)$') {
            Set-Item -Path "Env:$($Matches[1])" -Value $Matches[2].Trim()
        }
    }
}

$RunRoot = $args[0]
if (-not $RunRoot) {
    $latest = Get-ChildItem (Join-Path $env:USERPROFILE "dashboard_*") -Directory -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latest) { $RunRoot = $latest.FullName }
}
if (-not $RunRoot) {
    $out = .\.venv\Scripts\python -c "from pathlib import Path; from local.dashboard.executor import create_dashboard_run; from local.dashboard.repo_root import find_repo_root; print(create_dashboard_run('cloud cycle', template_dir=find_repo_root(Path('.'))))"
    $RunRoot = ($out | Out-String).Trim()
}

Write-Host "Run: $RunRoot"
.\.venv\Scripts\python local\orchestrator\runner.py --focus-root $RunRoot --max-cycles 1
exit $LASTEXITCODE
