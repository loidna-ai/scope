"""
중앙 설정 파일
모든 상수, 임계값, 모델 경로 등을 여기서 관리합니다.
"""

# Real-ESRGAN 설정
SR_SCALE = 2  # 초해상도 확대 배율
MODEL_PATH = "weights/RealESRGAN_x4plus.pth"  # 모델 가중치 경로

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
