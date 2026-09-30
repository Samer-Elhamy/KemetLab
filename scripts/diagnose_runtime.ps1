# Diagnose Ollama + GPU + mock mode for AutoScientists-Local
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot\..

Write-Host ""
Write-Host "=== AutoScientists Runtime Diagnostic ===" -ForegroundColor Cyan
Write-Host ""

if ($env:LOCAL_MOCK_LLM -eq "1") {
    Write-Host "WARNING: LOCAL_MOCK_LLM=1" -ForegroundColor Yellow
    Write-Host "  Qwen/Ollama is DISABLED. Jobs use fake JSON - GPU stays idle for LLM."
    Write-Host ""
} else {
    Write-Host "LOCAL_MOCK_LLM is not set (good for real inference)."
    Write-Host ""
}

Write-Host "--- Ollama service ---" -ForegroundColor Green
try {
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
    Write-Host "OK: Ollama reachable"
    foreach ($m in $tags.models) {
        Write-Host ("  model: " + $m.name)
    }
} catch {
    Write-Host "FAIL: Cannot reach http://127.0.0.1:11434" -ForegroundColor Red
    Write-Host "  Start: ollama serve"
    Write-Host "  Then:  ollama pull qwen3.5-9b-gguf:ud-q4_k_xl"
    Write-Host "         ollama pull qwen3.5:0.8b-gguf"
}

Write-Host ""
Write-Host "--- Models in VRAM (ollama ps) ---" -ForegroundColor Green
if (Get-Command ollama -ErrorAction SilentlyContinue) {
    ollama ps
    Write-Host "Tip: GPU shows under ollama.exe in Task Manager, not always python.exe"
} else {
    Write-Host "ollama CLI not in PATH"
}

Write-Host ""
Write-Host "--- Full health (Python) ---" -ForegroundColor Green
.\.venv\Scripts\python scripts\print_runtime_health.py

Write-Host ""
Write-Host "Done."
