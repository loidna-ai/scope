# 가상환경 자동 활성화 스크립트
# 사용법: .\activate.ps1 또는 프로젝트 디렉토리에서 자동 실행

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPath = Join-Path $scriptPath "venv"

# 프로젝트 디렉토리로 이동
Set-Location $scriptPath

# 가상환경 활성화
if (Test-Path (Join-Path $venvPath "Scripts\Activate.ps1")) {
    & (Join-Path $venvPath "Scripts\Activate.ps1")
    Write-Host "✓ 가상환경이 활성화되었습니다. (Python $(python --version))" -ForegroundColor Green
    Write-Host "프로젝트 디렉토리: $scriptPath" -ForegroundColor Cyan
} else {
    Write-Host "✗ 가상환경을 찾을 수 없습니다: $venvPath" -ForegroundColor Red
    Write-Host "가상환경을 생성하려면: python -m venv venv" -ForegroundColor Yellow
}

