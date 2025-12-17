# 실행 방법

## 1. 가상환경 활성화

### PowerShell에서:
```powershell
.\venv\Scripts\Activate.ps1
```

### CMD에서:
```cmd
venv\Scripts\activate.bat
```

## 2. 필요한 패키지 설치 (최초 1회)

```powershell
pip install -r requirements.txt
```

## 3. 실행

```powershell
python main.py Data\Primary_Arc_Bead_1.png
```

또는

```powershell
python main.py Data/Primary_Arc_Bead_1.png
```

## 실행 예시

```powershell
# PowerShell에서
.\venv\Scripts\Activate.ps1
python main.py Data\Primary_Arc_Bead_1.png
```

## 출력

실행 후 `outputs/` 디렉토리에 다음 파일들이 생성됩니다:

- `0_input_Primary_Arc_Bead_1.png` - 원본 이미지
- `1_cropped.png` - 크롭된 이미지
- `2_enhanced.png` - 향상된 이미지 (4x 확대)
- `3_filtered.png` - 필터 적용 이미지
- `analyzer/4_analysis_mask.png` - 분석 마스크
- `llm_analysis_data.json` - 분석 데이터 (표준 형식)
- `llm_gemini_format.json` - Gemini 형식
- `llm_gemini_request.json` - Gemini 요청 형식

