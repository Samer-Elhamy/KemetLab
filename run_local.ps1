# Full local pipeline: launch + qwen35custom FSM (no Claude / no ClawInstitute)
param(
    [string]$Name = "run_$(Get-Date -Format 'MMdd_HHmm')",
    [string]$Task = "task-smoke-local",
    [int]$Cycles = 1,
    [switch]$Mock
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($Mock) { $env:LOCAL_MOCK_LLM = "1" }

.\.venv\Scripts\python launch.py $Name --task $Task --run --cycles $Cycles
