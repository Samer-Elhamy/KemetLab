# Bootstrap dual-track: production + experiments meta agent
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ExpRepo = "C:\Users\Samer\AutoScientists-Local-Experiments"
$ProdRun = "C:\Users\Samer\dashboard_0602_174304"

Set-Location $Repo

if (-not (Test-Path $ExpRepo)) {
    Write-Host "Creating experiments clone..."
    robocopy $Repo $ExpRepo /E /XD .venv __pycache__ .git /NFL /NDL /NJH /NJS | Out-Null
}

# Sync meta task + docs into experiments
foreach ($rel in @("task-meta-local", "docs\META_LOCAL_RESEARCH.md", "docs\DUAL_TRACK.md")) {
    $src = Join-Path $Repo $rel
    $dst = Join-Path $ExpRepo $rel
    if (Test-Path $src) {
        $dstDir = Split-Path $dst -Parent
        if (-not (Test-Path $dstDir)) { New-Item -ItemType Directory -Path $dstDir -Force | Out-Null }
        Copy-Item $src $dst -Recurse -Force
    }
}

# Marker
@{
    role = "experiments_clone"
    source_repo = $Repo
    created = (Get-Date).ToUniversalTime().ToString("o")
    do_not_edit_production = $true
} | ConvertTo-Json | Set-Content (Join-Path $ExpRepo "EXPERIMENTS.json") -Encoding UTF8

# Venv in experiments (shared packages)
if (-not (Test-Path "$ExpRepo\.venv")) {
    python -m venv "$ExpRepo\.venv"
    & "$ExpRepo\.venv\Scripts\pip" install -q -r "$Repo\requirements.txt"
    & "$ExpRepo\.venv\Scripts\pip" install -q psutil
}

& "$Repo\.venv\Scripts\pip" install -q psutil 2>$null

# Bootstrap meta run
$ts = Get-Date -Format "MMdd_HHmmss"
$MetaRun = "C:\Users\Samer\meta_qwen_local_$ts"
& "$Repo\.venv\Scripts\python" -c @"
from pathlib import Path
from local.launch_local import bootstrap_local_run
repo = Path(r'$Repo')
run = Path(r'$MetaRun')
bootstrap_local_run(repo, run, repo / 'task-meta-local', 'meta_optimization')
# Initial champion = high score until first benchmark
import json
(run / 'champion.json').write_text(json.dumps({
    'val_loss': 9999.0,
    'params': {},
    'direction': 'minimize',
    'note': 'meta resource_score — lower is better'
}, indent=2), encoding='utf-8')
print(run)
"@

$config = @{
    production_repo = $Repo
    experiments_repo = $ExpRepo
    production_run = $ProdRun
    meta_run = $MetaRun
    target_repo_env = $ExpRepo
    meta_target_score = 50
    production_mode = "guided_local_lite"
    started = (Get-Date).ToUniversalTime().ToString("o")
}
$configPath = Join-Path $ProdRun "logs\dual_track.json"
$config | ConvertTo-Json -Depth 4 | Set-Content $configPath -Encoding UTF8

Write-Host ""
Write-Host "=== Dual track ready ===" -ForegroundColor Green
Write-Host "Production run: $ProdRun"
Write-Host "Meta run:       $MetaRun"
Write-Host "Experiments:    $ExpRepo"
Write-Host "Config:         $configPath"
Write-Host ""
Write-Host "Next: .\scripts\start_dual_track_agents.ps1"
