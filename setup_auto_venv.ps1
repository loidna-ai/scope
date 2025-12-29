# PowerShell 프로필에 자동 가상환경 활성화 기능 추가
# 사용법: .\setup_auto_venv.ps1

$profilePath = $PROFILE
$projectPath = "C:\Users\loidn\Documents\Projects\P_04_Scope"

# 프로필 디렉토리 생성 (없는 경우)
$profileDir = Split-Path -Parent $profilePath
if (-not (Test-Path $profileDir)) {
    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
}

# 자동 활성화 함수
$autoActivateFunction = @"

# P_04_Scope 프로젝트 자동 가상환경 활성화
function Enter-P04Scope {
    `$projectPath = "$projectPath"
    if (Test-Path `$projectPath) {
        Set-Location `$projectPath
        `$venvPath = Join-Path `$projectPath "venv"
        if (Test-Path (Join-Path `$venvPath "Scripts\Activate.ps1")) {
            & (Join-Path `$venvPath "Scripts\Activate.ps1")
            Write-Host "✓ P_04_Scope 가상환경 활성화됨" -ForegroundColor Green
        }
    }
}

# 프로젝트 디렉토리로 이동 시 자동 활성화 (선택사항)
# 주석을 해제하면 프로젝트 디렉토리로 이동할 때마다 자동으로 활성화됩니다
# function prompt {
#     `$currentPath = Get-Location
#     if (`$currentPath.Path -eq "$projectPath" -or `$currentPath.Path.StartsWith("$projectPath")) {
#         `$venvPath = Join-Path "$projectPath" "venv"
#         if (Test-Path (Join-Path `$venvPath "Scripts\Activate.ps1")) {
#             `$env:VIRTUAL_ENV = Join-Path `$venvPath "Scripts"
#             if (`$env:VIRTUAL_ENV -ne `$env:VIRTUAL_ENV_DISABLE_PROMPT) {
#                 & (Join-Path `$venvPath "Scripts\Activate.ps1") | Out-Null
#             }
#         }
#     }
#     `$prompt = "PS `$(`$executionContext.SessionState.Path.CurrentLocation)`$('>' * (`$nestedPromptLevel + 1)) "
#     return `$prompt
# }

"@

# 프로필에 추가 (중복 방지)
if (Test-Path $profilePath) {
    $existingContent = Get-Content $profilePath -Raw
    if ($existingContent -notmatch "Enter-P04Scope") {
        Add-Content -Path $profilePath -Value "`n$autoActivateFunction"
        Write-Host "✓ PowerShell 프로필에 자동 활성화 기능이 추가되었습니다." -ForegroundColor Green
    } else {
        Write-Host "⚠ PowerShell 프로필에 이미 자동 활성화 기능이 있습니다." -ForegroundColor Yellow
    }
} else {
    Set-Content -Path $profilePath -Value $autoActivateFunction
    Write-Host "✓ PowerShell 프로필이 생성되고 자동 활성화 기능이 추가되었습니다." -ForegroundColor Green
}

Write-Host "`n사용 방법:" -ForegroundColor Cyan
Write-Host "  1. PowerShell을 다시 시작하거나 다음 명령어 실행:" -ForegroundColor White
Write-Host "     . `$PROFILE" -ForegroundColor Yellow
Write-Host "  2. 프로젝트 디렉토리로 이동하고 가상환경 활성화:" -ForegroundColor White
Write-Host "     Enter-P04Scope" -ForegroundColor Yellow
Write-Host "  또는 프로젝트 루트의 activate.ps1 실행:" -ForegroundColor White
Write-Host "     .\activate.ps1" -ForegroundColor Yellow

