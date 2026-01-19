# 프로젝트 워크플로우

## 개요

화재조사 AI 멀티 에이전트 시스템은 세 가지 실행 모드를 지원합니다:

1. **ReAct 모드** (기본): 전처리 → ReAct 에이전트 (동적 도구 사용)
2. **일반 모드** (`--normal-mode`): 전처리 → 멀티 에이전트 분석
3. **전처리만 모드** (`--preprocess-only`): 전처리만 실행

---

## 전체 워크플로우 다이어그램

```
┌─────────────────────────────────────────────────────────────────┐
│                        main.py (진입점)                          │
│  python main.py [image_path] [--normal-mode] [--preprocess-only]│
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────┐
        │  1. 이미지 전처리 파이프라인    │
        │     (모든 모드에서 공통)        │
        └────────────────┬───────────────┘
                         │
                         ▼
        ┌────────────────────────────────┐
        │  2. 실행 모드 분기              │
        └───────┬───────────┬────────────┘
                │           │
    ┌───────────┘           └───────────┐
    │                                    │
    ▼                                    ▼
┌──────────────────┐         ┌──────────────────┐
│ ReAct 모드        │         │ 일반 모드          │
│ (기본)           │         │ (--normal-mode)  │
└──────┬───────────┘         └────────┬──────────┘
       │                               │
       ▼                               ▼
┌──────────────────────┐     ┌──────────────────┐
│ ReAct 에이전트 실행  │     │ 멀티 에이전트 분석 │
│ (동적 도구 선택)      │     │ (5명 전문가)      │
└──────────────────────┘     └──────────────────┘
```

---

## 1단계: 이미지 전처리 파이프라인

**모든 실행 모드에서 공통으로 실행됩니다.**

### 그래프 구조

```
START
  │
  ├─→ load_node (이미지 로드)
  │     │
  │     └─→ original_image (numpy.ndarray)
  │
  ├─→ crop_node (단락흔 영역 크롭)
  │     │
  │     └─→ Morphological Gradient 기반 탐지
  │     └─→ cropped_image
  │
  ├─→ enhancement_node (Real-ESRGAN 4x 향상)
  │     │
  │     └─→ enhanced_image (4배 해상도)
  │
  ├─→ filter_node (CLAHE 필터) ──┐
  │     │                         │
  │     └─→ filtered_image        │
  │                               ├─→ packaging_node
  ├─→ metrics_node (형태학적 분석) ──┘
  │     │
  │     └─→ metrics {
  │           circularity: float,
  │           solidity: float,
  │           area: int
  │         }
  │
  └─→ packaging_node (LLM 입력 데이터 생성)
        │
        └─→ analysis_data {
              metadata: {...},
              images: {
                enhanced: base64,
                filtered: base64,
                analysis_mask: base64
              },
              metrics: {...},
              comparison: {...}
            }
```

### 노드 상세

| 노드 | 기능 | 입력 | 출력 |
|------|------|------|------|
| `load_node` | 이미지 파일 로드 | `input_image_path` | `original_image` |
| `crop_node` | 단락흔 영역 탐지 및 크롭 | `original_image` | `cropped_image`, `binary_mask` |
| `enhancement_node` | Real-ESRGAN 4x 초해상도 향상 | `cropped_image` | `enhanced_image` |
| `filter_node` | CLAHE 필터 적용 | `enhanced_image` | `filtered_image` |
| `metrics_node` | 형태학적 분석 (원형도, 고형도, 면적) | `cropped_image`, `binary_mask` | `metrics` |
| `packaging_node` | LLM 입력 형식으로 변환 (Base64 인코딩) | 모든 전처리 결과 | `analysis_data` (JSON) |

---

## 2단계: 실행 모드별 워크플로우

### 모드 1: ReAct 모드 (기본)

**실행 명령:**
```bash
python main.py [image_path]
# 또는 명시적으로
python main.py [image_path] --query "질문"
```

**워크플로우:**

```
전처리 완료
  │
  ├─→ Payload 변환 (to_gemini_vertex_ai_format)
  │     │
  │     └─→ payload_parts (이미지 + 텍스트)
  │
  └─→ ReAct 에이전트 실행
        │
        ├─→ ReAct 그래프 초기화
        │     ├─→ GeminiChatModel 생성
        │     ├─→ ToolRegistry 초기화
        │     │     ├─→ ImageAnalyzerTool
        │     │     ├─→ ImageEnhancerTool
        │     │     ├─→ ImageCropperTool
        │     │     ├─→ ImageFilterTool
        │     │     ├─→ RunPreprocessingPipelineTool
        │     │     └─→ RunInvestigationPipelineTool
        │     └─→ create_react_agent() 호출
        │
        ├─→ 초기 상태 설정
        │     └─→ messages: [HumanMessage("질문 + 이미지 경로")]
        │
        └─→ ReAct 사이클 실행 (동적)
              │
              ├─→ Thought: 작업 계획 수립
              │
              ├─→ Action: 도구 선택 및 호출
              │     │
              │     └─→ 예: run_investigation_pipeline(image_path)
              │           │
              │           ├─→ 내부적으로 전처리 파이프라인 실행
              │           │
              │           └─→ 내부적으로 조사 파이프라인 실행
              │                 │
              │                 └─→ "조사 완료" 메시지 반환
              │
              ├─→ Observation: 도구 실행 결과 수신
              │
              └─→ Final Answer: 최종 답변 생성
                    │
                    └─→ "Final Answer: [결과 요약]"
```

**ReAct 에이전트 도구:**

| 도구 | 기능 | 입력 |
|------|------|------|
| `analyze_image_morphology` | 형태학적 특성 분석 | `image_path` |
| `enhance_image` | Real-ESRGAN 4x 향상 | `image_path`, `output_path` (선택) |
| `crop_image` | 단락흔 영역 크롭 | `image_path`, `output_path` (선택) |
| `apply_clahe_filter` | CLAHE 필터 적용 | `image_path`, `output_path` (선택) |
| `run_preprocessing_pipeline` | 전처리 파이프라인 실행 | `image_path` |
| `run_investigation_pipeline` | 전처리 + 조사 파이프라인 실행 | `image_path` |

**출력:**
- `output/{image_name}/react_agent_result.txt`: ReAct 에이전트 최종 답변

---

### 모드 2: 일반 모드

**실행 명령:**
```bash
python main.py [image_path] --normal-mode
```

**워크플로우:**

```
전처리 완료
  │
  ├─→ Payload 변환 (to_gemini_vertex_ai_format)
  │     │
  │     └─→ payload_parts (이미지 + 텍스트)
  │
  └─→ 멀티 에이전트 분석 파이프라인
        │
        ├─→ START
        │     │
        │     ├─→ contact_expert (접촉불량 전문가)
        │     │     ├─→ Step 1: 위치적 맥락 확인
        │     │     ├─→ Step 2: 색채 스펙트럼 분석
        │     │     ├─→ Step 3: 열적 구배 분석
        │     │     └─→ Step 4: 금속 표면 상태 분석
        │     │
        │     ├─→ dielectric_expert (절연열화 전문가)
        │     │     ├─→ Step 1: 탄화 깊이 분석
        │     │     ├─→ Step 2: 부풀림 분석
        │     │     └─→ Step 3: 전역 노화 분석
        │     │
        │     ├─→ mechanical_expert (압착/기계적 손상 전문가)
        │     │     ├─→ Step 1: 기계적 변형 분석
        │     │     ├─→ Step 2: 가닥 분산 분석
        │     │     └─→ Step 3: 비드 구속 분석
        │     │
        │     ├─→ tracking_expert (트래킹 전문가)
        │     │     ├─→ Step 1: 수지상 패턴 분석
        │     │     ├─→ Step 2: 광택 탐지 (흑연화)
        │     │     └─→ Step 3: 표면 침식 분석
        │     │
        │     └─→ strand_fracture_expert (반단선 전문가)
        │           ├─→ Step 1: 끝단 형태 분석
        │           ├─→ Step 2: 비드 분포 분석
        │           └─→ Step 3: 기계적 피로 분석
        │                 │
        │                 └─→ (모든 전문가 완료 대기)
        │                       │
        │                       └─→ chief_investigator (Arbiter Agent)
        │                             │
        │                             ├─→ 시각적 특징 추출
        │                             ├─→ 1차/2차 단락흔 판정
        │                             ├─→ 상충 해결 논리 적용
        │                             ├─→ 증거 위계 적용
        │                             └─→ 최종 결론 도출
        │                                   │
        │                                   └─→ END
```

**출력:**
- `output/{image_name}/expert_reports.txt`: 전문가 리포트
- `output/{image_name}/final_verdict.txt`: 최종 결론
- `output/{image_name}/investigation_result.json`: 전체 결과 (JSON)

---

### 모드 3: 전처리만 모드

**실행 명령:**
```bash
python main.py [image_path] --preprocess-only
```

**워크플로우:**

```
전처리 완료
  │
  └─→ 결과 저장
        │
        ├─→ output/{image_name}/preprocessing_result.json
        ├─→ output/{image_name}/enhanced_image.png
        ├─→ output/{image_name}/filtered_image.png
        ├─→ output/{image_name}/analysis_mask.png
        └─→ output/{image_name}/metrics.txt
```

**종료** (조사 파이프라인 실행 안 함)

---

## 데이터 흐름

### State 흐름

#### GraphState (전처리 파이프라인)
```python
{
    "input_image_path": str,
    "original_image": np.ndarray,
    "cropped_image": np.ndarray,
    "enhanced_image": np.ndarray,
    "filtered_image": np.ndarray,
    "binary_mask": np.ndarray,
    "metrics": dict,
    "analysis_data": dict,
    "errors": List[str]
}
```

#### InvestigationState (조사 파이프라인)
```python
{
    "payload": List[Any],  # LLM 입력 데이터
    "expert_reports": List[str],
    "expert_analysis_results": dict,
    "expert_confidence_scores": dict,
    "expert_evidence": dict,
    "final_verdict": str,
    "errors": List[str],
    # 각 서브그래프별 캐시
    "contact_cached_image_data": Optional[bytes],
    "dielectric_cached_image_data": Optional[bytes],
    ...
}
```

#### ReActState (ReAct 에이전트)
```python
{
    "messages": List[BaseMessage],  # LangChain MessagesState 상속
    "task": str,  # 선택적
    "context": dict  # 선택적
}
```

---

## 실행 예시

### ReAct 모드 (기본)
```bash
# 이미지 파일 지정 (기본 질문 사용)
python main.py data/Primary_Arc_Bead_1.png

# 사용자 질문 지정
python main.py data/Primary_Arc_Bead_1.png --query "이미지를 분석하고 화재 원인을 조사하세요."

# 대화형 선택 모드
python main.py
```

### 일반 모드
```bash
# 일반 멀티 에이전트 분석 실행
python main.py data/Primary_Arc_Bead_1.png --normal-mode
```

### 전처리만 모드
```bash
python main.py data/Primary_Arc_Bead_1.png --preprocess-only
```

---

## 주요 특징

### 1. 병렬 처리
- **전처리 파이프라인**: `filter`와 `metrics` 노드가 병렬 실행
- **조사 파이프라인**: 5명의 전문가가 병렬 실행 (Fan-out/Fan-in 패턴)

### 2. 상태 기반 워크플로우
- LangGraph의 `StateGraph`를 사용하여 상태를 공유
- 각 노드는 부분 상태만 반환하여 업데이트

### 3. 서브그래프 패턴
- 각 전문가는 독립적인 서브그래프로 구현
- 서브그래프를 컴파일된 그래프 객체로 부모 그래프에 노드로 추가

### 4. ReAct 패턴
- ReAct 에이전트는 `create_react_agent`를 사용하여 구현
- 동적으로 도구를 선택하고 실행하여 작업 수행

---

## 변경 이력

- 2024-01-XX: ReAct 에이전트 모드 추가
- 2024-01-XX: `run_investigation_pipeline` 중복 호출 문제 해결
- 2024-01-XX: "Final Answer:" 종료 신호 추가
- 2024-01-XX: ReAct 모드를 기본 모드로 변경, 일반 모드는 `--normal-mode` 플래그로 활성화

