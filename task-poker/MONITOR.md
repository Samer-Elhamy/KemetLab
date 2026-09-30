# Poker AutoScientists — monitor cheat sheet

## Active run
- Focus root: `C:\Users\Samer\poker_kaggle_0921_0001`
- Task profile: `C:\Users\Samer\AutoScientists-Local\task-poker`
- Competition: `detect-suspicious-value-transfers-in-poker`
- Exec mode: Kaggle cloud only (`AUTOSCIENTISTS_NO_LOCAL_FALLBACK=1`)

## Live kernels (cloud)
```bat
C:\Users\Samer\kaggle\.venv\Scripts\kaggle.exe kernels status samerelhamy/as-exp-6cce270f
C:\Users\Samer\kaggle\.venv\Scripts\kaggle.exe kernels status samerelhamy/poker-quad-apex-v7
C:\Users\Samer\kaggle\.venv\Scripts\kaggle.exe kernels status samerelhamy/poker-baseline-repro-v1
C:\Users\Samer\kaggle\.venv\Scripts\kaggle.exe kernels status samerelhamy/poker-autoscientists-champion-v4
```

## FSM logs
- Cycle 1 (failed old slug): `C:\Users\Samer\AutoScientists-Local\logs\poker_kaggle_0921_0001.log`
- Cycle 2 (CPU Kaggle push, polling): `C:\Users\Samer\AutoScientists-Local\logs\poker_fsm_cpu_cycle2.log`
- Sessions/experiments: `C:\Users\Samer\poker_kaggle_0921_0001\logs\`

## Resume GPU cycles when a slot frees
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\Samer\AutoScientists-Local\scripts\wait_gpu_then_poker_cycles.ps1
```

## Fresh launch (after GPU free)
```powershell
cd C:\Users\Samer\AutoScientists-Local
$env:AUTOSCIENTISTS_EXEC_MODE="kaggle"
$env:AUTOSCIENTISTS_NO_LOCAL_FALLBACK="1"
$env:AUTOSCIENTISTS_COMPETITION="detect-suspicious-value-transfers-in-poker"
$env:AUTOSCIENTISTS_KAGGLE_TIMEOUT="7200"
$env:AUTOSCIENTISTS_KAGGLE_GPU="1"
$env:LOCAL_TEAM_MODE="0"
$env:LOCAL_LLM_PROVIDER="gemini"
.\.venv\Scripts\python.exe launch.py poker_kaggle_NEWRUN --task task-poker --runtime local --run --cycles 2
```

## Cockpit ports
- 8317 EasyCLIProxy / CPA: required for Gemini propose/review — was UP
- 3000 ClawInstitute: NOT required for this path — was DOWN
- No competition submit from this loop (kernels push only)
