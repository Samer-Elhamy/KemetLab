# Run guided cycles until target %% improvement vs measured baseline
param(
    [string]$FocusRoot = "C:\Users\Samer\dashboard_0602_174304",
    [double]$TargetPct = 85,
    [int]$MaxCycles = 200
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

Remove-Item Env:LOCAL_MOCK_LLM -ErrorAction SilentlyContinue
$env:LOCAL_TEAM_MODE = "0"
$env:LOCAL_PROPOSE_MODE = "guided"
$env:LOCAL_PEER_REVIEW = "local"

$log = Join-Path $FocusRoot "logs\autorun_stdout.log"
Write-Host "Autorun log: $log"
Write-Host "Target: $TargetPct% vs baseline | focus: $FocusRoot"

& "$RepoRoot\.venv\Scripts\python" "$RepoRoot\scripts\run_until_improvement.py" `
    --focus-root $FocusRoot `
    --target-pct $TargetPct `
    --max-cycles $MaxCycles `
    --pause 0.5 `
    2>&1 | Tee-Object -FilePath $log
