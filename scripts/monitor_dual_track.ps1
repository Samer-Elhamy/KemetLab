# Monitor dual-track agent progress (production + meta experiments)
param([int]$Tail = 5)

$configPath = "C:\Users\Samer\dashboard_0602_174304\logs\dual_track.json"
if (-not (Test-Path $configPath)) {
    Write-Host "Run bootstrap_dual_track.ps1 first" -ForegroundColor Yellow
    exit 1
}
$cfg = Get-Content $configPath | ConvertFrom-Json

Write-Host "`n=== Dual Track Monitor ===" -ForegroundColor Cyan
Write-Host "Production run: $($cfg.production_run)"
Write-Host "Meta run:       $($cfg.meta_run)"
Write-Host "Experiments:    $($cfg.experiments_repo)"

# Production champion
& "$($cfg.production_repo)\.venv\Scripts\python.exe" -c @"
from pathlib import Path
from local.dashboard.cycle_metrics import load_baseline, _pct_improve
from local.orchestrator import promotion
from local.dashboard.job_status import read_job_status
rd = Path(r'$($cfg.production_run)')
b = float(load_baseline(rd)['val_loss'])
c = float(promotion.load_champion_json(rd)['val_loss'])
imp = _pct_improve(b, c, 'minimize')
st = read_job_status(rd)
print(f'Production: champion={c:.6f} improve={imp:.2f}% state={st.get(\"state\")} cycle={st.get(\"current_cycle\",\"?\")}')
"@

# Meta champion
& "$($cfg.production_repo)\.venv\Scripts\python.exe" -c @"
from pathlib import Path
from local.orchestrator import promotion
from local.dashboard.job_status import read_job_status
import json
rd = Path(r'$($cfg.meta_run)')
if (rd / 'champion.json').exists():
    c = promotion.load_champion_json(rd)
    ex = rd / 'logs' / 'experiments.jsonl'
    n = sum(1 for _ in open(ex, encoding='utf-8') if _.strip()) if ex.exists() else 0
    print(f'Meta: resource_score={c.get(\"val_loss\")} experiments={n}')
else:
    print('Meta: not bootstrapped')
"@

Write-Host "`nRecent meta experiments:" -ForegroundColor Yellow
$metaEx = Join-Path $cfg.meta_run "logs\experiments.jsonl"
if (Test-Path $metaEx) { Get-Content $metaEx -Tail $Tail }

Write-Host "`nPython agents:" -ForegroundColor Yellow
Get-Process python -ErrorAction SilentlyContinue | Select-Object Id, CPU, StartTime | Format-Table

Write-Host "Logs:"
Write-Host "  $($cfg.production_run)\logs\production_autorun.log"
Write-Host "  $($cfg.meta_run)\logs\meta_agent.log"
