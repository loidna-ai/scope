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

- **이미지 전처리 파이프라인**: 단락흔 탐지(Hotspot Detector), 초해상도 향상, 컴포넌트 분류(Preprocessor).
- **멀티 에이전트 병렬 분석**: 활성화된 3명의 전문가(Contact, Deform, Necking)가 병렬로 분석 수행.
- **Map-Reduce 패턴**: 각 전문가가 여러 Hotspot을 Send API로 분산 처리(Worker) 후 종합(Supervisor).
- **Analyst-Critic Debate**: 각 전문가 내부 및 최종 중재 시, AI 분석관과 비평가 간의 논쟁을 통한 판정 신뢰도 향상.
- **Arbiter Agent**: 전문가들의 분석 결과를 종합하고 논쟁 과정을 거쳐 최종 결론 도출.

### 주요 특징

- **LangGraph 기반**: 상태 기반 워크플로우 오케스트레이션 및 Map-Reduce 분산 처리.
- **상태 관리 구조화**: `InvestigationState` 및 각 전문가별 `ExpertState`를 분리하여 데이터 오염 방지.
- **API 동시성 제어**: `ThreadSafeRateLimiter`와 전역 Semaphore를 이용한 Gemini API 호출 최적화(429/503 에러 방지).
- **자동 Fallback 및 재시도**: Exponential Backoff 적용 및 모델 Fallback 메커니즘 지원.

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
│ 공통 전처리      │          │ 멀티 에이전트 분석  │
│ 파이프라인       │          │ 파이프라인          │
└───────┬────────┘          └────────┬──────────┘
        │                             │
┌───────▼─────────────────────────────▼──────────┐
│           LangGraph StateGraph                   │
│  (상태 기반 워크플로우 오케스트레이션)              │
└──────────────────────────────────────────────────┘
```

---

## 워크플로우

### 1단계: 공통 전처리 파이프라인 (Pre-computation)

```
START
  │
  ├─→ hotspot_detector_node
  │     └─→ Overlap Grid 방식으로 이미지 패치 분할
  │     └─→ 병렬 Gemini 분석을 통해 Hotspot 후보군 탐지
  │     └─→ NMS 적용하여 중복 핫스팟 제거
  │
  └─→ preprocess_hotspots_node
        └─→ ROI 크롭 (Crop)
        └─→ 컴포넌트 조기 분류 (Classification)
        └─→ 이미지 해상도 향상 (Enhancement - Caching 지원)
```

### 2단계: 전문가 & Debate 워크플로우

```
preprocessor
  │
  ├─→ [Fan-out] 전문가 병렬 처리 (Contact, Deform, Necking)
  │     │
  │     ├─→ distribute_work (Send API 기반 Map-Reduce 패턴)
  │     │     └─→ analyze_hotspot_worker (각 Hotspot 병렬 분석)
  │     │
  │     ├─→ supervisor_verdict (Worker 분석 내용 취합)
  │     │
  │     └─→ Analyst-Critic Debate (조건부 발생)
  │           ├─→ verdict_analyst (가설 수립)
  │           ├─→ verdict_critic (가설 비판)
  │           └─→ verdict_finalize (최종 결론 생성)
  │
  └─→ [Fan-in] 전문분석 완료 후 대기
        │
        └─→ Arbiter Agent (chief_investigator / debate nodes)
              ├─→ 전문가 의견 종합 및 상충 해결
              └─→ 최종 화재 원인 결론 생성 및 출력
```

_참고: Aging(절연열화), Tracking(트래킹) 관련 2명의 전문가는 현재 버전에서 비활성화되어 있습니다._

---

## 주요 컴포넌트

### 1. 전처리/탐지 노드

- **`hotspot_detector_node` (`common_nodes.py`)**: 원본 이미지를 다중 Slicing하여 각 패치별 단락흔 가능성 영역을 탐지 후 NMS로 병합합니다.
- **`preprocess_hotspots_node` (`preprocessor_node.py`)**: 단락흔 영역을 미리 자르고, 분석에 불필요한 영역 식별을 위해 기초 분류 작업을 수행합니다. 이 단계는 향후 Worker단위 연산 비용을 아끼기 위해 1회 선행 처리됩니다.

### 2. 활성 전문가 (Expert Nodes)

공통적으로 `Map-Reduce`를 활용하며, `src/nodes/{expert}_nodes.py` 내부에 로직이 구현됩니다.

- **`contact_expert` (접촉불량 전문가)**
  - 위치적 맥락, 색채 스펙트럼, 열적 구배 및 표면 상태 등을 종합 분석하여 접속 불량 여부 판단.
- **`deform_expert` (기계적 손상 전문가)**
  - 압착, 가닥 분산, 변형 패턴 등의 기계적 요소와 외력 개입 여부 분석.
- **`necking_expert` (반단선 전문가)**
  - 소선의 절단면 형태, 용융 비드의 분포 등을 통해 반단선/단선 징후 추적 및 분석.

### 3. Debate 메커니즘 (Analyst-Critic)

거짓양성률(오판)을 낮추기 위해 도입된 구조로, AI가 단순히 초기 결론을 내는 것이 아니라 자체적으로 비판적 리뷰(Critic) 루프를 전개합니다.

- **Analyst**: 초기 증거를 기반으로 지배적 화재 원인 가설 수립.
- **Critic**: 증거 과대해석, 정보 공백 및 맹점을 점검하고 방어 논리를 무너뜨리는 검증 시도.
- **Supervisor / Finalize**: 최대 3턴 간의 합의 과정을 관장하며, 타협 불가 시 보수적인 관점으로 '판단 불가' 또는 패널티 적용 등을 제어.

---

## 기술 스택

### 핵심 프레임워크

- **LangGraph (≥0.2.0)**: 상태 기반 워크플로우 통제, Send API 등 최신 Graph 패턴 제공.
- **LangChain Core (≥0.3.0)**: 구조화된 컨텍스트 통신 지원.

### AI 및 통신

- **google-genai (≥0.3.0)**: Vertex AI 환경을 지원하며 API Rate Limit과 호환 지원되는 Gemini 호출 엔진. 모델 `gemini-3-flash-preview` 적용.

### 이미지 프로세싱

- **OpenCV / scikit-image / NumPy**: BBox 연산 처리, NMS, Morphological 알고리즘 제어.
- **Real-ESRGAN**: 이미지 초해상도 복원.

### 동시성 최적화

- **`ThreadSafeRateLimiter` (`api_concurrency.py`)**: 다중 Event Loop 간 Thread-safe하게 동작하도록 API 요청 속도 및 동시성을 제어.

---

## 프로젝트 구조

```
P_04_Scope/
├── main.py                          # 파이프라인 싱글 엔트리 포인트
├── config.py                        # 글로벌 시스템 파라미터 및 임계값
├── requirements.txt                 # 의존성 정의 파일
│
├── data/                            # 테스트 및 원본 입력 이미지 경로
├── outputs/                         # 분석 결과물 출력 경로 (생성형 보고서, JSON 등)
│
├── src/                             # 코어 아키텍처
│   ├── agent.py                     # Main Graph 조립 스크립트 (진입 노드 정의)
│   ├── state.py                     # 글로벌 LangGraph State 스키마 (InvestigationState)
│   ├── utils/                       # 통합 유틸리티 패키지
│   │   ├── api_concurrency.py       # API Global Rate Limiter 제어체계
│   │   ├── retry_utils.py           # 구글 API Timeout, 429 방어 Retry 구현
│   │   ├── expert_api_utils.py      # Gemini 공통 호출 인터페이스
│   │   └── image_utils.py           # 이미지 입출력, Crop, Safe Load 유틸리티
│   ├── nodes/
│   │   ├── common_nodes.py          # Hotspot Detector
│   │   ├── preprocessor_node.py     # Crop, Encode, Enhance 전처리
│   │   ├── expert_worker_utils.py   # 각 전문가가 사용하는 공통 Vision Call 동작
│   │   ├── contact_nodes.py         # Contact 전문가 전용 노드
│   │   ├── deform_nodes.py          # Deform 전문가 전용 노드
│   │   ├── necking_nodes.py         # Necking 전문가 전용 노드
│   │   └── arbiter_nodes/           # Arbiter의 Debate, Judge 처리 관련
│   ├── graphs/
│   │   ├── graph_utils.py           # 공통 래퍼, 라우팅 정의 모듈
│   │   └── {expert}_expert_graph.py # 각 전문가 Map-Reduce State Graph 정의
│   ├── models/                      # Pydantic 기반 구조화된 출력 스키마
│   ├── prompts/                     # Prompt 설계 정의
│   └── edges/                       # (엣지 관제)
```

---

## 실행 방법

### 1. 환경 설정

```powershell
# 가상 환경 생성 및 진입
python -m venv venv
.\venv\Scripts\Activate.ps1

# 필수 라이브러리 설치
pip install -r requirements.txt
```

### 2. 구글 크레덴셜 (`.env`)

프로젝트 최상단에 `.env` 파일을 생성하고 내용을 세팅합니다.

```ini
GEMINI_API_KEY=your-api-key-here
# (선택) Vertex AI 프로젝트 연결 시
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=global
```

### 3. 모델 구동

**특정 이미지 분석 실행**:

```powershell
python main.py data/image.jpg
```

_실행이 완료되면 메인 디렉터리에 `outputs/image/` 디렉터리가 생성되며 그 안에 정돈된 결과 (`investigation_result.json`, `.md` 등)가 저장됩니다._

---

## 세부 사항

1. **에러 제어 및 백오프 체계 (Resilience)**: `RetryBudgetGuard` 및 지수 백오프(`async_retry_with_backoff`) 로직을 내장하여 LLM API Rate Limit 등 제한을 영리하게 분산 대응합니다.
2. **동적 Hotspot Loop 성능**: Slicing 이미지에서 확보된 다발성 Hotspot 들이 각기 다른 Subgraph 안에서도 병렬 Worker 노드들에 의해 동시 분석됨에 따라 시스템 효율을 극대화 합니다.
3. **Pydantic 응답 엄격성**: 체계적인 리포트와 State Graph 간 자료 교환을 위해, LLM의 거의 모든 생성값은 `src/models/`에 맞춘 규격화된 객체(Structured)로 전파됩니다.
