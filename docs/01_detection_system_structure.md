# 탐지 시스템 구조 상세 (Detection System Architecture)

프로젝트 기능을 기준으로 **화재 징후 탐지(Adaptive Hotspot Detection)** 시스템의 전체 구조를 정리합니다.

---

## 1. 개요

### 1.1 목적
- 화재 현장 이미지에서 **단락흔(용융 비드, 탄화, 금속 결손 등)** 가능성 영역을 찾아냄
- **Overlap Grid Slicing** 전략으로 고해상도 이미지를 패치 단위로 분할 후 병렬 분석
- **0~1000 정규화 좌표**로 해상도 독립적 분석 지원

### 1.2 지원 모드
| 모드 | 설명 | 처리 방식 |
|------|------|-----------|
| **Single** | 단일 이미지 | Grid Slicing → 패치별 Gemini 분석 |
| **Deep** | 동일 지점 다각도 | Identity Fusion으로 동일 객체 병합 |
| **Wide** | 다중 지점 | 이미지별 NMS 후 독립 Hotspot 관리 |

---

## 2. 전체 워크플로우

```
[입력] image_paths / payload
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  hotspot_detector_node (common_nodes.py)                         │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ 1. 이미지 로드 (image_paths[0] 또는 payload에서 추출)         ││
│  │ 2. slice_multiple_images() → Overlap Grid 패치 생성           ││
│  │ 3. batch_process_hotspots() → Gemini API 병렬 호출           ││
│  │ 4. map_hotspots_to_global() → 패치 좌표 → 전역 좌표 변환     ││
│  │ 5. perform_batch_nms() → 중복 Hotspot 제거                   ││
│  │ 6. run_identity_fusion() → 다중 뷰 객체 병합 (2장 이상 시)   ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
[출력] hotspots (UnifiedHotspot[]), image_path, analysis_status
    │
    ▼
preprocessor_node → preprocessed_hotspots (Crop + Enhance + Classify)
```

---

## 3. 5단계 상세 구조

### 3.1 단계 1: 이미지 슬라이싱 (Overlap Grid)

**파일**: `src/utils/image_processing.py`  
**함수**: `slice_image()`, `slice_multiple_images()`

| 항목 | 내용 |
|------|------|
| **전략** | Overlap Grid – 패치 간 겹침으로 경계 누락 방지 |
| **패치 크기** | `HOTSPOT_PATCH_SIZE` (1024px) |
| **오버랩** | `HOTSPOT_OVERLAP` (200px) → stride 824px |
| **다운스케일** | `max_dimension`(2048) 초과 시 자동 축소 |
| **필터링** | 블러(Laplacian < 50) / 빈 배경(Edge < 10) 패치 제거 |

**패치 구조** (dict):
```python
{
    "image_bytes": bytes,           # JPEG
    "offset": (x, y),               # 리사이즈 이미지 내 픽셀 오프셋
    "original_offset": (x, y),       # 원본 이미지 좌표 (scale_factor 반영)
    "size": (pw, ph),
    "original_size": (pw, ph),
    "index": (r_idx, c_idx),
    "scale_factor": float,
    "source_image_path": str,       # slice_multiple_images에서 추가
}
```

---

### 3.2 단계 2: 병렬 API 호출

**파일**: `src/utils/api_concurrency.py`  
**함수**: `batch_process_hotspots()`

| 항목 | 내용 |
|------|------|
| **배치 크기** | `HOTSPOT_BATCH_SIZE` (5) – 1회 호출당 패치 개수 |
| **모델** | `GEMINI_MODEL_NAME` (gemini-2.5-flash) |
| **동시성** | `acquire_api_slot("flash")` – Rate Limit + Semaphore |
| **반환** | `[(patches_chunk, hotspots), ...]` |

**프롬프트**: `get_micro_evidence_prompt()` – `common_prompts.py`  
- 패치 단위 미세 증거 탐지
- Step 1~4: 객체 스캔 → 형상 이탈 감지 → 검증 → 추출
- 출력: `HotspotDetectionResult` (JSON Schema)

---

### 3.3 단계 3: 좌표 전역 매핑

**파일**: `src/utils/image_processing.py`  
**함수**: `map_hotspots_to_global()`, `map_box_to_global()`

| 변환 | 설명 |
|------|------|
| **입력** | 패치 내 0~1000 정규화 좌표 (LLM 출력) |
| **출력** | 전체 이미지 기준 0~1000 정규화 좌표 |
| **공식** | `global_px = (norm/1000 * patch_size) + offset` → `norm_global = px / full_size * 1000` |

**image_index**: LLM이 여러 패치 중 어떤 패치에서 탐지했는지 지정 (1부터 시작).

---

### 3.4 단계 4: NMS 중복 제거

**파일**: `src/utils/nms.py`, `image_processing.perform_batch_nms()`

| 항목 | 내용 |
|------|------|
| **알고리즘** | IoU 기반 Non-Maximum Suppression |
| **임계값** | `HOTSPOT_NMS_IOU_THRESHOLD` (0.3) |
| **우선순위** | `severity_score` 내림차순 |
| **그룹** | `source_image_path`별로 NMS 수행 |

---

### 3.5 단계 5: Identity Fusion (다중 뷰 병합)

**파일**: `src/utils/identity_fusion.py`  
**함수**: `run_identity_fusion()`

| 조건 | 동작 |
|------|------|
| **이미지 1장** | `_fallback_to_mapping()` – 1:1 매핑 |
| **이미지 2장 이상** | Gemini Pro로 동일 객체 판별 후 병합 |

**출력**: `UnifiedHotspot` – `boxes: {image_path: BoundingBox2D}` 형태로 이미지별 좌표 보관.

---

## 4. 데이터 모델

### 4.1 Hotspot (패치 단위)

**파일**: `src/models/hotspot_models.py`

```python
class Hotspot(BaseModel):
    id: int
    image_index: int
    box_2d: BoundingBox2D
    severity_score: int
    location_description: str
    visual_evidence: str
```

### 4.2 UnifiedHotspot (전역)

```python
class UnifiedHotspot(BaseModel):
    id: int
    source_images: List[str]
    boxes: Dict[str, BoundingBox2D]
    severity_score: int
    location_description: str
    visual_evidence: str
    raw_hotspot_ids: List[int]
    roi_image_paths: Dict[str, str]
    component_type: Optional[str]
```

---

## 5. 설정 (config.py)

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `HOTSPOT_MAX_IMAGE_DIMENSION` | 2048 | 최대 이미지 해상도 |
| `HOTSPOT_PATCH_SIZE` | 1024 | 패치 크기 (px) |
| `HOTSPOT_OVERLAP` | 200 | 패치 간 오버랩 (px) |
| `HOTSPOT_NMS_IOU_THRESHOLD` | 0.3 | NMS IoU 임계값 |
| `HOTSPOT_BLUR_THRESHOLD` | 50.0 | 블러 패치 제거 기준 |
| `HOTSPOT_EDGE_THRESHOLD` | 10 | 빈 배경 패치 제거 기준 |
| `HOTSPOT_BATCH_SIZE` | 5 | 1회 API 호출당 패치 수 |
| `PRE_RESIZE_ENABLED` | True | 파이프라인 진입 전 리사이즈 |
| `PRE_RESIZE_MAX_DIMENSION` | 2048 | 최대 이미지 해상도 |

---

## 6. 파일 의존성

```
common_nodes.py (hotspot_detector_node)
├── image_processing.py
│   ├── slice_image
│   ├── slice_multiple_images
│   ├── map_hotspots_to_global
│   ├── map_box_to_global
│   ├── perform_batch_nms
│   └── get_image_size
├── api_concurrency.py (batch_process_hotspots)
├── identity_fusion.py (run_identity_fusion)
├── nms.py (perform_nms)
├── common_prompts.py (get_micro_evidence_prompt)
├── hotspot_models.py (HotspotDetectionResult)
└── expert_utils.py (extract_images_from_payload, save_bytes_to_temp_file)
```

---

## 7. State 흐름

| State 필드 | 설정 | 설명 |
|------------|------|------|
| `image_paths` | agent 초기화 | `process_payload_images()` 결과 |
| `image_path` | hotspot_detector | `primary_image_path` |
| `hotspots` | hotspot_detector | `UnifiedHotspot[]` |
| `corrected_total_count` | hotspot_detector | 최종 Hotspot 개수 |
| `analysis_status` | hotspot_detector | `DETECTED` / `NO_HOTSPOTS_DETECTED` / `ERROR` |

---

## 8. 하위 파이프라인 연결

```
hotspot_detector_node
    │
    ▼
preprocessor_node (Crop + Enhance + Classify)
    │
    ▼
[contact, necking] 전문가 병렬 (Map-Reduce)
    │
    ▼
arbiter_node → visualizer_node
```

탐지 결과(`hotspots`)는 후속 preprocessor에서 `TOP_N_HOTSPOTS`(5개)만 선택해 `preprocessed_hotspots`로 전달됩니다.
