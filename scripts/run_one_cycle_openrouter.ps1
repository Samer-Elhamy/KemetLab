# One FSM cycle via OpenRouter (no local GPU / Ollama required)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Remove-Item Env:LOCAL_MOCK_LLM -ErrorAction SilentlyContinue
$env:LOCAL_LLM_PROVIDER = "openrouter"
$env:LOCAL_TEAM_MODE = "0"
$env:OPENROUTER_MODEL_HEAVY = "qwen/qwen3-coder:free"
$env:OPENROUTER_MODEL_LIGHT = "qwen/qwen3-coder:free"

if (-not $env:OPENROUTER_API_KEY) {
    $hermes = Join-Path $env:USERPROFILE ".hermes\.env"
    if (Test-Path $hermes) {
        Get-Content $hermes | ForEach-Object {
            if ($_ -match '^\s*OPENROUTER_API_KEY=(.+)$') {
                $env:OPENROUTER_API_KEY = $Matches[1].Trim()
            }
        }
    }
}

if (-not $env:OPENROUTER_API_KEY) {
    Write-Host "Set OPENROUTER_API_KEY or add to ~/.hermes/.env" -ForegroundColor Red
    exit 1
}

$RunRoot = $args[0]
if (-not $RunRoot) {
    $candidates = Get-ChildItem (Join-Path $env:USERPROFILE "dashboard_*") -Directory -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($candidates) { $RunRoot = $candidates.FullName }
}
if (-not $RunRoot -or -not (Test-Path $RunRoot)) {
    Write-Host "Creating new smoke mission..."
    $RunRoot = .\.venv\Scripts\python -c "
from pathlib import Path
from local.dashboard.executor import create_dashboard_run
from local.dashboard.repo_root import find_repo_root
r = find_repo_root(Path('.'))
d = create_dashboard_run('OpenRouter smoke cycle', template_dir=r)
print(d)
".Trim()
    $RunRoot = ($RunRoot | Out-String).Trim()
}

Write-Host "Focus root: $RunRoot"
Write-Host "Provider: OpenRouter | Team mode: off"

.\.venv\Scripts\python local\orchestrator\runner.py --focus-root $RunRoot --max-cycles 1
$code = $LASTEXITCODE
Write-Host "Exit: $code"
if ($code -eq 0) {
    Write-Host "Check logs/experiments.jsonl and logs/cycle_monitor.json"
}
exit $code
