# 핫스팟 디텍터 구조 및 워크플로우 상세 문서

## 목차
1. [개요](#개요)
2. [시스템 아키텍처](#시스템-아키텍처)
3. [핵심 컴포넌트 상세](#핵심-컴포넌트-상세)
4. [워크플로우 단계별 상세](#워크플로우-단계별-상세)
5. [데이터 모델](#데이터-모델)
6. [설정 및 파라미터](#설정-및-파라미터)
7. [에러 처리 및 예외 상황](#에러-처리-및-예외-상황)
8. [성능 최적화 전략](#성능-최적화-전략)
9. [통합 및 의존성](#통합-및-의존성)

---

## 개요

### 목적
핫스팟 디텍터(Hotspot Detector)는 화재 조사 이미지에서 이상 징후(Hotspot)를 탐지하는 핵심 컴포넌트입니다. Overlap Grid Strategy를 사용하여 대형 이미지를 고해상도 패치로 분할하고, 각 패치를 병렬로 분석하여 전체 이미지에서 손상 영역을 식별합니다.

### 주요 특징
- **Overlap Grid Strategy**: 이미지를 겹치는 패치로 분할하여 경계 영역 손실 방지
- **병렬 처리**: asyncio 기반 비동기 API 호출로 처리 속도 최적화
- **NMS 중복 제거**: Non-Maximum Suppression으로 겹치는 탐지 결과 병합
- **전역 Rate Limiting**: 모든 API 호출에 대한 통합 제어로 429/503 에러 방지
- **좌표 정규화**: 패치 로컬 좌표를 전역 이미지 좌표로 자동 변환

### 파일 위치
- **메인 구현**: `src/nodes/common_nodes.py` - `hotspot_detector_node()` 함수
- **데이터 모델**: `src/models/hotspot_models.py` - Pydantic 모델 정의
- **이미지 처리**: `src/utils/image_processing.py` - 슬라이싱 및 좌표 변환
- **NMS 알고리즘**: `src/utils/nms.py` - 중복 제거 로직
- **프롬프트**: `src/prompts/common_prompts.py` - `get_micro_evidence_prompt()`
- **Rate Limiting**: `src/utils/api_concurrency.py` - 전역 동시성 제어

---

## 시스템 아키텍처

### 전체 그래프 구조
```
START
  ↓
hotspot_detector (공통 노드)
  ↓
  ├─→ contact (Contact Expert)
  ├─→ deform (Deform Expert)
  └─→ necking (Necking Expert)
      ↓
    arbiter (최종 판정)
      ↓
    visualizer (시각화)
      ↓
    END
```

### 핫스팟 디텍터 내부 구조
```
hotspot_detector_node (Sync Wrapper)
  │
  ├─→ Event Loop 체크
  │   ├─→ 이미 실행 중인 루프? → 별도 스레드에서 실행
  │   └─→ 루프 없음? → asyncio.run()으로 실행
  │
  └─→ _async_detector_logic() (Async Core)
      │
      ├─→ 1. 이미지 경로 확인 및 준비
      │   ├─→ state.image_path 우선 사용
      │   └─→ 없으면 payload에서 추출 → 임시 파일 저장
      │
      ├─→ 2. 이미지 슬라이싱 (Overlap Grid)
      │   ├─→ slice_image() 호출
      │   ├─→ 패치 크기: config.HOTSPOT_PATCH_SIZE (기본 1024px)
      │   ├─→ 오버랩: config.HOTSPOT_OVERLAP (기본 200px)
      │   └─→ 패치 리스트 생성 (image_bytes, offset, size, index)
      │
      ├─→ 3. 병렬 API 호출
      │   ├─→ 각 패치에 대해 _process_patch() 태스크 생성
      │   ├─→ asyncio.gather()로 병렬 실행
      │   ├─→ async_retry_with_backoff()로 재시도 및 Rate Limit 적용
      │   └─→ Gemini API 호출 (JSON Schema 기반 구조화 출력)
      │
      ├─→ 4. 결과 집계 및 좌표 변환
      │   ├─→ 각 패치 결과의 좌표를 전역 좌표로 변환
      │   ├─→ map_box_to_global() 사용
      │   └─→ raw_hotspots 리스트 생성
      │
      ├─→ 5. NMS 중복 제거
      │   ├─→ non_max_suppression() 호출
      │   ├─→ IoU 임계값: config.HOTSPOT_NMS_IOU_THRESHOLD (기본 0.3)
      │   ├─→ 심각도 점수 기준 정렬
      │   └─→ 겹치는 Hotspot 병합 (visual_evidence 통합)
      │
      └─→ 6. 결과 반환
          ├─→ hotspots: 최종 Hotspot 리스트
          ├─→ corrected_total_count: 실제 개수
          ├─→ analysis_status: 상태 플래그
          └─→ image_path: State 업데이트용 경로
```

---

## 핵심 컴포넌트 상세

### 1. hotspot_detector_node() - 메인 진입점

**위치**: `src/nodes/common_nodes.py:61`

**시그니처**:
```python
def hotspot_detector_node(state: InvestigationState) -> Dict[str, Any]
```

**역할**:
- LangGraph 호환 동기 래퍼 함수
- 이벤트 루프 충돌 방지 (이미 실행 중인 루프 감지)
- 비동기 로직을 별도 스레드에서 실행 (필요 시)

**이벤트 루프 처리 전략**:
1. 현재 이벤트 루프 확인 (`asyncio.get_event_loop()`)
2. 루프가 실행 중이면:
   - 별도 스레드 생성
   - 새 이벤트 루프 생성 (`asyncio.new_event_loop()`)
   - 타임아웃 설정 (`config.HOTSPOT_THREAD_JOIN_TIMEOUT`, 기본 600초)
3. 루프가 없으면:
   - `asyncio.run()`으로 직접 실행

**반환값**:
```python
{
    "hotspots": List[Dict[str, Any]],  # 최종 Hotspot 리스트
    "corrected_total_count": int,      # 실제 탐지 개수
    "analysis_status": str,            # "DETECTED" | "NO_HOTSPOTS_DETECTED" | "ERROR"
    "image_path": str,                 # State 업데이트용 이미지 경로
    "errors": List[str]                # 에러 메시지 (에러 발생 시)
}
```

### 2. _async_detector_logic() - 비동기 핵심 로직

**위치**: `src/nodes/common_nodes.py:72`

**주요 단계**:

#### 2.1 이미지 경로 준비
```python
# 우선순위: state.image_path > payload에서 추출
if image_path and os.path.exists(image_path):
    temp_image_path = image_path  # 기존 경로 사용
else:
    # payload에서 이미지 추출
    image_data = extract_image_from_payload(payload)
    temp_image_path = save_bytes_to_temp_file(image_data)
```

**메모리 최적화**:
- Payload의 바이너리 데이터 대신 파일 경로만 State에 저장
- 임시 파일은 후속 노드에서 재사용되므로 즉시 삭제하지 않음
- 파일 정리는 전체 파이프라인 완료 후 `main.py`에서 처리

#### 2.2 이미지 슬라이싱
```python
patches = await asyncio.to_thread(
    slice_image, 
    temp_image_path, 
    patch_size=config.HOTSPOT_PATCH_SIZE,    # 기본 1024px
    overlap=config.HOTSPOT_OVERLAP            # 기본 200px
)
```

**슬라이싱 알고리즘** (`slice_image()` 함수):
1. 이미지 로드 및 RGB 변환
2. Stride 계산: `stride = patch_size - overlap`
3. X/Y 좌표 생성:
   - `get_starts()` 함수로 시작 좌표 리스트 생성
   - 마지막 패치는 이미지 끝에 강제 배치 (경계 손실 방지)
4. 각 좌표에서 패치 크롭
5. 최소 크기 검증 (`min_patch_size`, 기본 512px)
6. JPEG로 인코딩 (품질 95%)

**패치 데이터 구조**:
```python
{
    "image_bytes": bytes,           # JPEG 인코딩된 이미지 바이트
    "offset": (x, y),               # 원본 이미지에서의 좌상단 좌표 (픽셀)
    "size": (width, height),        # 패치 크기 (픽셀)
    "index": (row_idx, col_idx)     # 그리드 인덱스
}
```

#### 2.3 병렬 API 호출

**프롬프트 설정**:
- `get_micro_evidence_prompt()` 사용
- 패치 단위 미세 증거 탐지에 특화
- Hallucination 방지용 네거티브 프롬프트 포함

**API 설정**:
```python
api_config = {
    "response_mime_type": "application/json",
    "response_json_schema": HotspotDetectionResult.model_json_schema(),
    "safety_settings": [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ],
}
```

**패치 처리 함수** (`_process_patch()`):
```python
async def _process_patch(patch_data):
    # 1. 이미지 Part 생성
    image_part = types.Part.from_bytes(
        data=patch_data['image_bytes'],
        mime_type="image/jpeg"
    )
    
    # 2. API 호출 (재시도 및 Rate Limit 포함)
    async def _call_api(**kwargs):
        resp = await client.aio.models.generate_content(
            model=kwargs.get("model_name", model_name),
            contents=[prompt, image_part],
            config=api_config
        )
        return resp
    
    response = await async_retry_with_backoff(
        _call_api,
        max_retries=3,
        context_name=f"Patch {patch_idx}",
        model_name=model_name
    )
    
    # 3. 응답 파싱
    # - Safety block 체크
    # - JSON 파싱 및 Pydantic 검증
    # - Hotspot 리스트 추출
    
    # 4. 통계 업데이트
    # - success/failed/safety_blocked 카운트
    
    await asyncio.sleep(config.API_CALL_DELAY)  # Traffic smoothing
    return hotspots
```

**병렬 실행**:
```python
tasks = [_process_patch(p) for p in patches]
patch_results_list = await asyncio.gather(*tasks)
```

**Rate Limiting**:
- `async_retry_with_backoff()` 내부에서 `acquire_api_slot()` 호출
- 전역 `AsyncLimiter` (RPM 제한) + `threading.Semaphore` (동시성 제한)
- 설정값:
  - `GEMINI_TIER1_RPM`: 30 (분당 요청 제한)
  - `GEMINI_TIER1_CONCURRENT`: 2 (동시 실행 제한)
  - `API_CALL_DELAY`: 2.0초 (패치 간 대기 시간)

#### 2.4 좌표 변환 (Local → Global)

**변환 과정**:
```python
for i, patch_hotspots in enumerate(patch_results_list):
    patch_info = patches[i]
    offset = patch_info['offset']      # (x, y) 픽셀 좌표
    p_size = patch_info['size']        # (width, height) 픽셀
    original_size = get_image_size(temp_image_path)  # (width, height) 픽셀
    
    for h in patch_hotspots:
        # Pydantic 모델을 Dict로 변환
        h_dict = h.model_dump(mode='json')
        
        # 좌표 변환: 패치 정규화 좌표(0-1000) → 전역 정규화 좌표(0-1000)
        global_box = map_box_to_global(
            h_dict['box_2d'],      # {ymin, xmin, ymax, xmax} (0-1000, 패치 기준)
            offset,                # 패치의 원본 이미지에서의 오프셋
            p_size,                # 패치 크기
            original_size          # 원본 이미지 크기
        )
        
        h_dict['box_2d'] = global_box
        h_dict['id'] = global_hotspot_id  # 임시 ID
        h_dict['_origin_patch'] = patch_info['index']  # 디버깅용
        
        raw_hotspots.append(h_dict)
        global_hotspot_id += 1
```

**좌표 변환 알고리즘** (`map_box_to_global()`):
1. **De-normalize**: 패치 정규화 좌표(0-1000) → 패치 픽셀 좌표
   ```
   py_min = ymin / 1000 * patch_height
   px_min = xmin / 1000 * patch_width
   ```
2. **Add Offset**: 패치 픽셀 좌표 → 전역 픽셀 좌표
   ```
   gx_min = px_min + offset_x
   gy_min = py_min + offset_y
   ```
3. **Clip to Bounds**: 이미지 경계 내로 클리핑
4. **Re-normalize**: 전역 픽셀 좌표 → 전역 정규화 좌표(0-1000)
   ```
   global_ymin = int(gy_min / original_height * 1000)
   global_xmin = int(gx_min / original_width * 1000)
   ```

#### 2.5 NMS 중복 제거

**알고리즘** (`non_max_suppression()`):
1. **정렬**: 심각도 점수(`severity_score`) 기준 내림차순 정렬
2. **반복 처리**:
   - 가장 높은 점수의 Hotspot 선택
   - 나머지 Hotspot과 IoU 계산
   - IoU >= 임계값이면 제거 (중복)
   - 제거 시 `visual_evidence` 통합
3. **반환**: 최종 선택된 Hotspot 리스트

**IoU 계산** (`calculate_iou()`):
```python
# 교집합 영역 계산
x_left = max(box1["xmin"], box2["xmin"])
y_top = max(box1["ymin"], box2["ymin"])
x_right = min(box1["xmax"], box2["xmax"])
y_bottom = min(box1["ymax"], box2["ymax"])

intersection_area = (x_right - x_left) * (y_bottom - y_top)

# 합집합 영역 계산
area1 = (box1["xmax"] - box1["xmin"]) * (box1["ymax"] - box1["ymin"])
area2 = (box2["xmax"] - box2["xmin"]) * (box2["ymax"] - box2["ymin"])
union_area = area1 + area2 - intersection_area

iou = intersection_area / union_area
```

**설정값**:
- `HOTSPOT_NMS_IOU_THRESHOLD`: 0.3 (기본값)
  - 값이 작을수록: 더 많은 Hotspot 유지 (중복 허용)
  - 값이 클수록: 더 적은 Hotspot 유지 (엄격한 중복 제거)

**Evidence 통합**:
- 제거되는 Hotspot의 `visual_evidence`를 유지되는 Hotspot에 병합
- 형식: `"{current_evidence} | {merged_evidence}"`

#### 2.6 ID 재번호화 및 정리

```python
# NMS 후 ID 재번호화 (1부터 시작)
for idx, h in enumerate(final_hotspots, 1):
    h['id'] = idx
    h.pop('_origin_patch', None)  # 디버깅 필드 제거
```

---

## 워크플로우 단계별 상세

### Phase 1: 초기화 및 준비

**입력**:
- `state: InvestigationState`
  - `image_path: Optional[str]` (우선 사용)
  - `payload: List[Any]` (Fallback)

**처리**:
1. Gemini API 클라이언트 획득 (`get_genai_client()`)
   - Vertex AI 또는 Google AI Studio 자동 선택
   - 인증 실패 시 에러 반환
2. 이미지 경로 확인
   - `state.image_path` 존재 및 유효성 확인
   - 없으면 `payload`에서 이미지 추출
   - 임시 파일로 저장 (후속 노드 재사용)

**출력**:
- `temp_image_path: str` (이미지 파일 경로)

### Phase 2: 이미지 슬라이싱

**입력**:
- `temp_image_path: str`
- `patch_size: int` (기본 1024px)
- `overlap: int` (기본 200px)

**처리**:
1. 이미지 로드 및 RGB 변환
2. Stride 계산: `stride = patch_size - overlap` (기본 824px)
3. X/Y 좌표 생성:
   ```
   x_coords = [0, 824, 1648, ...]  # stride 간격으로 시작 좌표 생성
   y_coords = [0, 824, 1648, ...]
   # 마지막 패치는 이미지 끝에 강제 배치
   ```
4. 각 좌표에서 패치 크롭
5. 최소 크기 검증 (512px 미만 패치 제외)
6. JPEG 인코딩 (품질 95%)

**출력**:
- `patches: List[Dict]` (패치 리스트)
  - 각 패치: `image_bytes`, `offset`, `size`, `index`

**예시**:
- 이미지 크기: 3000x2000px
- 패치 크기: 1024px
- 오버랩: 200px
- Stride: 824px
- X 패치 수: ceil((3000-1024)/824) + 1 = 4개
- Y 패치 수: ceil((2000-1024)/824) + 1 = 3개
- 총 패치 수: 4 × 3 = 12개

### Phase 3: 병렬 API 호출

**입력**:
- `patches: List[Dict]`
- `prompt: str` (프롬프트)
- `api_config: Dict` (API 설정)

**처리**:
1. 각 패치에 대해 `_process_patch()` 태스크 생성
2. `asyncio.gather()`로 병렬 실행
3. 각 태스크 내부:
   - `async_retry_with_backoff()` 호출
     - 전역 Rate Limiter 적용 (`acquire_api_slot()`)
     - 최대 3회 재시도
     - 지수 백오프 (503 에러 시 40s, 80s, 160s)
   - Gemini API 호출
   - 응답 파싱 및 검증
   - Safety block 체크
   - 통계 업데이트
   - `API_CALL_DELAY` 대기 (Traffic smoothing)

**출력**:
- `patch_results_list: List[List[Hotspot]]` (각 패치별 Hotspot 리스트)
- `patch_stats: Dict` (성공/실패/차단 통계)

**통계 예시**:
```
Patch stats — total: 12, success: 11, failed: 0, safety_blocked: 1 (success rate: 91.7%)
```

### Phase 4: 결과 집계 및 좌표 변환

**입력**:
- `patch_results_list: List[List[Hotspot]]`
- `patches: List[Dict]` (패치 메타데이터)
- `original_size: Tuple[int, int]` (원본 이미지 크기)

**처리**:
1. 각 패치 결과 순회
2. 각 Hotspot의 좌표를 전역 좌표로 변환
3. 임시 ID 할당
4. 디버깅 필드 추가 (`_origin_patch`)

**출력**:
- `raw_hotspots: List[Dict]` (전역 좌표로 변환된 Hotspot 리스트)

**예시**:
- 패치 0 (offset: (0, 0), size: (1024, 1024))에서 탐지된 Hotspot
  - 로컬 좌표: `{ymin: 100, xmin: 200, ymax: 150, xmax: 250}` (0-1000 정규화)
  - 전역 좌표: `{ymin: 100, xmin: 200, ymax: 150, xmax: 250}` (동일, offset이 (0,0)이므로)

- 패치 1 (offset: (824, 0), size: (1024, 1024))에서 탐지된 Hotspot
  - 로컬 좌표: `{ymin: 50, xmin: 50, ymax: 100, xmax: 100}` (0-1000 정규화)
  - 전역 좌표: `{ymin: 50, xmin: 874, ymax: 100, xmax: 924}` (x 좌표에 824 추가)

### Phase 5: NMS 중복 제거

**입력**:
- `raw_hotspots: List[Dict]`
- `iou_threshold: float` (기본 0.3)

**처리**:
1. 심각도 점수 기준 정렬 (내림차순)
2. 반복:
   - 가장 높은 점수 선택
   - 나머지와 IoU 계산
   - IoU >= 0.3이면 제거 및 Evidence 통합
3. ID 재번호화 (1부터 시작)
4. 디버깅 필드 제거

**출력**:
- `final_hotspots: List[Dict]` (최종 Hotspot 리스트)

**예시**:
- Raw Hotspots: 15개
- NMS 후: 7개
- 제거된 Hotspot: 8개 (중복)

### Phase 6: 결과 반환

**입력**:
- `final_hotspots: List[Dict]`
- `temp_image_path: str`
- `image_path: Optional[str]` (기존 경로)

**처리**:
1. 결과 딕셔너리 생성
2. `image_path` 업데이트 (필요 시)
3. 상태 플래그 설정

**출력**:
```python
{
    "hotspots": final_hotspots,
    "corrected_total_count": len(final_hotspots),
    "analysis_status": "DETECTED" | "NO_HOTSPOTS_DETECTED" | "ERROR",
    "image_path": temp_image_path,
    "errors": []  # 에러 발생 시
}
```

---

## 데이터 모델

### BoundingBox2D

**위치**: `src/models/hotspot_models.py:9`

**정의**:
```python
class BoundingBox2D(BaseModel):
    ymin: int = Field(ge=0, le=1000, description="Y 최소값 (정규화)")
    xmin: int = Field(ge=0, le=1000, description="X 최소값 (정규화)")
    ymax: int = Field(ge=0, le=1000, description="Y 최대값 (정규화)")
    xmax: int = Field(ge=0, le=1000, description="X 최대값 (정규화)")
```

**검증**:
- 좌표 범위: 0-1000 (정규화 좌표)
- 논리 검증: `ymin < ymax`, `xmin < xmax`
- 하위 호환성: 배열 형식 `[ymin, xmin, ymax, xmax]`도 지원

### Hotspot

**위치**: `src/models/hotspot_models.py:40`

**정의**:
```python
class Hotspot(BaseModel):
    id: int = Field(ge=1, description="Hotspot 고유 ID")
    box_2d: BoundingBox2D = Field(description="2D Bounding Box (정규화 좌표 0-1000)")
    severity_score: int = Field(ge=0, le=100, description="심각도 점수 (0-100)")
    location_description: str = Field(description="위치 설명")
    visual_evidence: str = Field(description="시각적 증거 요약 (2-3문장)")
    reason_for_selection: Optional[str] = Field(default=None, description="선정 근거")
    suspected_feature: Optional[str] = Field(default=None, description="물리적 특징 묘사")
```

**심각도 점수 기준**:
- 0: 식별 불가
- 1-30: 경미 (표면 그을음, 미세 변색)
- 31-60: 중등 (형상 열 변형, 부분 소실)
- 61-80: 심각 (완전 소실, 심한 산화)
- 81-100: 치명적 (비드, 망울 등 용융 흔적 명확)

### HotspotDetectionResult

**위치**: `src/models/hotspot_models.py:74`

**정의**:
```python
class HotspotDetectionResult(BaseModel):
    hotspots: List[Hotspot] = Field(default_factory=list, description="탐지된 Hotspot 리스트")
    total_count: int = Field(ge=0, description="탐지된 총 Hotspot 개수")
    scene_overview: Optional[str] = Field(default=None, description="현장 전체 요약")
    detailed_observations: Optional[List[str]] = Field(default=None, description="객체별 묘사 리스트")
```

**JSON Schema**:
- Gemini API의 구조화 출력에 사용
- `response_json_schema`로 전달
- Pydantic 모델에서 자동 생성 (`model_json_schema()`)

---

## 설정 및 파라미터

### config.py 설정값

#### 슬라이싱 파라미터
```python
HOTSPOT_PATCH_SIZE = 1024       # 패치 크기 (px)
HOTSPOT_OVERLAP = 200            # 패치 간 오버랩 (px)
```

**영향**:
- 패치 크기가 클수록: 더 많은 컨텍스트, 더 적은 패치 수, 더 높은 API 비용
- 오버랩이 클수록: 경계 손실 감소, 더 많은 패치 수, 더 높은 API 비용

#### NMS 파라미터
```python
HOTSPOT_NMS_IOU_THRESHOLD = 0.3  # NMS IoU 임계값 (0.0~1.0)
```

**영향**:
- 값이 작을수록: 더 많은 Hotspot 유지 (중복 허용)
- 값이 클수록: 더 적은 Hotspot 유지 (엄격한 중복 제거)

#### Rate Limiting 파라미터
```python
API_CALL_DELAY = 2.0                    # 패치 간 대기 시간 (초)
GEMINI_TIER1_RPM = 30                   # 분당 요청 제한
GEMINI_TIER1_CONCURRENT = 2             # 동시 실행 제한
HOTSPOT_THREAD_JOIN_TIMEOUT = 600       # 스레드 타임아웃 (초)
```

**영향**:
- `API_CALL_DELAY`: Traffic smoothing으로 429 에러 방지
- `GEMINI_TIER1_RPM`: Preview 모델 안정성을 위해 30으로 하향 조정
- `GEMINI_TIER1_CONCURRENT`: 429 에러 방지를 위한 최적값

#### 모델 설정
```python
GEMINI_MODEL_NAME = "gemini-3-flash-preview"
GEMINI_FALLBACK_MODEL = "gemini-2.5-flash"
GEMINI_ENABLE_FALLBACK = True
GEMINI_FALLBACK_THRESHOLD = 2           # 연속 503 에러 2회 시 Fallback
```

**Fallback 전략**:
- 연속 503 에러 2회 발생 시 `gemini-2.5-flash`로 자동 전환
- Preview 모델의 제한적인 RPD 보호

---

## 에러 처리 및 예외 상황

### 에러 타입 및 처리

#### 1. 인증 실패
**발생 위치**: `get_genai_client()` 호출 시
**처리**:
```python
try:
    client = get_genai_client()
except ValueError as e:
    logger.error(f"Hotspot Detector: {e}")
    return {"hotspots": [], "errors": [str(e)]}
```

#### 2. 이미지 파일 없음
**발생 위치**: 이미지 경로 확인 시
**처리**:
```python
if not payload:
    error_msg = "Hotspot Detector: No payload and no image path available."
    return {"hotspots": [], "errors": [error_msg]}
```

#### 3. 슬라이싱 실패
**발생 위치**: `slice_image()` 호출 시
**처리**:
```python
if not patches:
    raise ValueError("Image slicing failed (no patches generated).")
```

#### 4. API 호출 실패
**발생 위치**: Gemini API 호출 시
**처리**:
- `async_retry_with_backoff()` 내부에서 재시도
- 최대 3회 재시도
- 지수 백오프 적용
- 모든 재시도 실패 시 예외 전파

**재시도 가능한 에러**:
- 503 (UNAVAILABLE, overloaded)
- 429 (RESOURCE_EXHAUSTED)
- SSL 에러 (10054, ECONNRESET)
- JSON 파싱 에러

#### 5. Safety Block
**발생 위치**: API 응답 처리 시
**처리**:
```python
is_safety_blocked = (
    hasattr(candidate, "safety_ratings") 
    and candidate.safety_ratings
    and any(r.probability in ["HIGH", "MEDIUM"] for r in candidate.safety_ratings)
)

if is_safety_blocked:
    logger.warning(f"Patch {patch_idx}: Safety block detected. Skipping.")
    patch_stats["safety_blocked"] += 1
```

#### 6. 스레드 타임아웃
**발생 위치**: 별도 스레드 실행 시
**처리**:
```python
thread.join(timeout=config.HOTSPOT_THREAD_JOIN_TIMEOUT)

if thread.is_alive():
    error_msg = f"Hotspot Detector: Thread timed out after {config.HOTSPOT_THREAD_JOIN_TIMEOUT}s."
    return {
        "hotspots": [], 
        "errors": [error_msg],
        "analysis_status": "ERROR",
    }
```

### 에러 통계 및 로깅

**패치 통계**:
```python
patch_stats = {
    "total": total_patches,
    "success": 0,
    "failed": 0,
    "safety_blocked": 0,
}
```

**로깅**:
- 성공률 50% 미만 시 경고 로그
- 각 패치별 상세 에러 로그
- 최종 결과 요약 로그

---

## 성능 최적화 전략

### 1. 메모리 최적화

**전략**:
- Payload의 바이너리 데이터 대신 파일 경로만 State에 저장
- 임시 파일 재사용 (후속 노드에서 사용)
- 파일 정리는 파이프라인 완료 후 일괄 처리

**효과**:
- State 크기 감소
- 메모리 사용량 감소

### 2. 병렬 처리 최적화

**전략**:
- `asyncio.gather()`로 모든 패치 병렬 처리
- 전역 Rate Limiter로 동시성 제어
- `API_CALL_DELAY`로 Traffic smoothing

**효과**:
- 처리 시간 단축 (순차 처리 대비)
- 429/503 에러 방지

### 3. Rate Limiting 최적화

**전략**:
- 전역 `AsyncLimiter` (RPM 제한)
- `threading.Semaphore` (동시성 제한)
- 지수 백오프 (재시도 시)

**효과**:
- API Rate Limit 준수
- 안정적인 API 호출

### 4. 좌표 변환 최적화

**전략**:
- 정규화 좌표 사용 (0-1000)
- 벡터화된 변환 연산
- 경계 클리핑 최소화

**효과**:
- 계산 속도 향상
- 메모리 사용량 감소

### 5. NMS 최적화

**전략**:
- 심각도 점수 기준 정렬 (한 번만)
- IoU 계산 최적화
- Evidence 통합 최소화

**효과**:
- 중복 제거 속도 향상
- 메모리 사용량 감소

---

## 통합 및 의존성

### LangGraph 통합

**State 업데이트**:
```python
# InvestigationState에 업데이트되는 필드
{
    "hotspots": List[Dict[str, Any]],      # 최종 Hotspot 리스트
    "corrected_total_count": int,          # 실제 탐지 개수
    "analysis_status": str,                # 상태 플래그
    "image_path": str,                     # 이미지 경로 (업데이트)
}
```

**Reducer 함수**:
- `hotspots`: `keep_last` (마지막 값만 유지)
- `corrected_total_count`: `keep_last`
- `analysis_status`: `keep_last`
- `image_path`: `keep_last`

### 후속 노드 연동

**전문가 노드들**:
- Contact Expert
- Deform Expert
- Necking Expert

**입력**:
- `state.hotspots`: 탐지된 Hotspot 리스트
- `state.image_path`: 이미지 경로

**처리**:
- 각 Hotspot에 대해 Map-Reduce 패턴으로 분석
- ROI 크롭 및 향상
- 전문가별 분석 수행

### 의존성 모듈

**필수 모듈**:
- `src.utils.genai_client`: Gemini API 클라이언트
- `src.utils.api_concurrency`: Rate Limiting
- `src.utils.image_processing`: 이미지 처리
- `src.utils.nms`: NMS 알고리즘
- `src.utils`: 재시도 로직
- `src.models.hotspot_models`: 데이터 모델
- `src.prompts.common_prompts`: 프롬프트
- `src.tools.experts.expert_utils`: 유틸리티 함수

**외부 라이브러리**:
- `asyncio`: 비동기 처리
- `threading`: 스레드 관리
- `PIL (Pillow)`: 이미지 처리
- `pydantic`: 데이터 검증
- `google.genai`: Gemini API

---

## 추가 고려사항

### 1. 프롬프트 최적화

**현재 프롬프트 특징**:
- 패치 단위 미세 증거 탐지에 특화
- Hallucination 방지용 네거티브 프롬프트
- 객관적 사실 중심

**개선 가능 영역**:
- 패치 크기에 따른 프롬프트 조정
- 이미지 해상도에 따른 프롬프트 조정

### 2. 슬라이싱 전략 개선

**현재 전략**:
- 고정 크기 패치 (1024px)
- 고정 오버랩 (200px)

**개선 가능 영역**:
- 이미지 크기에 따른 동적 패치 크기 조정
- 중요 영역 감지 후 집중 슬라이싱

### 3. NMS 알고리즘 개선

**현재 알고리즘**:
- IoU 기반 중복 제거
- 심각도 점수 기준 정렬

**개선 가능 영역**:
- Soft-NMS 적용
- 클러스터링 기반 그룹화

### 4. 모니터링 및 디버깅

**현재 로깅**:
- 패치별 상세 로그
- 통계 요약 로그

**개선 가능 영역**:
- 성능 메트릭 수집
- 시각화 도구 통합
- 디버깅 모드 추가

---

## 결론

핫스팟 디텍터는 Overlap Grid Strategy를 사용하여 대형 이미지를 효율적으로 분석하는 핵심 컴포넌트입니다. 병렬 처리, Rate Limiting, NMS 중복 제거 등의 최적화 전략을 통해 안정적이고 빠른 Hotspot 탐지를 제공합니다.

주요 강점:
- 확장 가능한 아키텍처
- 안정적인 에러 처리
- 효율적인 메모리 사용
- 정확한 좌표 변환

개선 가능 영역:
- 동적 패치 크기 조정
- 고급 NMS 알고리즘 적용
- 성능 모니터링 강화

---

**문서 작성일**: 2026-02-17
**버전**: 1.0
**작성자**: AI Assistant
