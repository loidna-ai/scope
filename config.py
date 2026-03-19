"""
중앙 설정 파일
모든 상수, 임계값, 모델 경로 등을 여기서 관리합니다.
"""

# Real-ESRGAN 설정
SR_SCALE = 2  # 초해상도 확대 배율
MODEL_PATH = "weights/RealESRGAN_x4plus.pth"  # PyTorch 모델 가중치 경로
MODEL_PATH_ONNX = "weights/Real-ESRGAN-x4plus.onnx"  # ONNX 모델 경로 (AMD GPU 가속용)
USE_ONNX_PREFERRED = True  # ONNX Runtime 우선 사용 여부 (True: ONNX 우선, False: PyTorch 우선)

# CLAHE 필터 설정
CLAHE_CLIP_LIMIT = 4.0  # CLAHE 클립 리미트
CLAHE_TILE_GRID_SIZE = (8, 8)  # CLAHE 타일 그리드 크기

# 출력 디렉토리
OUTPUT_DIR = "outputs"  # 기본 출력 디렉토리

# 캐시 디렉토리 (사용자 결과물과 분리하여 관리)
CACHE_DIR = ".enhancement_cache"

# 캐시 보관 기간 (일). 분석 시작 시 이 기간 초과 캐시 자동 삭제
CACHE_MAX_AGE_DAYS = 7

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

# Hotspot 최소 심각도 임계값 (이 값 미만은 분석 대상에서 제외)
MIN_SEVERITY_FOR_ANALYSIS = 50  # severity_score 50 미만은 분석 가치가 낮으므로 제외

# [Deprecated] API_CALL_DELAY - Native Async 리팩토링(2026-02) 후 미사용
# Rate Limiter(acquire_api_slot)가 traffic smoothing을 담당함

# Media Resolution 설정
MEDIA_RESOLUTION_DEFAULT = "MEDIA_RESOLUTION_HIGH"  # 기본값: HIGH 해상도
                                                      # 옵션: MEDIA_RESOLUTION_LOW, MEDIA_RESOLUTION_MEDIUM,
                                                      #       MEDIA_RESOLUTION_HIGH, MEDIA_RESOLUTION_ULTRA_HIGH
MEDIA_RESOLUTION_ULTRA_HIGH_ENABLED = False  # ULTRA_HIGH 사용 여부 (향후 구현)
                                              # True로 설정 시 특정 중요 Hotspot에만 ULTRA_HIGH 적용 가능
                                              # 참고: ULTRA_HIGH는 비용이 2배 증가 (1120 → 2240 tokens/이미지)

# === Gemini API Rate Limiting ===
GEMINI_TIER = 1
GEMINI_MODEL_NAME = "gemini-2.5-flash"
GEMINI_PRO_MODEL_NAME = "gemini-2.5-pro"
GEMINI_FALLBACK_MODEL = "gemini-2.5-flash"

# Vertex AI gemini-2.5-flash / gemini-2.5-pro 기준 (GA 모델, Standard PayGo Tier 적용)
# - Standard PayGo: Flash Tier 1 = 2M TPM, Pro Tier 1 = 500K TPM
# - 플랫폼 한도: 30,000 RPM per model per region (vertex-ai/docs/quotas)
# - 권장: Global endpoint + traffic smoothing (요청 분산)
# 참고: https://cloud.google.com/vertex-ai/generative-ai/docs/standard-paygo
#       https://cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/2-5-flash
# Flash 전용 (Hotspot, Preprocessor, Workers, Debater(Flash), FactChecker 등)
GEMINI_TIER1_RPM = 30   # 분당 요청 제한
GEMINI_TIER1_RPD = 5000 # 일일 요청 제한 (Vertex AI 상한)
GEMINI_TIER1_CONCURRENT = 2  # 동시 실행 (Semaphore 2: 429 에러 방지를 위한 최적값)

# Pro 전용 (Supervisor, Analyst, Critic, Judge, Report Generator, Debater(Pro))
# Pro는 Vertex AI에서 별도 할당량·더 낮은 동시성 → 분리된 Rate Limiter 필수
GEMINI_PRO_RPM = 10         # Pro 분당 요청 (429 완화를 위해 10으로 하향)
GEMINI_PRO_CONCURRENT = 1   # Pro 동시 실행 (burst·429 방지)

# Model Fallback 전략
GEMINI_ENABLE_FALLBACK = True  # 자동 Fallback 활성화
GEMINI_FALLBACK_THRESHOLD = 2  # 연속 503 에러 2회 시 Fallback

# Daily Budget 관리
GEMINI_ENABLE_BUDGET_GUARD = True  # Retry Budget 보호 활성화
GEMINI_DAILY_RETRY_BUDGET = 100  # 하루 최대 재시도 횟수 제한

# === Hotspot Detector Slicing ===
HOTSPOT_MAX_IMAGE_DIMENSION = 2048 # 최대 이미지 해상도(이보다 크면 다운스케일링)
HOTSPOT_PATCH_SIZE = 1024       # 패치 크기 (px)
HOTSPOT_OVERLAP = 200           # 패치 간 오버랩 (px)
HOTSPOT_NMS_IOU_THRESHOLD = 0.3 # NMS IoU 임계값 (0.0~1.0)
HOTSPOT_BLUR_THRESHOLD = 50.0   # OpenCV Laplacian Variance (이하 값이면 블러로 간주해 Drop)
HOTSPOT_EDGE_THRESHOLD = 10     # OpenCV Canny Edge 평균값 (이하 값이면 텍스처/정보가 없다고 간주해 Drop)
HOTSPOT_BATCH_SIZE = 5          # 1번의 API 호출에 태울 이미지 패치 개수 제한. Gemini 2.5 Flash의 Multi-Image 특성을 활용하여 여러 장을 일괄 전송함.

# === Image Pre-processing ===
PRE_RESIZE_ENABLED = True   # True: 파이프라인 진입 시 자동 리사이즈 수행
PRE_RESIZE_MAX_DIMENSION = 2048  # 최대 이미지 해상도 제한 (HOTSPOT_MAX_IMAGE_DIMENSION과 동일 권장)
PRE_RESIZE_JPEG_QUALITY = 88

# === Event Loop ===
# [Deprecated] Native Async 리팩토링 후 스레드 기반 실행 제거됨 (2026-02)

# === Vertex AI (선택) ===
USE_VERTEX_AI = True  # Vertex AI 사용
GOOGLE_CLOUD_PROJECT = "loidna-ai-scope"
GOOGLE_CLOUD_LOCATION = "global"  # gemini-2.5-flash/pro는 global 지원

# === Main.py Configuration ===
# 이미지 파일 처리 설정
MAX_IMAGE_SIZE_MB = 50  # 이미지 크기 제한 (MB)
IMAGE_EXTENSIONS = ["*.png", "*.jpg", "*.jpeg", "*.PNG", "*.JPG", "*.JPEG", "*.heic", "*.HEIC"]  # 지원 이미지 확장자 목록
TEST_IMAGE_CANDIDATES = ["Primary_Arc_Bead_1.png", "Primary_Arc_Bead_1.jpg"]  # 테스트 모드에서 사용할 이미지 파일명 우선순위

# 리포트 포맷팅 설정
EMBED_IMAGE_IN_MARKDOWN = True  # True: 이미지를 Base64로 마크다운에 직접 삽입 (단일 파일, 어디서나 표시), False: 상대 경로 참조
REASONING_TEXT_TRUNCATE_LENGTH = 300  # 텍스트 자르기 길이 (문자 수)
CONTENT_LINES_TRUNCATE_THRESHOLD = 8  # 콘텐츠 줄 수 제한 (이 값보다 많으면 중략)
FULL_AUDIT_TRAIL_OUTPUT = True  # True: 상세 토론 내역 전체 출력, False: 중략(앞3줄+...중략...+뒤2줄)
MAX_BULLET_POINTS = 5  # bullet 포인트 최대 개수

# 신뢰도 임계값 설정
CONFIDENCE_HIGH_THRESHOLD = 80  # High 신뢰도 임계값 (%)
CONFIDENCE_MEDIUM_THRESHOLD = 60  # Medium 신뢰도 임계값 (%)
