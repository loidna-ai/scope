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

# 개별 Hotspot 분석 결과 JSON 저장 (output/contact_analysis, deform_analysis, necking_analysis)
SAVE_INDIVIDUAL_HOTSPOT_JSON = False  # True: 각 Worker별 JSON 저장 (디버그/감사용), False: 저장 안 함

# 리포트 생성 방식: True=LLM 기반(프롬프트), False=정규식/템플릿 기반
USE_LLM_REPORT_GENERATOR = True  # True: LLM이 Raw Log를 전문 보고서로 변환, False: 기존 format_investigation_result 사용

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

# API Rate Limit 방지 (Vertex AI traffic smoothing)
# 공식 문서: "Distributing API calls more evenly... Avoid sharp second-level spikes"
# 참고: https://cloud.google.com/vertex-ai/generative-ai/docs/standard-paygo
API_CALL_DELAY = 2.0  # 패치 간 대기(초) - 429 완화를 위해 traffic smoothing 강화
                        # 값이 클수록: 안정적이나 느림
                        # 값이 작을수록: 빠르나 429 throttling 위험

# Media Resolution 설정
MEDIA_RESOLUTION_DEFAULT = "MEDIA_RESOLUTION_HIGH"  # 기본값: HIGH 해상도
                                                      # 옵션: MEDIA_RESOLUTION_LOW, MEDIA_RESOLUTION_MEDIUM,
                                                      #       MEDIA_RESOLUTION_HIGH, MEDIA_RESOLUTION_ULTRA_HIGH
MEDIA_RESOLUTION_ULTRA_HIGH_ENABLED = False  # ULTRA_HIGH 사용 여부 (향후 구현)
                                              # True로 설정 시 특정 중요 Hotspot에만 ULTRA_HIGH 적용 가능
                                              # 참고: ULTRA_HIGH는 비용이 2배 증가 (1120 → 2240 tokens/이미지)

# === Gemini API Rate Limiting ===
GEMINI_TIER = 1
GEMINI_MODEL_NAME = "gemini-3-flash-preview"
GEMINI_FALLBACK_MODEL = "gemini-2.5-flash"

# Vertex AI gemini-3-flash-preview 기준 (공식 문서)
# - Standard PayGo: Flash 모델 Tier 1 = 2M TPM (Preview는 tier 미적용, 모델별 문서 참조)
# - 플랫폼 한도: 30,000 RPM per model per region (vertex-ai/docs/quotas)
# - 권장: Global endpoint + traffic smoothing (요청 분산)
# 참고: https://cloud.google.com/vertex-ai/generative-ai/docs/standard-paygo
#       https://cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-flash
GEMINI_TIER1_RPM = 30   # 분당 요청 제한 (Preview 모델 안정성을 위해 30으로 하향)
GEMINI_TIER1_RPD = 5000 # 일일 요청 제한 (Vertex AI 상한)
GEMINI_TIER1_CONCURRENT = 2  # 동시 실행 (Semaphore 2: 429 에러 방지를 위한 최적값)

# Model Fallback 전략
GEMINI_ENABLE_FALLBACK = True  # 자동 Fallback 활성화
GEMINI_FALLBACK_THRESHOLD = 2  # 연속 503 에러 2회 시 Fallback

# Daily Budget 관리
GEMINI_ENABLE_BUDGET_GUARD = True  # Retry Budget 보호 활성화
GEMINI_DAILY_RETRY_BUDGET = 100  # 하루 최대 재시도 횟수 제한

# === Hotspot Detector Slicing ===
HOTSPOT_PATCH_SIZE = 1024       # 패치 크기 (px)
HOTSPOT_OVERLAP = 200           # 패치 간 오버랩 (px)
HOTSPOT_NMS_IOU_THRESHOLD = 0.3 # NMS IoU 임계값 (0.0~1.0)

# === Event Loop ===
HOTSPOT_THREAD_JOIN_TIMEOUT = 600  # hotspot_detector_node 스레드 타임아웃 (초)

# === Vertex AI (선택) ===
USE_VERTEX_AI = True  # Vertex AI 사용
GOOGLE_CLOUD_PROJECT = "loidna-ai-scope"
GOOGLE_CLOUD_LOCATION = "global"  # gemini-3-flash-preview는 global 전용

# === Main.py Configuration ===
# 이미지 파일 처리 설정
MAX_IMAGE_SIZE_MB = 50  # 이미지 크기 제한 (MB)
IMAGE_EXTENSIONS = ["*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG", "*.heic", "*.HEIC"]  # 지원 이미지 확장자 목록
TEST_IMAGE_CANDIDATES = ["Primary_Arc_Bead_1.png", "Primary_Arc_Bead_1.jpg"]  # 테스트 모드에서 사용할 이미지 파일명 우선순위

# 리포트 포맷팅 설정
REASONING_TEXT_TRUNCATE_LENGTH = 300  # 텍스트 자르기 길이 (문자 수)
CONTENT_LINES_TRUNCATE_THRESHOLD = 8  # 콘텐츠 줄 수 제한 (이 값보다 많으면 중략)
FULL_AUDIT_TRAIL_OUTPUT = True  # True: 상세 토론 내역 전체 출력, False: 중략(앞3줄+...중략...+뒤2줄)
MAX_BULLET_POINTS = 5  # bullet 포인트 최대 개수

# 신뢰도 임계값 설정
CONFIDENCE_HIGH_THRESHOLD = 80  # High 신뢰도 임계값 (%)
CONFIDENCE_MEDIUM_THRESHOLD = 60  # Medium 신뢰도 임계값 (%)
