# Dual-track bootstrap: production smoke + meta experiments (Qwen heavy/light)

Production codebase: `C:\Users\Samer\AutoScientists-Local`
Experiments codebase: `C:\Users\Samer\AutoScientists-Local-Experiments`
Production run (keep improving): `C:\Users\Samer\dashboard_0602_174304`

## What this script does (Cursor setup only — agents do the work)

1. Syncs new meta task files into experiments clone
2. Creates meta run directory `meta_qwen_local_*`
3. Writes track config JSON for monitoring
4. Does **not** replace production code

```powershell
.\scripts\bootstrap_dual_track.ps1
.\scripts\start_dual_track_agents.ps1   # starts agent jobs in background
.\scripts\monitor_dual_track.ps1        # watch progress
```
