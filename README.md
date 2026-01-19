# Fire CSI AI Agent (P_04_Scope) - 프로젝트 설명서

## 1. 프로젝트 개요
**Fire CSI AI Agent**는 화재 현장 이미지를 정밀 분석하여 화재 원인(접촉 불량, 절연 열화, 기계적 손상, 트래킹 등)을 과학적으로 규명하는 AI 시스템입니다. 
다양한 전문가 에이전트(Expert Agents)들이 협업하는 구조로 설계되었으며, LangGraph 기반의 Multi-Hotspot Loop 아키텍처를 채택하여 이미지 내 여러 발화 지점을 순차적으로 정밀 타격합니다.

---

## 2. 시스템 아키텍처

### 2.1. 전체 워크플로우 (OODA Loop 기반)
시스템은 크게 4단계의 OODA Loop(Observe-Orient-Decide-Act)를 따르며, 그 중 **Decide(판단)** 및 **Act(실행)** 단계에서 전문가 그래프가 작동합니다.

1.  **Main Graph (`investigation_graph.py`)**: 사용자 입력을 받아 적절한 전문가에게 배분하고 결과를 취합합니다.
2.  **Expert Sub-graphs**: 각 전문 분야별로 독립된 그래프가 존재하며, 심층 분석을 수행합니다.

### 2.2. 전문가 에이전트 구성 (src/graphs/)
각 전문가는 특정 화재 원인에 특화되어 있으며, 공통된 **Multi-Hotspot Loop** 구조를 가집니다.

*   **Contact Expert** (`contact_expert_graph.py`): 접촉 불량(Loose Connection), 단자대 과열 분석.
*   **Aging Expert** (`aging_expert_graph.py`): 절연 열화(Insulation Degradation), 경년 변화 분석.
*   **Deform Expert** (`deform_expert_graph.py`): 기계적 변형(Compression, Crushing), 외력 손상 분석.
*   **Necking Expert** (`necking_expert_graph.py`): 반단선(Semi-disconnection), 소선 단선 분석.
*   **Tracking Expert** (`tracking_expert_graph.py`): 트래킹(Tracking), 절연 파괴 경로 분석.

---

## 3. 전문가 그래프 상세 구조 (Multi-Hotspot Loop)

모든 전문가 그래프는 아래의 표준화된 파이프라인을 따릅니다.

### Phase 1: 탐지 및 준비 (Identify)
1.  **Hotspot Detector (Node 0)** (`common_nodes.py`):
    *   이미지 전체를 스캔하여 이상 징후(Hotspot)를 다수 탐지합니다.
    *   각 Hotspot에 ID, 심각도(Severity Score), 손상 유형(Damage Type)을 부여합니다.
2.  **Hotspot Manager**:
    *   탐지된 Hotspot을 심각도 순으로 정렬(Priority Quest)하고 큐(Queue)에 적재합니다.
    *   하나씩 꺼내어 루프(Loop)를 시작합니다.

### Phase 2: 루프 및 정밀 분석 (Analyze Loop)
각 Hotspot에 대해 다음 과정을 반복합니다:
1.  **ROI Crop**: 해당 지점을 잘라내고(Crop), 이미지 향상(Upscaling)을 적용하여 해상도를 높입니다.
2.  **Component Classifier (Node 1)**:
    *   크롭된 이미지와 원본 컨텍스트를 비교하여 부품 유형(Terminal, Wire, PCB, Plug 등)을 식별합니다. (LLM 기반)
3.  **Specialist Analysis (Node 2 - Routing)**:
    *   식별된 부품 유형에 맞는 전문 분석가 노드(예: `contact_terminal_node`, `aging_wire_node`)로 라우팅됩니다.
    *   **Dual Input Strategy**: 전문가 노드는 '원본 이미지(문맥)'와 'ROI 이미지(디테일)'를 동시에 보며 정밀 판독합니다.
4.  **Result Aggregator**: 개별 분석 결과를 리스트에 축적합니다.

### Phase 3: 종합 판정 (Verdict)
*   **Verdict Node (Node 3)**:
    *   모든 Hotspot의 분석 결과를 종합합니다.
    *   단순 나열이 아닌, **증거 대결(Evidence Weighing)** 로직을 통해 가장 유력한 화재 원인을 도출하고 최종 리포트를 작성합니다.

---

## 4. 디렉토리 구조 (`src/`)

```
src/
├── graphs/                 # LangGraph 정의 (워크플로우)
│   ├── investigation_graph.py
│   ├── contact_expert_graph.py
│   ├── aging_expert_graph.py
│   └── ... (기타 전문가 그래프)
├── nodes/                  # 노드 로직 구현 (실제 동작)
│   ├── common_nodes.py     # 공통 노드 (Detector 등)
│   ├── contact_nodes.py
│   ├── aging_nodes.py
│   └── ...
├── prompts/                # LLM 시스템 프롬프트
│   ├── common_prompts.py   # 공통 프롬프트
│   ├── contact_expert_prompts.py
│   └── ...
├── tools/                  # 유틸리티 도구
│   └── experts/expert_utils.py # Gemini 호출, 이미지 로드 등
├── state.py                # 전역 상태 정의 (InvestigationState)
└── utils.py                # 일반 헬퍼 함수
```

## 5. 핵심 기술 스택
*   **LangGraph**: 에이전트 워크플로우 및 상태 관리 (Cyclic Graph 지원).
*   **Google Gemini 1.5 Flash**: Vision 및 Text 처리를 담당하는 핵심 LLM.
*   **OpenCV / NumPy**: 이미지 전처리(ROI Crop) 및 향상.

## 6. 개발 가이드라인
*   **표준화 준수**: 모든 전문가 노드는 입출력 스키마와 함수 명명 규칙을 통일해야 합니다.
*   **절대 경로 사용**: 파일 스토리지 접근 시 항상 절대 경로를 사용합니다.
*   **검증 필수**: 코드 수정 후 반드시 `python scripts/verify_expert_graphs.py`를 실행하여 그래프 빌드 오류를 확인해야 합니다.
