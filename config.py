"""
중앙 설정 파일
모든 상수, 임계값, 모델 경로 등을 여기서 관리합니다.
"""

# Real-ESRGAN 설정
SR_SCALE = 4  # 초해상도 확대 배율
MODEL_PATH = "weights/RealESRGAN_x4plus.pth"  # PyTorch 모델 가중치 경로
MODEL_PATH_ONNX = "weights/Real-ESRGAN-x4plus.onnx"  # ONNX 모델 경로 (AMD GPU 가속용)
USE_ONNX_PREFERRED = True  # ONNX Runtime 우선 사용 여부 (True: ONNX 우선, False: PyTorch 우선)

# CLAHE 필터 설정
CLAHE_CLIP_LIMIT = 4.0  # CLAHE 클립 리미트
CLAHE_TILE_GRID_SIZE = (8, 8)  # CLAHE 타일 그리드 크기

# 출력 디렉토리
OUTPUT_DIR = "outputs"  # 기본 출력 디렉토리

# 데이터 디렉토리
DATA_DIR = "data"  # 입력 이미지가 있는 디렉토리

# 이미지 처리 설정
CROP_PADDING = 40  # 크롭 시 추가할 패딩 픽셀 수
CROP_MIN_AREA_RATIO = 0.01  # 최소 크롭 영역 비율 (전체 이미지 대비)

# 형태학적 처리 설정
MORPH_KERNEL_SIZE = (5, 5)  # Morphological Gradient 커널 크기
DILATION_KERNEL_SIZE = (9, 9)  # Dilation 커널 크기
DILATION_ITERATIONS = 2  # Dilation 반복 횟수

# Arbiter Agent 설정
ARBITER_CONFIDENCE_THRESHOLD = 0.6  # 전문가 신뢰도 평균 임계값 (60%). 이 값 미만일 경우 판단 불가(UNDETERMINED) 상태로 처리

# === Analysis Configuration ===
# Hotspot 선정 개수 설정
TOP_N_HOTSPOTS = 5  # 각 Expert가 분석할 최대 Hotspot 개수 (기본값: 5)
                     # 값이 클수록: 더 많은 증거 수집, 높은 비용/시간
                     # 값이 작을수록: 빠른 처리, 낮은 비용, 증거 누락 위험

# API Rate Limit 방지
API_CALL_DELAY = 1.5  # Hotspot 간 대기 시간 (초)
                      # Gemini API RPM 제한 방지용
                      # 값이 클수록: 안정적이나 느림
                      # 값이 작을수록: 빠르나 Rate Limit 위험

# Media Resolution 설정
MEDIA_RESOLUTION_DEFAULT = "MEDIA_RESOLUTION_HIGH"  # 기본값: HIGH 해상도
                                                      # 옵션: MEDIA_RESOLUTION_LOW, MEDIA_RESOLUTION_MEDIUM,
                                                      #       MEDIA_RESOLUTION_HIGH, MEDIA_RESOLUTION_ULTRA_HIGH
MEDIA_RESOLUTION_ULTRA_HIGH_ENABLED = False  # ULTRA_HIGH 사용 여부 (향후 구현)
                                              # True로 설정 시 특정 중요 Hotspot에만 ULTRA_HIGH 적용 가능
                                              # 참고: ULTRA_HIGH는 비용이 2배 증가 (1120 → 2240 tokens/이미지)

# === Gemini API Rate Limiting (Tier 1 Paid) ===
GEMINI_TIER = 1
GEMINI_MODEL_NAME = "gemini-3-flash-preview"
GEMINI_FALLBACK_MODEL = "gemini-2.5-flash"

# Tier 1 Preview Model Limits
# Preview 모델은 일반 Tier 1보다 제한적 (RPM: 20-25, RPD: 250)
GEMINI_TIER1_RPM = 20  # 분당 요청 제한 (보수적으로 20 설정)
GEMINI_TIER1_RPD = 250  # 일일 요청 제한
GEMINI_TIER1_CONCURRENT = 3  # 동시 실행 제한 (503 에러 완화를 위해 5→3으로 감소)

# Model Fallback 전략
GEMINI_ENABLE_FALLBACK = True  # 자동 Fallback 활성화
GEMINI_FALLBACK_THRESHOLD = 2  # 연속 503 에러 2회 시 Fallback

# Daily Budget 관리
GEMINI_ENABLE_BUDGET_GUARD = True  # Retry Budget 보호 활성화
GEMINI_DAILY_RETRY_BUDGET = 100  # 하루 최대 재시도 횟수 제한
