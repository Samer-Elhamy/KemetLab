# Run local smoke test end-to-end (mock LLM)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$RunName = "smoke_" + (Get-Date -Format "MMdd_HHmm")
$env:LOCAL_MOCK_LLM = "1"

python launch.py $RunName --task task-smoke-local --runtime local
$RunDir = Join-Path (Split-Path $Root -Parent) $RunName
if (-not (Test-Path $RunDir)) {
    $RunDir = Join-Path $Root ".." $RunName
}
python local/orchestrator/runner.py --focus-root $RunDir --max-cycles 1
Write-Host "Done. Run dir: $RunDir"
