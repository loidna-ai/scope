# 프로젝트 전체 워크플로우

## 개요
이 프로젝트는 **전기적 특이점(단락흔) 사진 분석을 위한 2단계 파이프라인**으로 구성되어 있습니다:
1. **이미지 전처리 파이프라인** (LangGraph StateGraph)
2. **화재조사 멀티 에이전트 분석 파이프라인** (LangGraph StateGraph)

---

## 1단계: 이미지 전처리 파이프라인

### 워크플로우 구조
```
START → load → crop → enhance → [filter, metrics] (병렬) → packaging → END
```

### 상세 단계별 설명

#### 1. **load** 노드 (`src/nodes/load.py`)
- **입력**: `input_image_path` (이미지 파일 경로)
- **처리**: 한글 경로 지원 이미지 로드 (`load_image_safe()`)
- **출력**: `original_image` (원본 이미지, numpy.ndarray)
- **기능**: cv2.imread 대신 np.fromfile + cv2.imdecode 패턴 사용

#### 2. **crop** 노드 (`src/nodes/crop.py`)
- **입력**: `original_image`
- **처리**: 
  - Morphological Gradient로 단락흔 영역 탐지
  - 가장 큰 Contour 찾기
  - 패딩 추가 후 크롭
- **출력**: `cropped_image` (크롭된 이미지)
- **알고리즘**: 
  - Morphological Gradient → 이진화 → Dilation → Largest Contour

#### 3. **enhance** 노드 (`src/nodes/enhancement.py`)
- **입력**: `cropped_image`
- **처리**: Real-ESRGAN으로 4x 초해상도 확대
- **출력**: `enhanced_image` (4배 확대된 고화질 이미지)
- **검증**: 출력 크기 = 입력 크기 × 4 확인 (SR_SCALE 검증)

#### 4. **filter** 노드 (`src/nodes/filter.py`) - 병렬 실행
- **입력**: `enhanced_image`
- **처리**: CLAHE (Contrast Limited Adaptive Histogram Equalization) 필터 적용
- **출력**: `filtered_image` (텍스처 강조된 이미지)
- **목적**: 대비 및 텍스처 강조로 미세한 결함 탐지

#### 5. **metrics** 노드 (`src/nodes/metrics.py`) - 병렬 실행
- **입력**: `enhanced_image`
- **처리**: 
  - 그레이스케일 변환 → 이진화
  - scikit-image로 형태학적 분석
  - 원형도(Circularity), 고형도(Solidity), 면적(Area) 추출
- **출력**: 
  - `binary_mask` (이진화된 마스크)
  - `metrics` (형태학적 메트릭스 딕셔너리)

#### 6. **packaging** 노드 (`src/nodes/packaging.py`)
- **입력**: `enhanced_image`, `filtered_image`, `metrics`, `binary_mask`
- **처리**: 
  - 모든 데이터를 JSON 형식으로 구조화
  - Base64 인코딩된 이미지 데이터 생성
  - 비교 분석 데이터 계산 (밝기 변화, 픽셀 차이 등)
- **출력**: `analysis_data` (LLM 분석용 JSON 데이터)

### 상태 관리 (GraphState)
```python
GraphState {
    input_image_path: str
    original_image: Optional[np.ndarray]
    cropped_image: Optional[np.ndarray]
    enhanced_image: Optional[np.ndarray]
    filtered_image: Optional[np.ndarray]
    binary_mask: Optional[np.ndarray]
    metrics: Optional[dict]
    analysis_data: Optional[dict]
    errors: Annotated[list[str], operator.add]
}
```

### 실행 파일
- **`main.py`**: 기본 이미지 처리 파이프라인 실행
  - 그래프 실행 후 `outputs/{input_filename}/` 디렉토리에 저장
  - `llm_gemini_format.json`: Gemini API 형식으로 변환된 데이터
  - `full_pipeline.png`: 전체 파이프라인 시각화 (1x5 레이아웃)

---

## 2단계: 화재조사 멀티 에이전트 분석 파이프라인

### 워크플로우 구조
```
START → [tracking, short_circuit, severed, contact, overcurrent] (병렬) 
     → chief_investigator → END
```

### 상세 단계별 설명

#### 1. **전문가 노드들** (병렬 실행)
5명의 전문가가 동시에 분석을 수행합니다:

- **tracking** (`node_tracking`): 화재 추적 전문가
  - 화재 시작점 추정
  - 화재 확산 방향 및 경로 분석
  - 연소 패턴 분석

- **short_circuit** (`node_short_circuit`): 단락 전문가
  - 단락 흔적의 형태학적 특성 분석
  - 단락 발생 가능성 평가
  - 단락 원인 추정 (과부하, 절연 파괴, 이물질 등)

- **severed** (`node_severed`): 절단 전문가
  - 전선 절단 흔적 분석
  - 절단 원인 추정 (기계적 손상, 화재 등)

- **contact** (`node_contact`): 접촉 전문가
  - 접촉 불량 흔적 분석
  - 접촉부 과열 원인 분석

- **overcurrent** (`node_overcurrent`): 과전류 전문가
  - 과전류 흔적 분석
  - 과부하 원인 추정

#### 2. **chief_investigator** 노드 (`node_chief_investigator`)
- **입력**: 모든 전문가 리포트 (`expert_reports`)
- **처리**: 
  - 5명의 전문가 리포트를 종합 분석
  - 최종 결론 도출
- **출력**: `final_verdict` (최종 분석 결과)

### 상태 관리 (InvestigationState)
```python
InvestigationState {
    payload: List[Any]  # LLM 입력 데이터 (이미지 + 텍스트)
    expert_reports: Annotated[List[str], operator.add]  # 전문가 리포트 수집
    final_verdict: Optional[str]  # 최종 결론
    errors: Annotated[List[str], operator.add]
}
```

### 실행 파일
- **`fire_investigation_main.py`**: 전체 파이프라인 실행
  1. 이미지 전처리 파이프라인 실행 (`build_graph()`)
  2. Format 2 형식으로 변환 (`to_gemini_vertex_ai_format()`)
  3. 멀티 에이전트 분석 실행 (`analyze_fire_evidence()`)
  4. 최종 결과 출력 및 저장

---

## 데이터 흐름

### Format 2 변환 (`to_gemini_vertex_ai_format()`)
`analysis_data`를 Vertex AI Gemini API 형식으로 변환:
```python
[
    "텍스트 설명 (순수 데이터만, 지시문 없음)",
    {"inline_data": {"mime_type": "image/png", "data": "base64..."}},  # enhanced
    {"inline_data": {"mime_type": "image/png", "data": "base64..."}},  # filtered
    {"inline_data": {"mime_type": "image/png", "data": "base64..."}}   # mask
]
```

### 저장 위치
```
outputs/
└── {input_filename}/
    ├── llm_gemini_format.json  # Gemini API 형식 데이터
    └── full_pipeline.png        # 파이프라인 시각화
```

---

## 기술 스택

### 핵심 라이브러리
- **LangGraph**: 워크플로우 오케스트레이션
- **Real-ESRGAN**: 초해상도 이미지 복원
- **OpenCV**: 이미지 처리
- **scikit-image**: 형태학적 분석
- **LangChain + Gemini**: 멀티 에이전트 분석

### 설정 파일
- **`config.py`**: 모든 상수 및 임계값 관리
  - SR_SCALE, MODEL_PATH
  - CLAHE 설정
  - 크롭 설정
  - 형태학적 처리 설정

---

## 실행 방법

### 1. 이미지 전처리만 실행
```bash
python main.py [이미지_경로]
# 또는 대화형 모드
python main.py
```

### 2. 전체 파이프라인 실행 (전처리 + 멀티 에이전트 분석)
```bash
python fire_investigation_main.py [이미지_경로]
# 또는 대화형 모드
python fire_investigation_main.py
```

