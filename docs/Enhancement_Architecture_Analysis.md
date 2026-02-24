# Enhancement (업스케일링) 구조 및 워크플로우 분석

## 목차
1. [개요](#개요)
2. [아키텍처 구조](#아키텍처-구조)
3. [ImageEnhancer 클래스 상세 분석](#imageenhancer-클래스-상세-분석)
4. [워크플로우](#워크플로우)
5. [성능 최적화 전략](#성능-최적화-전략)
6. [백엔드 선택 로직](#백엔드-선택-로직)
7. [에러 처리 및 Fallback](#에러-처리-및-fallback)

---

## 개요

### 목적
화재 조사 이미지 분석에서 Hotspot ROI(Region of Interest) 영역의 해상도를 2배 향상시켜 상세 분석을 가능하게 합니다.

### 핵심 설계 원칙
- **Lazy Evaluation**: 모든 hotspot을 일괄 업스케일링하지 않고, 각 전문가가 필요할 때만 수행
- **싱글톤 패턴**: 모델을 한 번만 로드하고 모든 인스턴스가 공유하여 메모리 효율성 확보
- **하이브리드 백엔드**: CUDA/DirectML/CPU 자동 감지 및 최적 백엔드 선택
- **분산 처리**: 각 전문가 Worker가 독립적으로 업스케일링 수행

---

## 아키텍처 구조

### 파일 구조
```
src/nodes/
├── enhancement.py          # ImageEnhancer 클래스 정의 (핵심 엔진)
└── expert_worker_utils.py  # 전문가 노드용 공통 유틸리티 (인터페이스)
    ├── crop_and_enhance_roi()    # 크롭 + 업스케일링
    └── enhance_roi_only()        # 업스케일링만 수행

src/nodes/
├── contact_nodes.py        # Contact 전문가 노드
├── deform_nodes.py         # Deform 전문가 노드
├── necking_nodes.py        # Necking 전문가 노드
└── preprocessor_node.py    # 전처리 노드 (Crop + Classification만 수행)
```

### 컴포넌트 계층 구조

```
┌─────────────────────────────────────────────────────────┐
│              전문가 Worker 노드들                        │
│  (contact_nodes, deform_nodes, necking_nodes)          │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │  expert_worker_utils.py                          │  │
│  │  - crop_and_enhance_roi()                        │  │
│  │  - enhance_roi_only()                            │  │
│  └──────────────────────────────────────────────────┘  │
│                        ↓                                 │
│  ┌──────────────────────────────────────────────────┐  │
│  │  enhancement.py                                  │  │
│  │  - ImageEnhancer 클래스                           │  │
│  │    ├── 싱글톤 모델 공유                          │  │
│  │    ├── 백엔드 자동 감지                          │  │
│  │    └── upscale() 메서드                          │  │
│  └──────────────────────────────────────────────────┘  │
│                        ↓                                 │
│  ┌──────────────────────────────────────────────────┐  │
│  │  백엔드 구현                                      │  │
│  │  - PyTorch (CUDA/CPU)                            │  │
│  │  - ONNX Runtime (DirectML/CPU)                   │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## ImageEnhancer 클래스 상세 분석

### 클래스 구조

```python
class ImageEnhancer:
    """Real-ESRGAN 기반 이미지 향상 클래스 (싱글톤 패턴으로 모델 공유)"""
    
    # 전역 싱글톤 변수들
    _shared_upscaler = None      # 공유 모델 인스턴스
    _upscaler_type = None         # "onnx" 또는 "pytorch"
    _onnx_input_shape = None     # ONNX 모델 입력 크기 정보
    _upscaler_lock = threading.Lock()      # 모델 로딩 동시성 제어
    _onnx_inference_lock = threading.Lock() # ONNX 추론 동시성 제어
```

### 주요 메서드

#### 1. `__init__(model_path: str = None)`
**역할**: 향상기 초기화 및 모델 로딩

**동작 흐름**:
1. 싱글톤 체크: `_shared_upscaler`가 이미 존재하면 재사용
2. 백엔드 감지: `_detect_available_backend()` 호출
3. 백엔드별 모델 로딩:
   - **DirectML**: ONNX Runtime 모델 로드 시도
   - **CUDA/CPU**: PyTorch 모델 로드
4. 전역 변수에 저장하여 모든 인스턴스가 공유

**백엔드 우선순위**:
1. CUDA (NVIDIA GPU)
2. DirectML (AMD GPU)
3. CPU (Fallback)

#### 2. `_detect_available_backend() -> str`
**역할**: 사용 가능한 하드웨어 백엔드 감지

**로직**:
```python
if torch.cuda.is_available():
    return "cuda"
elif HAS_ONNX_RUNTIME and 'DmlExecutionProvider' in available_providers:
    return "directml"
else:
    return "cpu"
```

#### 3. `upscale(img: np.ndarray) -> np.ndarray`
**역할**: 이미지를 4배 해상도로 업스케일링

**동작 흐름**:
1. `upscaler_type` 확인
2. 타입별 분기:
   - `"onnx"`: `upscale_onnx()` 호출
   - `"pytorch"`: `self.upscaler.enhance(img, outscale=4)` 호출
3. 에러 발생 시 `cv2.resize()` Fallback

**입력/출력**:
- 입력: BGR 형식 numpy 배열 (HWC)
- 출력: 4배 확대된 BGR 형식 numpy 배열

#### 4. `upscale_onnx(img: np.ndarray) -> np.ndarray`
**역할**: ONNX Runtime을 사용한 업스케일링

**처리 단계**:
1. **전처리** (`_preprocess_onnx`):
   - 이미지 리사이즈 (비율 유지)
   - 패딩 추가 (중앙 정렬)
   - BGR → RGB 변환
   - 정규화 (0-255 → 0-1)
   - HWC → CHW → 배치 차원 추가

2. **추론** (`_onnx_inference_lock`으로 동시성 제어):
   - ONNX Runtime InferenceSession 실행
   - DirectML provider 사용 시 동시 실행 제한

3. **후처리** (`_postprocess_onnx`):
   - 배치 차원 제거
   - CHW → HWC 변환
   - 0-1 → 0-255 변환
   - RGB → BGR 변환
   - 패딩 제거 및 원본 크기의 4배로 리사이즈

#### 5. `_load_model_pytorch(model_path: str) -> RealESRGANer`
**역할**: PyTorch 기반 Real-ESRGAN 모델 로딩

**동작**:
1. 모델 파일이 없으면 자동 다운로드
2. RRDBNet 아키텍처 정의 (scale=4)
3. 디바이스 선택 (CUDA 우선, 없으면 CPU)
4. RealESRGANer 초기화

---

## 워크플로우

### 전체 그래프 흐름

```
START
  ↓
hotspot_detector_node
  ↓ (hotspots 생성)
preprocessor_node
  ↓ (Crop + Classification만 수행, Enhancement 제외)
  ├─→ contact_expert_wrapper_node
  ├─→ deform_expert_wrapper_node
  └─→ necking_expert_wrapper_node
      ↓ (각 전문가 Worker에서 Enhancement 수행)
      └─→ arbiter_expert_wrapper_node
          ↓
          END
```

### 상세 워크플로우

#### 1. Preprocessor Node 단계
**파일**: `src/nodes/preprocessor_node.py`

**수행 작업**:
- ✅ ROI 크롭 (`_crop_roi`)
- ✅ 컴포넌트 분류 (`_classify`)
- ❌ **Enhancement 제외** (성능 최적화)

**출력**:
```python
preprocessed_hotspots = [
    {
        ...original hotspot fields...,
        "roi_image_path": "/path/to/cropped.jpg",  # 크롭만 완료
        "component_type": "Wire",
        "_preprocessed": True  # Enhancement 필요 플래그
    },
    ...
]
```

#### 2. 전문가 Worker 단계
**파일**: `src/nodes/expert_worker_utils.py`

**시나리오 A: Preprocessor를 거친 경우**
```python
if hotspot.get("_preprocessed"):
    cropped_path = hotspot.get("roi_image_path")
    # Enhancement만 수행
    roi_image_path = await enhance_roi_only(hotspot_id, cropped_path)
```

**시나리오 B: Preprocessor를 거치지 않은 경우 (Fallback)**
```python
else:
    box_2d = hotspot.get("box_2d")
    # 크롭 + Enhancement 모두 수행
    roi_image_path = await crop_and_enhance_roi(hotspot_id, image_path, box_2d)
```

#### 3. Enhancement 실행 흐름 (캐싱 적용)

**`enhance_roi_only()` 함수**:
```python
async def enhance_roi_only(hotspot_id: str, cropped_image_path: str) -> str:
    # 1. 캐시 확인 (중복 업스케일링 방지)
    cached_enhanced_path = await asyncio.to_thread(get_cached_enhancement, cropped_image_path)
    if cached_enhanced_path:
        # 캐시 히트: 즉시 반환
        return cached_enhanced_path
    
    # 2. 크롭된 이미지 로드 (비동기)
    cropped_img = await asyncio.to_thread(cv2.imread, cropped_image_path)
    
    # 3. Enhancement 수행 (동기 함수를 스레드로 실행)
    def enhance_image(img, path):
        enhancer = ImageEnhancer()  # 싱글톤 인스턴스 획득
        enhanced_img = enhancer.upscale(img)  # SR_SCALE배 업스케일링 (기본 2배)
        cv2.imwrite(path, enhanced_img)  # 덮어쓰기
        return path
    
    enhanced_path = await asyncio.to_thread(enhance_image, cropped_img, cropped_image_path)
    
    # 4. 캐시 저장 (다음 요청 시 재사용)
    await asyncio.to_thread(save_enhancement_cache, cropped_image_path, enhanced_path)
    return enhanced_path
```

**`crop_and_enhance_roi()` 함수**:
```python
async def crop_and_enhance_roi(hotspot_id: str, image_path: str, box_2d: Dict) -> str:
    # 1. ROI 크롭
    cropped_path = await asyncio.to_thread(crop_roi_from_box, image_path, box_2d)
    
    # 2. Enhancement (enhance_roi_only와 동일한 로직)
    # ...
    
    return roi_image_path
```

#### 4. ImageEnhancer.upscale() 내부 흐름

```
upscale(img)
  ↓
[백엔드 타입 확인]
  ├─→ "onnx" → upscale_onnx()
  │     ↓
  │   [전처리] → [ONNX 추론] → [후처리]
  │
  └─→ "pytorch" → self.upscaler.enhance(img, outscale=config.SR_SCALE)
        ↓
      [Real-ESRGAN 처리]
```

#### 5. 캐싱 메커니즘 흐름

```
enhance_roi_only(cropped_image_path)
  ↓
[캐시 확인]
  ├─→ 캐시 히트 → 즉시 반환 (< 0.001초)
  │
  └─→ 캐시 미스
        ↓
      [업스케일링 수행]
        ↓
      [캐시 저장]
        ↓
      [결과 반환]
```

---

## 성능 최적화 전략

### 1. 싱글톤 패턴
**목적**: 모델을 한 번만 로드하여 메모리 절약

**구현**:
```python
_shared_upscaler = None  # 전역 변수
_upscaler_lock = threading.Lock()  # 동시성 제어

with _upscaler_lock:
    if _shared_upscaler is None:
        # 모델 로딩 (최초 1회만)
        _shared_upscaler = load_model()
    
    self.upscaler = _shared_upscaler  # 모든 인스턴스가 공유
```

**효과**:
- 메모리 사용량 감소 (모델 1개만 메모리에 상주)
- 초기화 시간 단축 (두 번째 호출부터 즉시 사용)

### 2. Lazy Evaluation
**목적**: 필요한 hotspot만 업스케일링하여 불필요한 연산 제거

**구현**:
- `preprocessor_node`: Enhancement 제외
- 각 전문가 Worker: 필요 시에만 `enhance_roi_only()` 호출

**효과**:
- CPU/GPU 리소스 절약
- 전체 처리 시간 단축

### 3. 비동기 처리
**목적**: I/O 블로킹 방지

**구현**:
```python
# 동기 함수를 스레드로 실행
enhanced_path = await asyncio.to_thread(enhance_image, cropped_img, cropped_path)
```

**효과**:
- 다른 작업과 병렬 처리 가능
- 전체 파이프라인 성능 향상

### 4. 캐싱 메커니즘 ✅ 구현 완료
**목적**: 동일 ROI 이미지에 대한 중복 업스케일링 방지

**구현** (`src/nodes/enhancement_cache.py`):
- **파일 기반 캐싱**: `outputs/.enhancement_cache/` 디렉토리에 저장
- **해시 기반 키**: 파일 경로 + 크기 + 수정 시간 + 스케일
- **이중 캐시 구조**: 메모리 캐시 + 파일 캐시
- **자동 정리**: 7일 이상 오래된 캐시 파일 자동 삭제

**사용 위치**:
- `crop_and_enhance_roi()`: 크롭 후 캐시 확인 → 업스케일링 → 캐시 저장
- `enhance_roi_only()`: 캐시 확인 → 업스케일링 → 캐시 저장

**효과**:
- 여러 전문가가 동일 hotspot 처리 시 중복 업스케일링 방지
- 세션 간 캐시 유지로 재실행 시 성능 향상
- 캐시 히트 시 즉시 반환 (< 0.001초)

### 5. 동시성 제어 (ONNX Runtime)
**목적**: DirectML의 동시 실행 제한 대응

**구현**:
```python
_onnx_inference_lock = threading.Lock()

with _onnx_inference_lock:
    output_tensor = self.upscaler.run(None, {input_name: input_tensor})[0]
```

**효과**:
- DirectML provider 안정성 확보
- 동시 요청 시 에러 방지

---

## 백엔드 선택 로직

### 백엔드 우선순위

```
1. CUDA (NVIDIA GPU)
   ├─ 조건: torch.cuda.is_available() == True
   ├─ 모델: PyTorch Real-ESRGAN
   └─ 성능: 최고 (GPU 가속)

2. DirectML (AMD GPU)
   ├─ 조건: ONNX Runtime 설치 + DmlExecutionProvider 사용 가능
   ├─ 모델: ONNX Runtime (RealESRGAN-x4plus.onnx)
   └─ 성능: 높음 (GPU 가속)

3. CPU (Fallback)
   ├─ 조건: 위 두 가지 모두 불가능
   ├─ 모델: PyTorch Real-ESRGAN
   └─ 성능: 낮음 (CPU 처리)
```

### 백엔드별 특징

#### CUDA (PyTorch)
- **장점**: 최고 성능, 널리 사용됨
- **단점**: NVIDIA GPU 필요
- **모델 경로**: `config.MODEL_PATH` (기본: `weights/RealESRGAN_x4plus.pth`)

#### DirectML (ONNX Runtime)
- **장점**: AMD GPU 지원, 크로스 플랫폼
- **단점**: ONNX 모델 필요, 동시성 제한
- **모델 경로**: `config.MODEL_PATH_ONNX` (기본: `weights/RealESRGAN-x4plus.onnx`)

#### CPU (PyTorch Fallback)
- **장점**: 모든 환경에서 동작
- **단점**: 느린 처리 속도
- **모델 경로**: `config.MODEL_PATH`

---

## 에러 처리 및 Fallback

### 에러 처리 계층

```
1. 모델 로딩 실패
   ├─ ONNX 로딩 실패 → PyTorch로 Fallback
   ├─ PyTorch 로딩 실패 → 모델 다운로드 시도
   └─ 모든 실패 → upscaler = None

2. 업스케일링 실패
   ├─ ONNX 추론 실패 → cv2.resize() Fallback
   ├─ PyTorch 추론 실패 → cv2.resize() Fallback
   └─ 모든 실패 → 원본 이미지 반환

3. 파일 I/O 실패
   ├─ 이미지 읽기 실패 → 원본 경로 반환
   └─ 이미지 쓰기 실패 → 경고 로그만 출력
```

### Fallback 메커니즘

#### 1. Bicubic Interpolation Fallback
```python
except Exception as e:
    logger.warning(f"Upscale 실패, cv2.resize fallback: {e}")
    return cv2.resize(img, (w * config.SR_SCALE, h * config.SR_SCALE))
```

**사용 시점**:
- Real-ESRGAN 모델 로딩 실패
- 추론 중 에러 발생
- 의존성 누락

**특징**:
- 빠른 처리 속도
- 품질은 Real-ESRGAN보다 낮음
- 항상 동작 보장

#### 2. Graceful Degradation
```python
except Exception as enh_err:
    logger.warning(f"Worker {hotspot_id}: Enhancement Failed: {enh_err}")
    # 원본 크롭 이미지 그대로 사용
    roi_image_path = cropped_path
```

**사용 시점**:
- Enhancement 완전 실패 시
- 원본 해상도로도 분석 가능한 경우

---

## 설정 및 의존성

### Config 설정 (`config.py`)
```python
SR_SCALE = 2  # 업스케일 배율 (2배 모드)
MODEL_PATH = "weights/RealESRGAN_x4plus.pth"  # PyTorch 모델
MODEL_PATH_ONNX = "weights/RealESRGAN-x4plus.onnx"  # ONNX 모델
```

### 필수 의존성 (`requirements.txt`)
```python
basicsr>=1.4.2          # Real-ESRGAN 기본 라이브러리
realesrgan>=0.3.0       # Real-ESRGAN 래퍼
torch>=2.0.0            # PyTorch (CUDA/CPU)
onnxruntime-directml>=1.16.0  # ONNX Runtime (DirectML 지원)
opencv-python-headless>=4.8.0  # 이미지 처리
```

---

## 사용 예시

### 전문가 노드에서의 사용

**Contact Expert** (`contact_nodes.py`):
```python
# Preprocessor를 거친 경우
if hotspot.get("_preprocessed"):
    roi_image_path = await enhance_roi_only(hotspot_id, cropped_path)

# Fallback 경로
else:
    roi_image_path = await crop_and_enhance_roi(hotspot_id, image_path, box_2d)
```

**Deform Expert** (`deform_nodes.py`):
```python
# 동일한 패턴 사용
roi_image_path = await enhance_roi_only(hotspot_id, cropped_path)
```

**Necking Expert** (`necking_nodes.py`):
```python
# 동일한 패턴 사용
roi_image_path = await enhance_roi_only(hotspot_id, cropped_path)
```

---

## 성능 특성

### 처리 시간 (예상)
- **CUDA (NVIDIA GPU)**: 100x100 → 200x200 약 0.05-0.2초
- **DirectML (AMD GPU)**: 100x100 → 200x200 약 0.1-0.5초
- **CPU**: 100x100 → 200x200 약 1-5초
- **Bicubic Fallback**: 100x100 → 200x200 약 0.01초
- **캐시 히트**: 즉시 반환 (< 0.001초)

### 메모리 사용량
- **모델 로딩**: 약 200-500MB (백엔드별 상이)
- **싱글톤 공유**: 모델 1개만 메모리 상주
- **이미지 버퍼**: 입력 크기의 4배 (2x2 = 4배 픽셀)
- **캐시 메모리**: 메모리 캐시 딕셔너리 (경로만 저장, 이미지 데이터는 파일 시스템에 저장)

---

## 개선 가능 영역

### 1. 캐싱 메커니즘 ✅ 구현 완료
- **구현 상태**: 파일 기반 캐싱 시스템 구현 완료 (`src/nodes/enhancement_cache.py`)
- **동작 방식**:
  - 동일 ROI 이미지에 대한 중복 업스케일링 방지
  - 파일 해시 기반 캐시 키 생성 (경로 + 크기 + 수정 시간 + 스케일)
  - 메모리 캐시 + 파일 캐시 이중 구조
  - 캐시 디렉토리: `outputs/.enhancement_cache/`
- **효과**:
  - 여러 전문가가 동일 hotspot을 처리할 때 중복 업스케일링 방지
  - 세션 간 캐시 유지로 재실행 시 성능 향상
  - 자동 캐시 정리 기능 (7일 이상 오래된 파일 삭제)

### 2. 배치 처리
- **현재 상태**: LangGraph의 Send API를 통해 여러 Worker가 병렬 실행됨
- **GPU 레벨**: 각 Worker가 독립적으로 `asyncio.to_thread`로 실행되므로, GPU 추론은 순차적으로 큐에 들어감
- **개선 가능**: 여러 ROI를 배치로 묶어 한 번에 처리하면 GPU 활용도 향상 가능
- **참고**: Real-ESRGAN은 기본적으로 단일 이미지 처리용이지만, 배치 처리 구현 가능

### 3. 동적 배율 선택
- 현재는 `config.SR_SCALE`로 설정 가능 (기본값: 2배)
- ROI 크기에 따라 배율 조정 가능 (향후 개선)

### 4. 품질 설정
- Real-ESRGAN 모델 변형 선택 (x2, x4, x8)
- 속도/품질 트레이드오프 설정

---

## 결론

현재 Enhancement 시스템은 다음과 같은 특징을 가집니다:

✅ **효율성**: 싱글톤 패턴과 Lazy Evaluation으로 리소스 최적화
✅ **캐싱**: 파일 기반 캐싱으로 중복 업스케일링 방지
✅ **유연성**: 여러 백엔드 지원으로 다양한 환경 대응
✅ **안정성**: 다층 Fallback 메커니즘으로 에러 복구
✅ **확장성**: 전문가별 독립적 처리로 병렬화 용이
✅ **설정 가능**: config.SR_SCALE로 배율 조정 가능 (기본값: 2배)

이 구조는 대규모 이미지 분석 파이프라인에서 안정적이고 효율적인 업스케일링을 제공합니다.

---

## 배치 처리 분석

### 현재 상태

**Worker 레벨 병렬 처리**:
- LangGraph의 `Send` API를 통해 여러 Worker가 **병렬 실행**됨
- 각 전문가 그래프에서 `distribute_work_generic()`이 여러 `Send` 객체를 반환
- 예: 5개 hotspot → 5개 Worker가 동시에 실행

**GPU 레벨 처리**:
- 각 Worker 내부에서 `asyncio.to_thread(enhance_image, ...)` 호출
- `enhance_image`는 동기 함수이므로 스레드 풀에서 실행
- **GPU 추론은 순차적으로 큐에 들어감** (동시 실행 아님)

### 배치 처리 vs 현재 방식

**현재 방식 (순차 GPU 처리)**:
```
Worker 1: GPU 추론 요청 → 대기 → 처리 완료
Worker 2: GPU 추론 요청 → 대기 → 처리 완료
Worker 3: GPU 추론 요청 → 대기 → 처리 완료
```

**배치 처리 (이론적)**:
```
모든 Worker: GPU 추론 요청 수집
→ 배치로 묶어서 한 번에 처리
→ 결과 분배
```

### 결론

- **Worker 레벨**: 병렬 처리됨 (각 Worker가 독립적으로 실행)
- **GPU 레벨**: 순차 처리됨 (각 Worker가 순차적으로 GPU 사용)
- **자동 배치 처리 아님**: 각 Worker가 독립적으로 `upscale()` 호출
- **개선 가능**: 배치 처리 구현 시 GPU 활용도 향상 가능하나, Real-ESRGAN은 기본적으로 단일 이미지 처리용

---

## 배치 처리 해결책 (GitHub 검색 결과)

### 현재 Real-ESRGAN의 배치 처리 지원 상태

**공식 구현** (`inference_realesrgan.py`):
- 폴더 단위 배치 처리 지원 (여러 이미지를 순차적으로 처리)
- `RealESRGANer.enhance()` 메서드는 **단일 이미지만** 받음 (numpy array)
- 내부적으로는 torch tensor 사용 (`img.unsqueeze(0)`으로 배치 차원 추가)

**핵심 발견**:
- `RealESRGANer` 클래스는 단일 이미지 처리용으로 설계됨
- 하지만 내부 모델(`self.model`)은 PyTorch 모델이므로 **배치 처리 가능**
- `pre_process()`에서 `img.unsqueeze(0)`을 통해 배치 차원을 추가하고 있음

### 해결책 1: 수동 배치 처리 구현

**접근 방법**: 여러 이미지를 배치로 묶어서 모델에 직접 전달

```python
class BatchImageEnhancer:
    """배치 처리 지원 ImageEnhancer"""
    
    def __init__(self, model_path: str = None):
        self.enhancer = ImageEnhancer(model_path)
        self.model = self.enhancer.upscaler.model  # 내부 PyTorch 모델 접근
    
    def batch_upscale(self, images: List[np.ndarray]) -> List[np.ndarray]:
        """
        여러 이미지를 배치로 처리
        
        Args:
            images: numpy 배열 리스트
        
        Returns:
            업스케일링된 이미지 리스트
        """
        # 배치 텐서 생성
        batch_tensors = []
        for img in images:
            # 전처리 (RealESRGANer.pre_process 로직 참고)
            img_tensor = torch.from_numpy(np.transpose(img, (2, 0, 1))).float()
            img_tensor = img_tensor.unsqueeze(0).to(self.enhancer.device)
            batch_tensors.append(img_tensor)
        
        # 배치로 묶기
        batch = torch.cat(batch_tensors, dim=0)
        
        # 모델 추론
        with torch.no_grad():
            output_batch = self.model(batch)
        
        # 결과 분리 및 후처리
        results = []
        for i in range(len(images)):
            output_img = output_batch[i].cpu().numpy()
            # 후처리 (RealESRGANer.post_process 로직 참고)
            results.append(output_img)
        
        return results
```

**장점**:
- GPU 활용도 향상 (배치 크기만큼 병렬 처리)
- 처리 시간 단축

**단점**:
- 구현 복잡도 증가
- 배치 크기 제한 (GPU 메모리에 따라)
- 이미지 크기가 다를 경우 패딩 필요

### 해결책 2: 큐 기반 배치 수집

**접근 방법**: 여러 Worker의 요청을 큐에 모아서 배치로 처리

```python
import queue
import threading
from collections import deque

class BatchEnhancementQueue:
    """배치 처리를 위한 큐 시스템"""
    
    def __init__(self, batch_size: int = 4, timeout: float = 0.1):
        self.batch_size = batch_size
        self.timeout = timeout
        self.queue = queue.Queue()
        self.enhancer = ImageEnhancer()
        self.lock = threading.Lock()
    
    async def enhance_batch(self, image_path: str) -> str:
        """이미지를 큐에 추가하고 배치 처리 결과 반환"""
        future = asyncio.Future()
        self.queue.put((image_path, future))
        
        # 배치 처리 트리거
        if self.queue.qsize() >= self.batch_size:
            await self._process_batch()
        
        return await future
    
    async def _process_batch(self):
        """큐에서 배치를 꺼내서 처리"""
        batch = []
        futures = []
        
        # 배치 수집
        while len(batch) < self.batch_size and not self.queue.empty():
            item = self.queue.get_nowait()
            batch.append(item[0])
            futures.append(item[1])
        
        # 배치 처리
        results = await asyncio.to_thread(self._enhance_batch_sync, batch)
        
        # 결과 반환
        for future, result in zip(futures, results):
            future.set_result(result)
```

**장점**:
- 자동 배치 수집
- GPU 활용도 향상
- 기존 코드와 호환 가능

**단점**:
- 구현 복잡도 높음
- 타임아웃 처리 필요
- 동기화 오버헤드

### 해결책 3: 공식 스크립트 활용 (폴더 단위)

**접근 방법**: `inference_realesrgan.py` 스타일의 폴더 단위 처리

```python
# 여러 이미지를 임시 폴더에 모아서
# inference_realesrgan.py를 서브프로세스로 실행
import subprocess

def batch_enhance_folder(input_folder: str, output_folder: str):
    subprocess.run([
        'python', 'inference_realesrgan.py',
        '-i', input_folder,
        '-o', output_folder,
        '-n', 'RealESRGAN_x4plus',
        '--tile', '0'
    ])
```

**장점**:
- 구현 간단
- 공식 스크립트 활용

**단점**:
- 파일 I/O 오버헤드
- 프로세스 생성 비용
- 현재 아키텍처와 통합 어려움

### 해결책 4: Tile 기반 최적화 (현재 지원됨)

**접근 방법**: `RealESRGANer`의 `tile` 옵션 활용

```python
# 큰 이미지를 타일로 나눠서 처리
upsampler = RealESRGANer(
    scale=4,
    model_path=model_path,
    tile=512,  # 타일 크기 설정
    tile_pad=10
)
```

**장점**:
- 이미 구현되어 있음
- GPU 메모리 효율적
- 큰 이미지 처리 가능

**단점**:
- 배치 처리는 아님 (단일 이미지 내 타일링)
- 타일 경계 처리 필요

### 권장 해결책

**현재 프로젝트에 가장 적합한 방법**:

1. **단기**: 현재 구조 유지 + 캐싱 활용
   - 캐싱 메커니즘으로 중복 처리 방지
   - Worker 병렬 처리로 전체 시간 단축

2. **중기**: 큐 기반 배치 수집 구현
   - 여러 Worker 요청을 모아서 배치 처리
   - GPU 활용도 향상

3. **장기**: 배치 처리 전용 클래스 구현
   - `BatchImageEnhancer` 클래스 추가
   - 동일 크기 이미지에 대해 배치 처리

### 참고 자료

- **공식 저장소**: https://github.com/xinntao/Real-ESRGAN
- **inference_realesrgan.py**: 폴더 단위 배치 처리 예제
- **realesrgan/utils.py**: RealESRGANer 클래스 구현
- **타일 처리**: `tile_process()` 메서드로 큰 이미지 처리

---

## 기존 해결 방법 분석

### 현재 코드 상태

**확인된 사실**:
1. **ONNX 전처리**: `_preprocess_onnx()`에서 `np.expand_dims(img_chw, axis=0)`로 배치 차원 추가 (202번 라인)
2. **동시성 제어**: `_onnx_inference_lock`으로 ONNX 추론 시 동시성 제어 (565-567번 라인)
3. **배치 처리 미구현**: 실제로 여러 이미지를 배치로 묶어서 처리하는 코드는 없음

**현재 구조**:
```python
# enhancement.py:202
img_batch = np.expand_dims(img_chw, axis=0)  # 단일 이미지에 배치 차원만 추가

# enhancement.py:565-567
with _onnx_inference_lock:
    output_tensor = self.upscaler.run(None, {input_name: input_tensor})[0]
```

### 기존에 시도했을 수 있는 방법

**가능성 1: ONNX 모델의 배치 입력 지원**
- ONNX 모델이 `[batch, channels, height, width]` 형태의 입력을 받도록 설계됨
- 하지만 현재는 항상 `batch=1`로 처리됨
- **해결책**: 여러 이미지를 `np.concatenate()`로 묶어서 배치 크기 > 1로 처리

**가능성 2: Threading Lock을 통한 순차 처리**
- `_onnx_inference_lock`으로 동시 추론 방지
- 이는 배치 처리가 아니라 **동시성 제어**용
- 여러 Worker가 동시에 GPU를 사용하는 것을 방지

**가능성 3: Shared Model 인스턴스**
- `_shared_upscaler`로 모델을 공유하여 메모리 효율성 향상
- 하지만 이는 배치 처리가 아니라 **모델 재사용** 최적화

### 결론

**현재 상태**: 배치 처리는 구현되어 있지 않음
- 각 Worker가 독립적으로 단일 이미지를 처리
- `_onnx_inference_lock`은 동시성 제어용이지 배치 처리용이 아님
- ONNX 모델은 배치 입력을 지원하지만, 현재는 항상 `batch=1`로 사용됨

**개선 방향**: 위의 "해결책 2: 큐 기반 배치 수집"을 구현하면 GPU 활용도를 향상시킬 수 있음
