# Fire CSI AI Agent (P_04_Scope) - 프로젝트 설명서

## 1. 프로젝트 개요

**Fire CSI AI Agent**는 화재 현장 이미지를 정밀 분석하여 화재 원인(접촉 불량, 기계적 손상, 반단선 등)을 과학적으로 규명하는 AI 시스템입니다.
다양한 전문가 에이전트(Expert Agents)들이 협업하는 아키텍처로 구성되어 있으며, LangGraph 기반의 **Map-Reduce 패턴**과 **Analyst-Critic Debate** 설계를 채택하여 이미지 내 다중 발화 징후(Hotspot)를 빠르고 빈틈 없이 심층 분석합니다.

---

## 2. 시스템 아키텍처

### 2.1. 전체 워크플로우 관리

시스템은 LangGraph를 통해 메인 그래프와 각 전문가 서브그래프들을 제어하여 아래 흐름을 따릅니다:

1.  **공통 병렬 전처리 (Main Graph)**: `hotspot_detector_node`에서 이미지 전체를 겹치는 패치 단위로 스캔하여 Hotspot을 동시 다발적으로 탐지 후 1차 병합합니다. 이를 `preprocess_hotspots_node`가 받아 일괄 Crop 및 카테고리 분류, 선명도 향상을 1회 선처리 합니다.
2.  **독립 전문가 병렬 분석 (Expert Sub-graphs)**: 각 화재 원인 분석 분야별로 독립적인 프로세스가 생성되며, 담당 범위 내의 Hotspot들을 분산 동시 평가합니다.
3.  **최종 종합 결론 (Arbiter Sub-group)**: 각각의 전문가에서 도출해낸 증거를 바탕으로 상호 논쟁(Debate)을 거쳐 최종 판정(발화 인과관계 및 원인 판단)을 내립니다.

### 2.2. 전문가 에이전트 라인업

특정 증상 검토에 전문화된 에이전트 그룹으로 이뤄져 있습니다.

- **현재 활성 전문가 (Active):**
  - **Contact Expert** (`contact_expert_graph.py`): 접촉 불량(Loose Connection)에 의한 발열 및 아산화동 증후 등 분석.
  - **Deform Expert** (`deform_expert_graph.py`): 외력, 압착, 변형 패턴에 의한 기계적 단락 및 손상 분석.
  - **Necking Expert** (`necking_expert_graph.py`): 소선의 반복 단선, 열 수축 인장 및 반단선 이력 검측.
- **비활성 전문가 (Inactive):**
  - **Aging Expert** (절연 열화 분석)
  - **Tracking Expert** (이물질 기반 트래킹 전파 경로 검증)

---

## 3. 전문가 서브그래프 및 Map-Reduce 작동 원리

전문가 서브그래프는 속도 효율성 향상과 내부 보수적인 증명 로직을 탑재했습니다.

### Phase 1: 작업 분배 및 매핑 (Map: Fan-Out)

- `distribute_work` 기능이 LangGraph의 고수준 추상화인 `Send` 메커니즘을 동원해, 전처리 완료된 N개의 수많은 Hotspot 데이터를 각각의 Worker로 분배(Mapping)합니다.

### Phase 2: 정밀 분석 및 증명 획득 (Worker)

- `analyze_hotspot_worker` 단일 노드 안에서 각 Hotspot 하나씩을 집중 대상으로 놓고, 컴포넌트 특성에 맞춰 시각 증거와 물리 흔적 조사를 Gemini Vision API를 이용해 실시합니다.

### Phase 3: 분석 취합 및 강도 높은 자가 검증 (Reduce & Debate: Fan-In)

- **Supervisor**: 모든 개별 Worker가 조사해온 내역을 `operator.add`로 병합(Reduce)합니다.
- **Analyst-Critic Debate (논쟁 메커니즘)**:
  - 즉각적인 Verdict 수립의 불확실성을 배제하고, AI Analyst가 내세우는 최초 혐의 가설에 대해 Critic 모델이 증거 오남용, 맥락 간과 측면에서 강력히 반박 및 검증을 시도합니다.
- **Finalize**: 서로의 논리 조율 과정을 3차례 반복하며 가장 합당한 원인 도출 및 신뢰도 결정을 최종 처리합니다.

---

## 4. 핵심 기술 구조 (src/)

- **`src/agent.py`**: 시스템 진입 및 LangGraph Main StateGraph 빌더.
- **`src/graphs/`**: 각 Map-Reduce 전문가별 서브그래프 로직 캡슐화.
- **`src/nodes/`**: 실물 워크플로우의 컴포넌트(`common`, `experts`, `arbiter` 노드)를 정의하는 공간.
- **`src/utils/`**: Rate Limiter 제어체계 (`api_concurrency.py`), 구글 네트워크 불안정 방어형 지수 백오프 기반 재시도 로직 (`retry_utils.py`) 및 공통 API/Image 라이브러리.
- **`src/models/`**: Pydantic 스키마 정의 (JSON 정형 응답 객체 통제).
- **`src/states/`**: 전문가들간 글로벌 타입 정의 등 상태 충돌 회피 장치.

---

## 5. 핵심 기술 스택

- **LangGraph / LangChain**: 다계층 병렬 맵-리듀스 분산 제어 및 Debate 루프 설계 프레임워크.
- **Google GenAI SDK**: 강력한 텍스트-비전 동시 판독 Gemini-3-Flash 등 추론형 LLM 제공망.
- **OpenCV / NumPy / Real-ESRGAN**: Edge 검출 기반 핫스팟 도출 및 정밀 판독을 위한 해상도 복원 라이브러리.

## 6. 개발 가이드라인

- **API Concurrency(동시요청) 보호**: Rate Limits, Quota 제약을 피하기 위해 반드시 `ThreadSafeRateLimiter` 기반으로 전역 통제가 가능하도록 해야 합니다.
- **경로 보관성 증명**: 데이터 오염 방지 및 검사를 위해 이미지 디버깅 산출물과 정형 텍스트 파일들은 반드시 `outputs/{image키워드}/` 하위에 보존됩니다.
