$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendPath = Join-Path $ProjectRoot "backend"

Set-Location $BackendPath

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

$Python = Join-Path $BackendPath ".venv\Scripts\python.exe"

& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt

& $Python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000