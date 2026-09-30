# One cycle with champion-guided params (works without Ollama / when mock params appear)
param(
    [Parameter(Mandatory = $true)]
    [string]$FocusRoot
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

Remove-Item Env:LOCAL_MOCK_LLM -ErrorAction SilentlyContinue
$env:LOCAL_TEAM_MODE = "0"
$env:LOCAL_PROPOSE_MODE = "hybrid"
$env:LOCAL_LLM_PROVIDER = if ($env:LOCAL_LLM_PROVIDER) { $env:LOCAL_LLM_PROVIDER } else { "openrouter" }

& "$RepoRoot\.venv\Scripts\python" -c @"
from pathlib import Path
from local.dashboard.sync_runtime import sync_runtime_from_repo
sync_runtime_from_repo(Path(r'$FocusRoot'), Path(r'$RepoRoot'))
"@

$env:LOCAL_PEER_REVIEW = "local"

& "$RepoRoot\.venv\Scripts\python" "$RepoRoot\local\orchestrator\runner.py" `
    --focus-root $FocusRoot `
    --max-cycles 1 `
    --cycle-start (Get-Content (Join-Path $FocusRoot "logs\job_status.json") | ConvertFrom-Json).next_cycle
