# ⚗️ KemetLab One-Click Team Setup Script for PowerShell
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "         KemetLab - Automated Team Setup Engine" -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check Python
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "[ERROR] Python is not found in PATH! Please install Python 3.10+ from python.org" -ForegroundColor Red
    exit 1
}

$pyVer = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Write-Host "[*] Detected Python version: $pyVer" -ForegroundColor Green

# 2. Create or verify .venv
if (-not (Test-Path ".venv")) {
    Write-Host "[*] Creating isolated virtual environment (.venv)..." -ForegroundColor Cyan
    python -m venv .venv
} else {
    Write-Host "[OK] Virtual environment (.venv) already exists." -ForegroundColor Green
}

# 3. Activate .venv
Write-Host "[*] Activating virtual environment..." -ForegroundColor Cyan
& ".\.venv\Scripts\Activate.ps1"

# 4. Install dependencies
Write-Host "[*] Installing & upgrading dependencies from requirements.txt..." -ForegroundColor Cyan
python -m pip install --upgrade pip
if (Test-Path "requirements.txt") {
    pip install -r requirements.txt
}

# 5. Run sanity check
Write-Host "[*] Running sanity tests..." -ForegroundColor Cyan
python -m unittest tests/test_local_runtime.py

# 6. Verify Native Embedded EasyCLI / Antigravity Gateway
Write-Host "[*] Checking Native Antigravity / CPA Engine..." -ForegroundColor Cyan
python -c "from local.cpa.cpa_service import get_cpa_status; st = get_cpa_status(); print('Native CPA Online:', st['online'], '| Binary present:', st['binary_present'])"

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host "   SUCCESS: KemetLab is fully configured and ready!" -ForegroundColor Green
    Write-Host "   - To launch Cockpit GUI: run Start_KemetLab_Cockpit.bat" -ForegroundColor Yellow
    Write-Host "   - To manage Antigravity accounts: use Cockpit GUI or Streamlit" -ForegroundColor Yellow
    Write-Host "   - Run a smoke test: python launch.py my_run --task task-smoke-local --run" -ForegroundColor Yellow
    Write-Host "==========================================================" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "[WARNING] Setup completed, but some unit tests reported issues. Please check dependencies." -ForegroundColor Yellow
}
