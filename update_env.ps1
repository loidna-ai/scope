# update_env.ps1
$ErrorActionPreference = "Stop"

Write-Host "Checking virtual environment..." -ForegroundColor Cyan
if (-not (Test-Path venv)) {
    Write-Host "Creating venv..." -ForegroundColor Yellow
    python -m venv venv
}

Write-Host "Upgrading pip..." -ForegroundColor Cyan
.\venv\Scripts\python.exe -m pip install --upgrade pip

Write-Host "Installing requirements..." -ForegroundColor Cyan
.\venv\Scripts\pip.exe install -r requirements.txt

Write-Host "Environment updated successfully!" -ForegroundColor Green
