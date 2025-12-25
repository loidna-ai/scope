# 화재조사 AI 멀티 에이전트 시스템 - 프로젝트 개요

## 목차
1. [프로젝트 개요](#프로젝트-개요)
2. [시스템 아키텍처](#시스템-아키텍처)
3. [워크플로우](#워크플로우)
4. [주요 컴포넌트](#주요-컴포넌트)
5. [기술 스택](#기술-스택)
6. [프로젝트 구조](#프로젝트-구조)
7. [실행 방법](#실행-방법)
8. [세부 사항](#세부-사항)

---

## 프로젝트 개요

### 목적
전기화재 조사에서 발견되는 단락흔(Arc Bead) 이미지를 분석하여 화재 원인을 자동으로 진단하는 AI 멀티 에이전트 시스템입니다.

### 핵심 기능
- **이미지 전처리 파이프라인**: 단락흔 영역 탐지, 초해상도 향상, 형태학적 분석
- **멀티 에이전트 분석**: 5명의 전문가가 병렬로 분석 수행
- **Arbiter Agent**: 전문가들의 분석 결과를 종합하여 최종 결론 도출
- **1차/2차 단락흔 판정**: 화재 원인(1차)과 결과(2차) 구분

### 주요 특징
- **LangGraph 기반**: 상태 기반 워크플로우 오케스트레이션
- **병렬 처리**: Fan-out/Fan-in 패턴으로 전문가 노드 병렬 실행
- **구조화된 분석**: 각 전문가가 다단계 순차 분석 수행
- **상충 해결 논리**: 전문가 간 상충되는 의견 자동 해결
- **증거 위계**: 형상학적 변형 > 화학적 성분 > 일반적 탄화

---

## 시스템 아키텍처

### 전체 구조

```
┌─────────────────────────────────────────────────────────┐
│                    main.py (진입점)                      │
└──────────────────────┬──────────────────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        │                             │
┌───────▼────────┐          ┌────────▼──────────┐
│ 이미지 전처리    │          │ 멀티 에이전트 분석  │
│   파이프라인     │          │     파이프라인      │
└───────┬────────┘          └────────┬──────────┘
        │                             │
        │  GraphState                 │  InvestigationState
        │                             │
┌───────▼─────────────────────────────▼──────────┐
│           LangGraph StateGraph                   │
│  (상태 기반 워크플로우 오케스트레이션)              │
└──────────────────────────────────────────────────┘
```

### 2단계 파이프라인

#### 1단계: 이미지 전처리 파이프라인
- **입력**: 원본 단락흔 이미지
- **처리**: 크롭 → 향상 → 필터/메트릭스 (병렬) → 패키징
- **출력**: LLM 분석용 JSON 데이터

#### 2단계: 멀티 에이전트 분석 파이프라인
- **입력**: 전처리된 이미지 + 메트릭스 데이터
- **처리**: 5명 전문가 병렬 분석 → Arbiter Agent 종합
- **출력**: 최종 화재 원인 진단 리포트

---

## 워크플로우

### 1단계: 이미지 전처리 파이프라인

```
START
  │
  ├─→ load_node (이미지 로드)
  │     │
  │     └─→ cropped_image
  │
  ├─→ crop_node (단락흔 영역 크롭)
  │     │
  │     └─→ Morphological Gradient 기반 탐지
  │
  ├─→ enhancement_node (Real-ESRGAN 4x 향상)
  │     │
  │     └─→ enhanced_image
  │
  ├─→ filter_node (CLAHE 필터) ──┐
  │     │                         │
  │     └─→ filtered_image        │
  │                               ├─→ packaging_node
  ├─→ metrics_node (형태학적 분석) ──┘
  │     │
  │     └─→ metrics (circularity, solidity, area)
  │
  └─→ packaging_node (LLM 입력 데이터 생성)
        │
        └─→ analysis_data (JSON)
```

### 2단계: 멀티 에이전트 분석 파이프라인

```
START
  │
  ├─→ contact_expert (접촉불량 전문가)
  │     │
  │     ├─→ Step 1: 위치적 맥락 확인
  │     ├─→ Step 2: 색채 스펙트럼 분석 (아산화동)
  │     ├─→ Step 3: 열적 구배 분석
  │     └─→ Step 4: 금속 표면 상태 분석
  │
  ├─→ dielectric_expert (절연열화 전문가)
  │     │
  │     ├─→ Step 1: 탄화 깊이 분석
  │     ├─→ Step 2: 부풀림 분석
  │     └─→ Step 3: 전역 노화 분석
  │
  ├─→ mechanical_expert (압착/기계적 손상 전문가)
  │     │
  │     ├─→ Step 1: 기계적 변형 분석
  │     ├─→ Step 2: 가닥 분산 분석
  │     └─→ Step 3: 비드 구속 분석
  │
  ├─→ tracking_expert (트래킹 전문가)
  │     │
  │     ├─→ Step 1: 수지상 패턴 분석
  │     ├─→ Step 2: 광택 탐지 (흑연화)
  │     └─→ Step 3: 표면 침식 분석
  │
  └─→ strand_fracture_expert (반단선 전문가)
        │
        ├─→ Step 1: 끝단 형태 분석
        ├─→ Step 2: 비드 분포 분석
        └─→ Step 3: 기계적 피로 분석
              │
              └─→ (모든 전문가 완료 대기)
                    │
                    └─→ arbiter (Arbiter Agent)
                          │
                          ├─→ 시각적 특징 추출
                          ├─→ 1차/2차 단락흔 판정
                          ├─→ 상충 해결 논리 적용
                          ├─→ 증거 위계 적용
                          └─→ 최종 결론 도출
                                │
                                └─→ END
```

---

## 주요 컴포넌트

### 1. 이미지 처리 노드

#### `load_node`
- **기능**: 입력 이미지 로드
- **입력**: 이미지 파일 경로
- **출력**: 원본 이미지 (numpy.ndarray)

#### `crop_node`
- **기능**: Morphological Gradient 기반 단락흔 영역 탐지 및 크롭
- **알고리즘**: 
  - Morphological Gradient로 엣지 탐지
  - Dilation으로 영역 통합
  - Largest Contour로 크롭 영역 결정
- **출력**: 크롭된 이미지

#### `enhancement_node`
- **기능**: Real-ESRGAN을 사용한 4배 초해상도 향상
- **모델**: RealESRGAN_x4plus.pth
- **출력**: 향상된 이미지 (4x 해상도)

#### `filter_node`
- **기능**: CLAHE (Contrast Limited Adaptive Histogram Equalization) 필터 적용
- **목적**: 텍스처 강조 및 대비 향상
- **출력**: 필터 적용 이미지

#### `metrics_node`
- **기능**: 형태학적 분석 메트릭스 추출
- **메트릭스**:
  - **Circularity**: 원형도 (4π × area / perimeter²)
  - **Solidity**: 고형도 (area / convex_area)
  - **Area**: 면적 (픽셀 수)
- **출력**: 메트릭스 딕셔너리 + 이진 마스크

#### `packaging_node`
- **기능**: LLM 분석용 데이터 패키징
- **출력 형식**: Google GenAI 형식 (이미지 + 텍스트)

### 2. 전문가 노드

#### `contact_expert` (접촉불량 전문가)
- **목적**: 전기 접촉 불량 또는 이물질 접촉으로 인한 화재 가능성 분석
- **분석 단계**:
  1. **위치적 맥락 확인**: 접속점 위치 식별 (끝단, 칼날, 나사, 접속점 등)
  2. **색채 스펙트럼 분석**: 아산화동(Cu₂O) 의심 색상 패턴 관찰 (붉은색/주황색/적갈색)
     - **중요 제약**: 일반 RGB 카메라 이미지로는 화학적 성분을 확정할 수 없음
     - 색상만으로는 아산화동, 산화동, 다른 산화물, 열변색 등을 구별 불가
     - 따라서 "탐지"가 아닌 "의심 가능한 색상 패턴 관찰"만 수행
  3. **열적 구배 분석**: 접속부에서 시작하는 열 전파 패턴
  4. **금속 표면 상태 분석**: 전기적 부식 흔적 (곰보 자국, 요철 등)

#### `dielectric_expert` (절연열화 전문가)
- **목적**: 절연재 노화로 인한 화재 가능성 분석
- **분석 단계**:
  1. **탄화 깊이 분석**: 절연재 내부 탄화 정도
  2. **부풀림 분석**: 열에 의한 절연재 팽창
  3. **전역 노화 분석**: 전체적인 절연재 열화 상태

#### `mechanical_expert` (압착/기계적 손상 전문가)
- **목적**: 기계적 압착으로 인한 화재 가능성 분석
- **분석 단계**:
  1. **기계적 변형 분석**: 압착 흔적, 변형 패턴
  2. **가닥 분산 분석**: 전선 가닥의 분산 정도
  3. **비드 구속 분석**: 용융 비드의 구속 상태

#### `tracking_expert` (트래킹 전문가)
- **목적**: 절연재 표면 트래킹으로 인한 화재 가능성 분석
- **분석 단계**:
  1. **수지상 패턴 분석**: 전기적 트래킹 패턴
  2. **광택 탐지**: 흑연화(그래파이타이제이션) 증거
  3. **표면 침식 분석**: 트래킹에 의한 표면 손상

#### `strand_fracture_expert` (반단선 전문가)
- **목적**: 전선 가닥 절단으로 인한 화재 가능성 분석
- **분석 단계**:
  1. **끝단 형태 분석**: 절단면의 형태학적 특징
  2. **비드 분포 분석**: 용융 비드의 분포 패턴
  3. **기계적 피로 분석**: 반복 응력에 의한 피로 파괴

### 3. Arbiter Agent

#### `arbiter` (Arbiter Agent)
- **목적**: 모든 전문가의 분석 결과를 종합하여 최종 결론 도출
- **주요 기능**:
  1. **시각적 특징 추출**: 전문가 분석 결과에서 핵심 특징 추출
  2. **1차/2차 단락흔 판정**: 판정 매트릭스 기반 점수 계산
  3. **상충 해결**: 전문가 간 상충되는 의견 자동 해결
  4. **증거 위계 적용**: 증거 유형별 가중치 적용
  5. **신뢰도 임계값 체크**: 전문가 신뢰도 평균이 임계값 미만일 경우 "판단 불가(UNDETERMINED)" 상태 선언
  6. **최종 결론 생성**: LLM을 통한 종합 리포트 생성

#### 판정 매트릭스 (1차 vs 2차 단락흔)
- **Luster (광택)**: 높음/매끄러움 → 1차, 낮음/거침 → 2차
- **Porosity (기공)**: 없음/미세/조밀 → 1차, 높음/다공성 → 2차
- **Shape (형상)**: 구형/둥근 → 1차, 불규칙/타원형 → 2차
- **Demarcation (경계)**: 선명/명확 → 1차, 점진적/불명확 → 2차
- **Carbonization Location (탄화 위치)**: 국소적/초점 → 1차, 광범위/전역 → 2차

#### 상충 해결 규칙
1. **트래킹 vs 절연열화**: 흑연 광택 탐지 시 트래킹 우선
2. **압착 vs 반단선**: 압착 흔적 명확 시 압착 우선
3. **형상 vs 표면**: 구형이지만 거칠면 2차 단락흔 의심

#### 증거 위계
1. **형상학적 변형** (가중치 3.0): 압착 등 물리적 변형
2. **화학적 성분** (가중치 2.0): 아산화동, 흑연 등 화학적 증거
3. **일반적 탄화** (가중치 1.0): 일반적인 탄화 흔적

---

## 기술 스택

### 핵심 프레임워크
- **LangGraph** (≥0.2.0): 상태 기반 워크플로우 오케스트레이션
- **LangChain Core** (≥0.3.0): LLM 통합

### AI/ML 라이브러리
- **google-genai** (≥0.3.0): Google GenAI SDK (최신 Client 방식)
  - **모델**: gemini-3-flash-preview (기본값)
  - **API 방식**: API Key 기반 인증
- **PyTorch** (≥2.0.0): 딥러닝 프레임워크
- **Real-ESRGAN**: 초해상도 이미지 향상

### 이미지 처리
- **OpenCV** (≥4.8.0): 이미지 처리 및 컴퓨터 비전
- **scikit-image** (≥0.22.0): 형태학적 분석
- **NumPy** (≥1.24.0): 수치 연산
- **Pillow** (≥10.0.0): 이미지 I/O

### 기타
- **matplotlib** (≥3.7.0): 시각화
- **python-dotenv** (≥1.0.0): 환경 변수 관리

---

## 프로젝트 구조

```
P_04_Scope/
├── main.py                          # 메인 실행 파일
├── config.py                        # 설정 파일
├── requirements.txt                 # 의존성 목록
├── README_RUN.md                    # 실행 가이드
│
├── data/                            # 입력 이미지 디렉토리
│   ├── Primary_Arc_Bead_1.png
│   ├── Primary_Arc_Bead_2.png
│   └── ...
│
├── outputs/                         # 출력 디렉토리
│   ├── Primary_Arc_Bead_1/
│   │   ├── full_pipeline.png
│   │   ├── investigation_result.txt
│   │   └── llm_gemini_format.json
│   └── ...
│
├── src/                             # 소스 코드
│   ├── graph_builder.py            # 그래프 빌더
│   ├── state.py                    # 상태 정의
│   ├── utils.py                    # 공통 유틸리티
│   │
│   └── nodes/                      # 노드 모듈
│       ├── load.py                 # 이미지 로드 노드
│       ├── crop.py                 # 크롭 노드
│       ├── enhancement.py          # 향상 노드
│       ├── filter.py               # 필터 노드
│       ├── metrics.py              # 메트릭스 노드
│       ├── packaging.py            # 패키징 노드
│       ├── investigation.py        # 조사 노드 래퍼
│       │
│       └── experts/                # 전문가 모듈
│           ├── contact_expert.py           # 접촉불량 전문가
│           ├── dielectric_expert.py        # 절연열화 전문가
│           ├── mechanical_expert.py        # 압착 전문가
│           ├── tracking_expert.py           # 트래킹 전문가
│           ├── strand_fracture_expert.py    # 반단선 전문가
│           ├── arbiter.py                   # Arbiter Agent
│           ├── arbiter_utils.py             # Arbiter 유틸리티
│           ├── expert_utils.py              # 공통 유틸리티
│           └── system_instructions.py      # 시스템 인스트럭션
│
├── notebook/                        # 개발용 노트북
│   ├── Agent_1_NexusGlow_Expert.ipynb
│   ├── Agent_2_DielectricAge_Expert.ipynb
│   ├── Agent_3_MechStress_Expert.ipynb
│   ├── Agent_4_CarbonTrack_Expert.ipynb
│   ├── Agent_5_StrandFracture_Expert.ipynb
│   └── Arbiter_InsightArbiter.ipynb
│
├── weights/                         # 모델 가중치
│   └── RealESRGAN_x4plus.pth
│
└── Manual/                          # 문서 디렉토리
    └── PROJECT_OVERVIEW.md          # 이 문서
```

---

## 실행 방법

### 1. 환경 설정

#### 가상환경 활성화
```powershell
# PowerShell
.\venv\Scripts\Activate.ps1

# CMD
venv\Scripts\activate.bat
```

#### 의존성 설치
```powershell
pip install -r requirements.txt
```

### 2. 환경 변수 설정

`.env` 파일 생성:
```
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL_NAME=gemini-3-flash-preview  # 선택사항 (기본값: gemini-3-flash-preview)
```

**API 키 발급 방법**:
1. Google AI Studio (https://aistudio.google.com/) 접속
2. API 키 생성
3. `.env` 파일에 `GEMINI_API_KEY`로 설정

### 3. 실행

#### 이미지 파일 지정하여 실행
```powershell
python main.py data/Primary_Arc_Bead_1.png
```

#### 대화형 모드 (이미지 선택)
```powershell
python main.py
```

#### 전처리만 실행 (분석 제외)
```powershell
python main.py data/Primary_Arc_Bead_1.png --preprocess-only
```

### 4. 출력

실행 후 `outputs/{이미지명}/` 디렉토리에 다음 파일들이 생성됩니다:

- `full_pipeline.png`: 전체 파이프라인 시각화 (1x5 레이아웃)
- `investigation_result.txt`: 전문가 리포트 + 최종 분석 결과
- `llm_gemini_format.json`: LLM 입력 데이터 (JSON 형식)

---

## 세부 사항

### 상태 관리 (State Management)

#### GraphState (이미지 처리 파이프라인)
```python
class GraphState(TypedDict):
    input_image_path: str
    original_image: Optional[np.ndarray]
    cropped_image: Optional[np.ndarray]
    enhanced_image: Optional[np.ndarray]
    filtered_image: Optional[np.ndarray]
    binary_mask: Optional[np.ndarray]
    metrics: Optional[dict]
    analysis_data: Optional[dict]
    errors: Annotated[list[str], operator.add]
```

#### InvestigationState (멀티 에이전트 분석)
```python
class InvestigationState(TypedDict):
    payload: List[Any]
    expert_reports: Annotated[List[str], operator.add]
    expert_analysis_results: Annotated[dict, merge_dicts]
    expert_confidence_scores: Annotated[dict, merge_dicts]
    expert_evidence: Annotated[dict, merge_dicts]
    final_verdict: Optional[str]
    errors: Annotated[List[str], operator.add]
```

### Reducer 패턴

LangGraph의 Reducer 패턴을 사용하여 병렬 실행 시 상태 충돌 없이 병합:

- **`operator.add`**: 리스트 병합 (expert_reports, errors)
- **`merge_dicts`**: 딕셔너리 병합 (expert_analysis_results, expert_confidence_scores, expert_evidence)

### 병렬 처리

#### Fan-out (분산)
- START → [5개 전문가 노드] (병렬 실행)
- LangGraph가 자동으로 병렬 처리

#### Fan-in (수집)
- [5개 전문가 노드] → Arbiter Agent
- 모든 전문가 완료 대기 후 Arbiter 실행

### 전문가 분석 프로세스

각 전문가는 다음 단계를 거쳐 분석:

1. **이미지 추출**: payload에서 이미지 바이트 데이터 추출
2. **다단계 순차 분석**: 각 단계별 Gemini Vision API 호출 (Google GenAI SDK 사용)
   - 시스템 인스트럭션: `system_instruction` 파라미터로 전달
   - 부정적 제약: 불확실한 정보에 대한 추측 금지, 화학적 성분 확정 불가능 명시
3. **신뢰도 점수 계산**: 가중치 기반 점수 산출
4. **증거 수집**: 단계별 증거 추출
5. **리포트 생성**: 구조화된 리포트 텍스트 생성

### Arbiter Agent 프로세스

1. **신뢰도 임계값 체크**: 전문가 신뢰도 평균이 임계값(기본값: 0.6) 미만일 경우 "판단 불가(UNDETERMINED)" 상태 선언
2. **시각적 특징 추출**: 전문가 분석 결과에서 핵심 특징 추출
3. **1차/2차 판정**: 판정 매트릭스 기반 점수 계산
4. **상충 해결**: CONFLICT_RESOLUTION_RULES 적용
5. **증거 위계 적용**: EVIDENCE_HIERARCHY 기반 가중치 적용
6. **최종 결론 생성**: LLM을 통한 종합 리포트 생성 (Google GenAI SDK 사용)

### 설정 파일 (config.py)

주요 설정 항목:
- `SR_SCALE`: 초해상도 확대 배율 (기본값: 4)
- `CLAHE_CLIP_LIMIT`: CLAHE 클립 리미트 (기본값: 4.0)
- `OUTPUT_DIR`: 출력 디렉토리 (기본값: "outputs")
- `DATA_DIR`: 입력 이미지 디렉토리 (기본값: "data")
- `ARBITER_CONFIDENCE_THRESHOLD`: Arbiter Agent 신뢰도 임계값 (기본값: 0.6)

### 에러 처리

- 각 노드는 에러 발생 시 `errors` 리스트에 추가
- Reducer 패턴으로 모든 에러 자동 수집
- 최종 결과에 에러 정보 포함

### 확장성

#### 새 전문가 추가 방법
1. `src/nodes/experts/` 디렉토리에 새 전문가 모듈 생성
2. `src/nodes/investigation.py`에 노드 함수 추가
3. `src/graph_builder.py`의 `build_investigation_graph()`에 노드 및 엣지 추가

#### 새 이미지 처리 단계 추가 방법
1. `src/nodes/` 디렉토리에 새 노드 모듈 생성
2. `src/graph_builder.py`의 `build_graph()`에 노드 및 엣지 추가

---

## 참고 사항

- **LangGraph 공식 문서**: https://langchain-ai.github.io/langgraph/
- **Google GenAI SDK**: https://ai.google.dev/gemini-api/docs
- **Google AI Studio**: https://aistudio.google.com/ (API 키 발급)
- **Real-ESRGAN**: https://github.com/xinntao/Real-ESRGAN

---

**작성일**: 2024년
**버전**: 1.1.0

## 변경 이력

### v1.1.0 (최신)
- **SDK 변경**: Vertex AI SDK → Google GenAI SDK (google-genai)
- **모델 변경**: gemini-2.5-pro → gemini-3-flash-preview
- **인증 방식**: 서비스 계정 → API Key 기반
- **시스템 인스트럭션**: config의 `system_instruction` 파라미터로 전달
- **화학적 성분 분석 제약**: RGB 이미지로는 화학적 성분 확정 불가능 명시
- **Arbiter Agent**: 신뢰도 임계값 미만 시 "판단 불가(UNDETERMINED)" 상태 추가

### v1.0.0
- 초기 버전

