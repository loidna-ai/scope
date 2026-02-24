# ⚠️ [DEPRECATED] ReAct 에이전트 설계 문서는 사용하지 않습니다.

> 이 설계 문서는 프로젝트 이력 및 설계 초기 버전을 다루는 아카이브 목적입니다.
> 본 설계의 ReAct 패턴은 도입 검토되었으나, 현재는 각 전문가 노드 내에서 **Map-Reduce 패턴과 Analyst-Critic Debate** 체제를 직접 운용하는 방식으로 대체되어 사용되지 않습니다. 최신 워크플로우는 `WORKFLOW.md`나 `PROJECT_OVERVIEW.md`를 참고 바랍니다.

# ReAct 에이전트 통합 설계 문서

## 개요

이 문서는 LangGraph의 Prebuilt Agent를 활용한 ReAct(Reasoning+Acting) 에이전트 통합 설계를 설명합니다. ReAct 패턴을 통해 에이전트가 동적으로 도구를 선택하고 실행하여 사용자 질문에 답변합니다.

## 설계 원칙

1. **기존 구조 유지**: 기존 전문가 서브그래프 빌더는 그대로 유지 (안정성 보장)
2. **ReAct 추가**: ReAct 에이전트는 추가 기능으로 제공 (동적 의사결정)
3. **서브그래프 패턴**: 현재 프로젝트의 서브그래프를 직접 노드로 추가하는 패턴 유지
4. **Prebuilt Agent**: LangGraph의 `create_react_agent` 사용
5. **도구 기반 실행**: 기존 파이프라인과 함수를 도구로 제공하여 ReAct가 호출 가능
6. **독립 실행**: ReAct 에이전트를 독립적으로도 실행 가능
7. **모듈화**: 각 컴포넌트를 독립적으로 유지

## 디렉토리 구조

**현재 프로젝트 구조** (기존):

```
src/
├── state.py                    # GraphState, InvestigationState 정의
├── agent.py                    # build_graph(), build_investigation_graph()
├── graphs/                     # 전문가별 서브그래프 빌더
│   ├── contact_expert_graph.py
│   ├── dielectric_expert_graph.py
│   ├── mechanical_expert_graph.py
│   ├── tracking_expert_graph.py
│   └── strand_fracture_expert_graph.py
├── nodes/                      # 노드 정의
│   ├── load.py, crop.py, enhancement.py, ...
│   └── experts/               # 전문가 노드
│       ├── contact_expert.py
│       ├── node_factory.py    # create_step_node() 팩토리
│       └── expert_utils.py    # call_gemini_vision() 등
└── edges/                      # 엣지 정의
    ├── preprocessing_edges.py
    ├── investigation_edges.py
    └── expert_edges.py
```

**ReAct 에이전트 추가 구조** (신규 추가, 기존 구조 유지):

```
src/
├── state.py                    # ReActState 추가 (기존: GraphState, InvestigationState 유지)
├── agent.py                    # build_react_agent_graph() 추가 (기존 함수 유지)
│
├── graphs/                     # 전문가별 서브그래프 빌더 (기존 유지)
│   ├── __init__.py
│   ├── contact_expert_graph.py      # build_contact_expert_graph() (기존 유지)
│   ├── dielectric_expert_graph.py   # build_dielectric_expert_graph() (기존 유지)
│   ├── mechanical_expert_graph.py   # build_mechanical_expert_graph() (기존 유지)
│   ├── tracking_expert_graph.py     # build_tracking_expert_graph() (기존 유지)
│   └── strand_fracture_expert_graph.py  # build_strand_fracture_expert_graph() (기존 유지)
│
├── agents/                     # ReAct 에이전트 관련 (신규)
│   ├── __init__.py
│   ├── gemini_chatmodel.py    # Gemini ChatModel 래퍼
│   └── react_agent.py         # 통합 ReAct 서브그래프 빌더
│                               # build_react_agent_graph() 함수
│                               # (전문가별 ReAct는 선택적, 필요시 추가)
│
├── tools/                      # 도구 정의 (신규)
│   ├── __init__.py
│   ├── registry.py           # 도구 레지스트리 (싱글톤)
│   └── tools/                # 구체적인 도구들
│       ├── __init__.py
│       ├── image_tools.py    # 이미지 분석 도구
│       │                       # - ImageAnalyzerTool
│       │                       # - ImageEnhancerTool
│       └── pipeline_tools.py # 기존 파이프라인 도구
│                               # - RunPreprocessingPipelineTool
│                               # - RunInvestigationPipelineTool
│                               # (전문가별 특화 도구는 선택적, 필요시 추가)
│
├── nodes/                      # 노드 정의 (기존 유지)
│   ├── load.py                # load_node (기존 유지)
│   ├── crop.py                # crop_node (기존 유지)
│   ├── enhancement.py         # enhancement_node (기존 유지)
│   ├── filter.py              # filter_node (기존 유지)
│   ├── metrics.py             # metrics_node (기존 유지)
│   ├── packaging.py           # packaging_node (기존 유지)
│   │
│   ├── experts/               # 전문가 노드 (기존 유지)
│   │   ├── __init__.py
│   │   ├── contact_expert.py  # Contact 전문가 step 함수들 (기존 유지)
│   │   │                       # - step1_location_context()
│   │   │                       # - step2_spectral_analysis()
│   │   │                       # - step3_thermal_gradient()
│   │   │                       # - step4_surface_analysis()
│   │   │                       # - calculate_confidence_score()
│   │   │                       # - collect_evidence()
│   │   │                       # - generate_report()
│   │   │
│   │   ├── dielectric_expert.py    # Dielectric 전문가 step 함수들 (기존 유지)
│   │   ├── mechanical_expert.py    # Mechanical 전문가 step 함수들 (기존 유지)
│   │   ├── tracking_expert.py     # Tracking 전문가 step 함수들 (기존 유지)
│   │   ├── strand_fracture_expert.py  # StrandFracture 전문가 step 함수들 (기존 유지)
│   │   │
│   │   ├── arbiter.py         # node_arbiter (기존 유지)
│   │   ├── arbiter_utils.py   # Arbiter 유틸리티 (기존 유지)
│   │   ├── expert_utils.py    # call_gemini_vision() 등 (기존 유지)
│   │   ├── node_factory.py    # create_step_node() 팩토리 (기존 유지)
│   │   └── system_instructions.py  # 시스템 지시사항 (기존 유지)
│   │
│   └── react/                 # ReAct 노드 (서브그래프 사용) (신규)
│       ├── __init__.py
│       └── react_agent_node.py  # 서브그래프를 호출하는 노드 (선택적)
│                                 # InvestigationState와 ReActState 변환용
│
└── edges/                      # 엣지 정의 (기존 유지)
    ├── __init__.py
    ├── preprocessing_edges.py  # add_preprocessing_edges() (기존 유지)
    ├── investigation_edges.py  # add_investigation_edges() (기존 유지)
    │                           # add_investigation_edges_with_react() 추가 (신규)
    └── expert_edges.py         # add_contact_expert_edges() 등 (기존 유지)
```

**구조 요약**:

- **기존 구조**: 그대로 유지 (변경 없음)
  - `graphs/`: 전문가별 서브그래프 빌더
  - `nodes/`: 모든 노드 정의
  - `edges/`: 엣지 정의
- **신규 추가**: ReAct 에이전트 관련
  - `agents/`: ReAct 에이전트 빌더
  - `tools/`: 도구 정의 및 레지스트리
  - `nodes/react/`: ReAct 노드 (선택적)
- **수정**: `agent.py`에 `build_react_agent_graph()` 추가, `edges/investigation_edges.py`에 ReAct 포함 엣지 추가

## 1. ReActState 정의

`src/state.py`에 추가할 상태 정의:

**참고**: 현재 프로젝트는 `InvestigationState`를 사용하지만, ReAct 에이전트는 LangGraph의 표준 `MessagesState`를 사용합니다.

### 옵션 1: MessagesState 사용 (권장 - LangGraph 공식 방식)

LangGraph의 `create_react_agent`는 기본적으로 `MessagesState`를 사용합니다.

**LangGraph 공식 권장사항**:

- `MessagesState`는 `messages` 필드를 자동으로 포함하며 reducer 기능이 내장되어 있습니다
- `Annotated[List[BaseMessage], operator.add]` 패턴이 자동으로 적용됩니다
- 추가 필드가 필요하면 상속하여 확장 가능합니다

```python
from langgraph.graph import MessagesState
from typing import Optional, Dict, Any

# MessagesState는 이미 messages 필드를 포함하고 있음 (reducer 포함)
# 추가 필드가 필요하면 확장 가능
class ReActState(MessagesState):
    """
    ReAct 에이전트 상태 (MessagesState 확장)

    LangGraph 공식 권장 방식:
    - MessagesState를 상속받아 messages 필드 자동 포함
    - reducer 기능 자동 적용 (operator.add)
    - 추가 필드는 선택적으로 정의
    """
    # 추가 컨텍스트 (선택적)
    task: Optional[str] = ""  # 수행할 작업 설명 (기본값 설정 권장)
    context: Optional[Dict[str, Any]] = None  # 컨텍스트 정보
```

**참고**: LangGraph 공식 문서에서는 `MessagesState`를 직접 사용하거나 최소한의 확장만 권장합니다.

### 옵션 2: InvestigationState와 통합

기존 `InvestigationState`와 통합하려면:

```python
from langchain_core.messages import BaseMessage

class ReActState(TypedDict):
    """
    ReAct 에이전트 상태 (LangGraph 메시지 기반)

    LangGraph의 prebuilt agent는 메시지 기반 상태를 사용합니다.
    """
    # 메시지 히스토리 (LangGraph 표준)
    messages: Annotated[List[BaseMessage], operator.add]

    # InvestigationState와의 호환성을 위한 필드 (선택적)
    payload: Annotated[List[Any], keep_first]  # 기존 payload 유지

    # 추가 컨텍스트
    task: Optional[str]  # 수행할 작업 설명
    context: Optional[Dict[str, Any]]  # 컨텍스트 정보

    # 에러
    errors: Annotated[List[str], operator.add]
```

**권장**: 옵션 1 (MessagesState 사용) - LangGraph 표준 패턴 준수

## 2. Gemini ChatModel 래퍼

**파일**: `src/agents/gemini_chatmodel.py`

Google Gemini를 LangChain ChatModel 인터페이스로 래핑하여 LangGraph와 통합합니다.

### 현재 프로젝트의 Gemini 사용 방식

현재 프로젝트는 `google.genai` SDK를 직접 사용합니다:

- `src/nodes/experts/expert_utils.py`에서 `call_gemini_vision()` 함수 사용
- `google.genai.Client` 사용
- `types.GenerateContentConfig` 사용

### LangChain ChatModel 래퍼 필요성

`create_react_agent`는 LangChain의 `ChatModel` 인터페이스를 요구하므로, Gemini를 래핑해야 합니다.

### 주요 기능

- LangChain ChatModel 인터페이스 구현
- Gemini Function Calling 지원
- 메시지 형식 변환 (LangChain ↔ Gemini)
- 현재 프로젝트의 `google.genai` SDK 활용

### 핵심 메서드

- `_generate()`: 동기 생성
- `_convert_messages()`: LangChain 메시지를 Gemini 형식으로 변환
- `_convert_response_to_message()`: Gemini 응답을 AIMessage로 변환
- `_create_function_declarations()`: LangChain Tool을 Gemini Function Declaration로 변환

### 현재 프로젝트와의 통합

```python
from google import genai
from google.genai import types
from langchain_core.language_models.chat_models import BaseChatModel

class GeminiChatModel(BaseChatModel):
    """Google Gemini를 LangChain ChatModel로 래핑"""

    def __init__(self):
        # 현재 프로젝트의 설정 사용
        from src.nodes.experts.expert_utils import client, generation_config
        self.client = client
        self.config = generation_config
```

## 3. 도구 정의

### 3.1 이미지 분석 도구

**파일**: `src/tools/image_tools.py`

#### ImageAnalyzerTool (형태학적 분석 도구)

이미지의 형태학적 특성을 분석하는 도구입니다.

**기반 클래스**: `src/nodes/metrics.py`의 `MorphologyAnalyzer`

**주요 함수**:

- `analyze(image: np.ndarray) -> dict`
  - **입력**: 이미지 (BGR 형식, numpy array)
  - **출력**: 형태학적 메트릭스 딕셔너리
    - `circularity`: 원형도 (0~1, 1에 가까울수록 원형)
      - 계산식: `4π * area / perimeter²`
    - `solidity`: 고형도 (0~1, 1에 가까울수록 볼록)
      - 계산식: `area / convex_area`
    - `area`: 면적 (픽셀 수)
  - **추가 출력**: 이진화된 마스크 이미지 (binary_mask)

**사용 예시**:

```python
from src.tools.image_tools import ImageAnalyzerTool

tool = ImageAnalyzerTool()
result = tool._run(image_path="data/image.png")
# 결과: {"circularity": 0.85, "solidity": 0.92, "area": 12345}
```

#### ImageEnhancerTool (이미지 향상 도구)

Real-ESRGAN을 사용하여 이미지를 4배 초해상도로 향상시키는 도구입니다.

**기반 클래스**: `src/nodes/enhancement.py`의 `ImageEnhancer`

**주요 함수**:

- `upscale(image: np.ndarray) -> np.ndarray`
  - **입력**: 이미지 (BGR 형식, numpy array)
  - **출력**: 향상된 이미지 (4배 확대, BGR 형식)
  - **모델**: Real-ESRGAN x4plus
  - **Fallback**: 모델 실패 시 단순 리사이즈

**사용 예시**:

```python
from src.tools.image_tools import ImageEnhancerTool

tool = ImageEnhancerTool()
enhanced_image = tool._run(image_path="data/image.png")
# 결과: 4배 해상도로 향상된 이미지
```

#### ImageCropperTool (스마트 크롭 도구) - 선택적

Morphological Gradient 기반으로 단락흔 영역을 탐지하고 크롭하는 도구입니다.

**기반 클래스**: `src/nodes/crop.py`의 `ImageCropper`

**주요 함수**:

- `crop(image: np.ndarray) -> np.ndarray`
  - **입력**: 이미지 (BGR 형식, numpy array)
  - **출력**: 크롭된 이미지 (BGR 형식)
  - **알고리즘**:
    1. Morphological Gradient 계산 (엣지+질감 탐지)
    2. 이진화 (OTSU)
    3. Dilation (팽창)으로 엣지 연결
    4. Largest Contour 탐지
    5. 패딩 추가 후 크롭
  - **Fallback**: 탐지 실패 시 중앙 크롭

#### ImageFilterTool (CLAHE 필터 도구) - 선택적

CLAHE (Contrast Limited Adaptive Histogram Equalization) 필터를 적용하는 도구입니다.

**기반 클래스**: `src/nodes/filter.py`의 `TextureFilter`

**주요 함수**:

- `apply_clahe(image: np.ndarray) -> np.ndarray`
  - **입력**: 이미지 (BGR 형식, numpy array)
  - **출력**: 필터 적용된 이미지 (BGR 형식)
  - **알고리즘**:
    1. LAB 색공간 변환
    2. L 채널에 CLAHE 적용
    3. BGR 색공간으로 변환
  - **파라미터**: `clipLimit=4.0`, `tileGridSize=(8, 8)`

**도구 구현 예시**:

```python
from langchain_core.tools import BaseTool
from src.nodes.metrics import MorphologyAnalyzer
from src.nodes.enhancement import ImageEnhancer
import cv2
import numpy as np

class ImageAnalyzerTool(BaseTool):
    """이미지 형태학적 분석 도구"""

    name = "analyze_image_morphology"
    description = "이미지의 형태학적 특성을 분석합니다 (원형도, 고형도, 면적)"

    def _run(self, image_path: str) -> str:
        """이미지 형태학적 분석 실행"""
        # 이미지 로드
        img = cv2.imread(image_path)
        if img is None:
            return f"이미지 로드 실패: {image_path}"

        # 분석 수행
        analyzer = MorphologyAnalyzer()
        metrics, binary_mask = analyzer.analyze(img)

        return f"형태학적 분석 결과: 원형도={metrics['circularity']:.3f}, " \
               f"고형도={metrics['solidity']:.3f}, 면적={metrics['area']}픽셀"

class ImageEnhancerTool(BaseTool):
    """Real-ESRGAN 기반 이미지 향상 도구"""

    name = "enhance_image"
    description = "Real-ESRGAN을 사용하여 이미지를 4배 초해상도로 향상시킵니다"

    def _run(self, image_path: str, output_path: str = None) -> str:
        """이미지 향상 실행"""
        # 이미지 로드
        img = cv2.imread(image_path)
        if img is None:
            return f"이미지 로드 실패: {image_path}"

        # 향상 수행
        enhancer = ImageEnhancer()
        enhanced_img = enhancer.upscale(img)

        # 저장 (선택적)
        if output_path:
            cv2.imwrite(output_path, enhanced_img)
            return f"이미지 향상 완료: {output_path} (크기: {enhanced_img.shape})"

        return f"이미지 향상 완료 (크기: {enhanced_img.shape})"
```

### 3.2 파이프라인 도구

**파일**: `src/tools/pipeline_tools.py`

- `RunPreprocessingPipelineTool`: 기존 전처리 파이프라인을 도구로 제공
  - `src/agent.py`의 `build_graph()` 호출
- `RunInvestigationPipelineTool`: 기존 조사 파이프라인을 도구로 제공
  - `src/agent.py`의 `build_investigation_graph()` 호출

### 3.3 전문가별 특화 도구 (선택적, 필요시 추가)

**참고**: 기본적으로는 통합 ReAct 에이전트만 사용하며, 필요시 전문가별 특화 도구를 추가할 수 있습니다.

**파일**: `src/tools/contact_tools.py`, `tracking_tools.py`, etc. (필요시 생성)

각 전문가의 step 함수를 도구로 래핑하는 예시:

**Contact 전문가 도구** (`src/tools/contact_tools.py` - 필요시 생성):

- `AnalyzeLocationContextTool`: `src/nodes/experts/contact_expert.py`의 `step1_location_context()` 래핑
- `AnalyzeSpectralPatternTool`: `step2_spectral_analysis()` 래핑
- `AnalyzeThermalGradientTool`: `step3_thermal_gradient()` 래핑
- `AnalyzeSurfaceErosionTool`: `step4_surface_analysis()` 래핑

**참고**: 각 step 함수는 `src/nodes/experts/expert_utils.py`의 `call_gemini_vision()`을 사용합니다.

**기본 설계**: 통합 ReAct 에이전트는 기존 파이프라인 도구(`RunPreprocessingPipelineTool`, `RunInvestigationPipelineTool`)를 사용하여 기존 전문가 서브그래프를 간접적으로 호출할 수 있습니다.

### 3.4 도구 레지스트리

**파일**: `src/tools/registry.py`

싱글톤 패턴으로 모든 도구를 중앙에서 관리합니다.

```python
class ToolRegistry:
    """도구 레지스트리 싱글톤"""

    def get_tools(self) -> List[BaseTool]:
        """모든 도구 반환"""
        return self._tools

    def get_tools_by_category(self, category: str) -> List[BaseTool]:
        """카테고리별 도구 반환 (예: 'common', 'contact', 'tracking')"""
        return [tool for tool in self._tools if tool.category == category]
```

## 4. ReAct 에이전트 서브그래프 빌더

### 4.1 통합 ReAct 에이전트 (기본)

**파일**: `src/agents/react_agent.py`

모든 도구를 사용하는 통합 ReAct 에이전트:

**LangGraph 공식 권장사항**:

- `create_react_agent`는 `MessagesState`를 기본으로 사용합니다
- `state_modifier`는 시스템 메시지로 자동 추가됩니다
- 도구는 LangChain `BaseTool` 형식이어야 합니다

```python
from langgraph.prebuilt import create_react_agent
from langgraph.graph import CompiledGraph
from src.agents.gemini_chatmodel import GeminiChatModel
from src.tools.registry import ToolRegistry

def build_react_agent_graph() -> CompiledGraph:
    """
    ReAct 에이전트 서브그래프 빌드 (통합)

    LangGraph 공식 권장 방식:
    - create_react_agent는 MessagesState를 기본으로 사용
    - 반환 타입은 CompiledGraph (StateGraph가 아님)
    - 기존 파이프라인 도구를 사용하여 기존 전문가 서브그래프를 간접적으로 호출 가능
    """
    llm = GeminiChatModel()
    registry = ToolRegistry()
    tools = registry.get_tools()  # 모든 도구 (기본: image_tools, pipeline_tools)

    # LangGraph 공식 권장: create_react_agent 사용
    agent = create_react_agent(
        llm=llm,
        tools=tools,
        state_modifier=(
            "당신은 ReAct 패턴을 따르는 AI 에이전트입니다. "
            "사용자의 작업을 수행하기 위해 필요한 도구를 사용하세요. "
            "기존 파이프라인 도구를 사용하여 전문가 분석을 수행할 수 있습니다."
        )
    )

    # create_react_agent는 이미 컴파일된 그래프를 반환
    return agent
```

**LangGraph 공식 문서 참고사항**:

- `create_react_agent`는 내부적으로 `StateGraph`를 생성하고 컴파일하여 반환합니다
- 반환 타입은 `CompiledGraph`이므로 추가 컴파일이 필요 없습니다
- `state_modifier`는 첫 번째 메시지로 자동 추가됩니다

**주요 도구**:

- `RunPreprocessingPipelineTool`: 기존 전처리 파이프라인 호출
- `RunInvestigationPipelineTool`: 기존 조사 파이프라인 호출 (모든 전문가 포함)
- `ImageAnalyzerTool`: 이미지 형태학적 분석
- `ImageEnhancerTool`: Real-ESRGAN 기반 이미지 향상

### 4.2 전문가별 ReAct 에이전트 (선택적, 필요시 추가)

**참고**: 기본 설계에서는 통합 ReAct 에이전트만 사용합니다. 필요시 전문가별 특화 ReAct 에이전트를 추가할 수 있습니다.

**파일**: `src/agents/contact_react_agent.py` (필요시 생성)

예시 - Contact 전문가용 ReAct 에이전트:

```python
def build_contact_react_agent_graph() -> StateGraph:
    """
    Contact 전문가용 ReAct 에이전트 서브그래프 (선택적)

    Contact 전문가가 사용할 수 있는 특화 도구만 제공
    """
    llm = GeminiChatModel()

    # 공통 도구 + Contact 특화 도구
    tools = [
        registry.get_tool("analyze_image"),  # 공통 도구
        AnalyzeLocationContextTool(),        # Contact 특화
        AnalyzeSpectralPatternTool(),        # Contact 특화
        AnalyzeThermalGradientTool(),        # Contact 특화
        AnalyzeSurfaceErosionTool(),         # Contact 특화
    ]

    agent = create_react_agent(
        llm=llm,
        tools=tools,
        state_modifier=(
            "당신은 접촉불량 판별 전문가입니다. "
            "다음 단계를 순차적으로 수행하세요:\n"
            "1. 위치적 맥락 확인\n"
            "2. 색채 스펙트럼 분석\n"
            "3. 열적 구배 분석\n"
            "4. 금속 표면 상태 분석\n"
            "각 단계의 결과를 종합하여 최종 판단을 내리세요."
        )
    )

    return agent
```

### 4.3 싱글톤 패턴

현재 프로젝트는 서브그래프를 직접 노드로 추가하는 방식을 사용합니다 (`src/agent.py` 참고).

ReAct 에이전트도 동일한 패턴을 따릅니다:

```python
# src/agents/react_agent.py
import threading
from langgraph.graph import CompiledGraph

_react_agent_graph = None
_graph_lock = threading.Lock()

def _get_react_agent_graph() -> CompiledGraph:
    """ReAct 에이전트 서브그래프를 싱글톤으로 반환 (Thread-safe)"""
    global _react_agent_graph
    if _react_agent_graph is None:
        with _graph_lock:
            if _react_agent_graph is None:
                _react_agent_graph = build_react_agent_graph()
    return _react_agent_graph
```

**참고**: `src/agent.py`의 `build_investigation_graph()`에서 서브그래프를 직접 노드로 추가하는 방식:

```python
# 기존 전문가 서브그래프 (유지)
builder.add_node("contact", build_contact_expert_graph())
builder.add_node("dielectric", build_dielectric_expert_graph())
# ... 기존 전문가들

# ReAct 에이전트 추가 (신규)
builder.add_node("react_agent", build_react_agent_graph())
```

## 5. ReAct 패턴 동작 원리

### 5.1 ReAct 사이클

ReAct 에이전트는 다음 사이클을 반복합니다:

1. **Reasoning (추론)**: 현재 상황을 분석하고 다음 행동 계획
2. **Acting (행동)**: 도구를 선택하고 실행
3. **Observing (관찰)**: 도구 실행 결과를 관찰
4. **반복**: 목표 달성까지 반복

### 5.2 도구 선택 메커니즘

LangGraph의 `create_react_agent`는 자동으로:

- 사용 가능한 도구 목록을 LLM에 제공
- LLM이 상황에 맞는 도구를 선택
- 도구를 실행하고 결과를 관찰
- 필요시 추가 도구 호출

### 5.3 종료 조건

- 최종 답변 생성 완료
- 최대 반복 횟수 도달
- 에러 발생

## 6. ReAct 노드 (서브그래프 사용)

**파일**: `src/nodes/react/react_agent_node.py`

**참고**: 현재 프로젝트는 서브그래프를 직접 노드로 추가하는 방식을 사용합니다 (`src/agent.py`의 `build_investigation_graph()` 참고).

### 옵션 1: 서브그래프를 직접 노드로 추가 (권장, 현재 프로젝트 패턴)

`src/agent.py`에서:

```python
def build_investigation_graph_with_react() -> StateGraph:
    """조사 그래프에 ReAct 에이전트 노드 추가"""
    builder = StateGraph(InvestigationState)

    # 기존 전문가 노드들
    builder.add_node("contact", build_contact_expert_graph())
    # ...

    # ReAct 에이전트를 서브그래프로 직접 노드로 추가
    builder.add_node("react_agent", build_react_agent_graph())

    # 엣지 추가
    add_investigation_edges(builder)

    return builder.compile()
```

### 옵션 2: 노드 함수로 래핑 (호환성 필요 시)

`InvestigationState`와 `ReActState`가 다른 경우:

```python
def react_agent_node(state: InvestigationState) -> Dict[str, Any]:
    """
    ReAct 에이전트 노드 (서브그래프 사용)

    InvestigationState를 ReActState로 변환하여 실행
    """
    # 서브그래프 가져오기
    react_graph = _get_react_agent_graph()

    # InvestigationState → ReActState 변환
    from langchain_core.messages import HumanMessage

    subgraph_state: ReActState = {
        "messages": [HumanMessage(content=str(state.get("task", "")))],
        "task": state.get("task"),
        "context": {
            "payload": state.get("payload", []),
            "expert_reports": state.get("expert_reports", [])
        },
        "errors": []
    }

    # 서브그래프 실행
    result = react_graph.invoke(subgraph_state)

    # ReActState → InvestigationState 변환
    final_message = result.get("messages", [])[-1] if result.get("messages") else None

    return {
        "expert_reports": [final_message.content if final_message else ""],
        "errors": result.get("errors", [])
    }
```

**권장**: 옵션 1 (서브그래프를 직접 노드로 추가) - 현재 프로젝트 패턴과 일치

## 7. 기존 그래프와의 통합

### 7.1 독립 실행

ReAct 에이전트를 독립적으로 실행:

```python
def run_react_agent_standalone(input_image_path: str, user_query: str):
    """ReAct 에이전트를 독립적으로 실행"""
    react_graph = build_react_agent_graph()

    initial_state = {
        "messages": [HumanMessage(content=f"{user_query}\n이미지: {input_image_path}")],
        "task": user_query,
        "context": {"image_path": input_image_path},
        "errors": []
    }

    result = react_graph.invoke(initial_state)
    return result
```

### 7.2 서브그래프로 통합 (옵션 1: 기존 방식 유지 + ReAct 추가)

**기본 설계**: 기존 `build_investigation_graph()`는 그대로 유지하고, ReAct 에이전트는 별도 함수로 추가합니다.

**방법 1: 기존 그래프 유지 + ReAct 별도 함수 (권장)**

```python
# src/agent.py

# 기존 함수는 그대로 유지
def build_investigation_graph() -> StateGraph:
    """기존 조사 그래프 (변경 없음)"""
    builder = StateGraph(InvestigationState)

    # 기존 전문가 서브그래프들 (그대로 유지)
    builder.add_node("contact", build_contact_expert_graph())
    builder.add_node("dielectric", build_dielectric_expert_graph())
    builder.add_node("mechanical", build_mechanical_expert_graph())
    builder.add_node("tracking", build_tracking_expert_graph())
    builder.add_node("strand_fracture", build_strand_fracture_expert_graph())

    # Arbiter Agent 노드 추가
    builder.add_node("chief_investigator", node_arbiter)

    # 엣지 추가
    add_investigation_edges(builder)

    return builder.compile()

# ReAct 에이전트를 포함한 새로운 함수 추가 (선택적)
def build_investigation_graph_with_react() -> StateGraph:
    """조사 그래프에 ReAct 에이전트 노드 추가 (선택적)"""
    builder = StateGraph(InvestigationState)

    # 기존 전문가 서브그래프들 (그대로 유지)
    builder.add_node("contact", build_contact_expert_graph())
    builder.add_node("dielectric", build_dielectric_expert_graph())
    builder.add_node("mechanical", build_mechanical_expert_graph())
    builder.add_node("tracking", build_tracking_expert_graph())
    builder.add_node("strand_fracture", build_strand_fracture_expert_graph())

    # ReAct 에이전트 서브그래프 추가 (신규)
    builder.add_node("react_agent", build_react_agent_graph())

    # Arbiter Agent 노드 추가
    builder.add_node("chief_investigator", node_arbiter)

    # 엣지 추가 (src/edges/investigation_edges.py 사용)
    # ReAct 에이전트를 포함하도록 엣지 수정 필요
    add_investigation_edges_with_react(builder)

    return builder.compile()
```

**방법 2: 기존 그래프에 ReAct 추가 (선택적)**

기존 `build_investigation_graph()`를 수정하여 ReAct 에이전트를 추가할 수도 있습니다:

```python
def build_investigation_graph(include_react: bool = False) -> StateGraph:
    """조사 그래프 빌드 (ReAct 에이전트 선택적 포함)"""
    builder = StateGraph(InvestigationState)

    # 기존 전문가 서브그래프들 (항상 포함)
    builder.add_node("contact", build_contact_expert_graph())
    builder.add_node("dielectric", build_dielectric_expert_graph())
    builder.add_node("mechanical", build_mechanical_expert_graph())
    builder.add_node("tracking", build_tracking_expert_graph())
    builder.add_node("strand_fracture", build_strand_fracture_expert_graph())

    # ReAct 에이전트 (선택적)
    if include_react:
        builder.add_node("react_agent", build_react_agent_graph())

    # Arbiter Agent 노드 추가
    builder.add_node("chief_investigator", node_arbiter)

    # 엣지 추가
    if include_react:
        add_investigation_edges_with_react(builder)
    else:
        add_investigation_edges(builder)

    return builder.compile()
```

**권장**: 방법 1 (기존 함수 유지 + 별도 함수 추가)

- 기존 코드 안정성 보장
- 기존 사용처에 영향 없음
- ReAct는 필요시에만 사용

**참고**: 현재 프로젝트는 `src/edges/investigation_edges.py`에서 엣지를 정의합니다.

### 7.3 기존 파이프라인을 도구로 제공

ReAct 에이전트가 필요할 때 기존 파이프라인을 호출:

```python
from langchain_core.tools import BaseTool
from src.agent import build_graph, build_investigation_graph
from src.state import GraphState, InvestigationState

class RunPreprocessingPipelineTool(BaseTool):
    """기존 전처리 파이프라인을 ReAct 도구로 제공"""

    name = "run_preprocessing_pipeline"
    description = "이미지 전처리 파이프라인을 실행합니다 (load → crop → enhance → filter/metrics → packaging)"

    def _run(self, image_path: str) -> str:
        """전처리 파이프라인 실행"""
        graph = build_graph()  # src/agent.py의 build_graph() 사용

        initial_state: GraphState = {
            "input_image_path": image_path,
            "original_image": None,
            "cropped_image": None,
            "enhanced_image": None,
            "filtered_image": None,
            "binary_mask": None,
            "metrics": None,
            "analysis_data": None,
            "errors": []
        }

        result = graph.invoke(initial_state)
        return f"전처리 완료: {result.get('analysis_data', {})}"

class RunInvestigationPipelineTool(BaseTool):
    """기존 조사 파이프라인을 ReAct 도구로 제공"""

    name = "run_investigation_pipeline"
    description = "화재조사 멀티 에이전트 분석 파이프라인을 실행합니다"

    def _run(self, payload_data: List[Any]) -> str:
        """조사 파이프라인 실행"""
        from src.agent import analyze_fire_evidence  # src/agent.py의 함수 사용
        result = analyze_fire_evidence(payload_data)
        return f"조사 완료: {result.get('final_verdict', '')}"
```

## 8. 사용 예시

### 8.1 독립 실행

```python
# main.py에 추가
python main.py data/image.png --react-mode --query "이미지를 분석하세요"
```

### 8.2 도구 자동 선택

```python
# ReAct 에이전트가 자동으로 필요한 도구를 선택
# 예: "전처리 파이프라인을 실행하고 결과를 분석하세요"
# → ReAct가 run_preprocessing_pipeline 도구를 호출
# → 그 다음 analyze_image 도구를 호출
# → 최종 답변 생성
```

### 8.3 기존 파이프라인과 ReAct 통합 사용

```python
# ReAct 에이전트가 기존 파이프라인을 도구로 호출
# 예: "전처리 파이프라인을 실행하고 결과를 분석하세요"
# → ReAct가 run_preprocessing_pipeline 도구를 호출
# → 그 다음 analyze_image 도구를 호출
# → 최종 답변 생성

# 또는 기존 조사 파이프라인 호출
# 예: "화재 증거를 분석하세요"
# → ReAct가 run_investigation_pipeline 도구를 호출
# → 기존 전문가 서브그래프들이 실행됨
# → 결과를 종합하여 답변 생성
```

**참고**: 전문가별 ReAct 에이전트는 선택적이며, 기본적으로는 통합 ReAct 에이전트만 사용합니다.

### 8.4 기존 파이프라인과 통합

```python
# ReAct 에이전트가 자동으로 필요한 도구를 선택
# 예: "전처리 파이프라인을 실행하고 결과를 분석하세요"
# → ReAct가 run_preprocessing_pipeline 도구를 호출
```

## 9. LangGraph 권장 패턴 준수

### 9.1 서브그래프 패턴

**LangGraph 공식 권장 방식**:

- ✅ 서브그래프를 컴파일된 그래프 객체로 직접 노드로 추가
- ✅ `builder.add_node("subgraph_name", compiled_subgraph)` 패턴 사용
- ✅ 같은 State 스키마 사용 시 상태가 자동으로 공유됨
- ✅ 체크포인터는 부모 그래프에만 전달하면 자동으로 서브그래프에 전달됨

**현재 프로젝트 패턴**:

- ✅ 서브그래프를 직접 노드로 추가하는 방식 (LangGraph 공식 권장과 일치)
- ✅ 싱글톤 패턴으로 서브그래프 재사용 (선택적, 성능 최적화)
- ✅ Thread-safe 초기화 (선택적, 멀티스레드 환경 고려)

### 9.2 Prebuilt Agent 사용

**LangGraph 공식 권장 방식**:

- ✅ `create_react_agent` 사용 (LangGraph 공식 권장)
- ✅ 자동으로 ReAct 패턴 구현 (Reasoning → Acting → Observing)
- ✅ 도구 호출 및 반복 로직 자동 처리
- ✅ `MessagesState`를 기본으로 사용 (자동 reducer 적용)
- ✅ `tools_condition`을 사용하여 도구 호출 여부 자동 판단

**구현 세부사항**:

- `create_react_agent`는 내부적으로 `ToolNode`와 `tools_condition`을 사용합니다
- 도구 호출이 필요하면 `ToolNode`로 라우팅, 아니면 에이전트 노드로 라우팅
- 최대 반복 횟수는 기본값 사용하거나 `checkpoint` 옵션으로 제어 가능

### 9.3 상태 관리

**LangGraph 공식 권장 방식**:

- ✅ 메시지 기반 상태 (LangGraph 표준)
- ✅ `MessagesState` 사용 시 `Annotated[List[BaseMessage], operator.add]` 자동 적용
- ✅ Partial State 반환 (업데이트할 필드만 반환)
- ✅ Reducer 함수를 통해 상태 병합 (병렬 실행 시 중요)

**현재 프로젝트와의 통합**:

- `InvestigationState`: 커스텀 TypedDict (기존 전문가 서브그래프용)
- `ReActState`: MessagesState 확장 (ReAct 에이전트용)
- 두 상태 간 변환이 필요할 경우 노드 함수에서 처리

## 10. 구현 순서

1. **ReActState 정의** (`src/state.py`)
   - `MessagesState` 사용 또는 커스텀 `ReActState` 정의
2. **Gemini ChatModel 래퍼** (`src/agents/gemini_chatmodel.py`)
   - 현재 프로젝트의 `google.genai` SDK 활용
   - LangChain `ChatModel` 인터페이스 구현
3. **도구 정의** (`src/tools/`)
   - 공통 도구 (image_tools.py, pipeline_tools.py)
   - 전문가별 특화 도구 (선택적)
   - 각 step 함수를 도구로 래핑
4. **도구 레지스트리** (`src/tools/registry.py`)
   - 싱글톤 패턴으로 도구 관리
5. **ReAct 서브그래프 빌더** (`src/agents/react_agent.py`)
   - 통합 ReAct 에이전트 (기본)
   - `create_react_agent` 사용
   - 전문가별 ReAct 에이전트는 선택적 (필요시 추가)
6. **그래프 통합** (`src/agent.py`)
   - `build_react_agent_graph()` 함수 추가
   - `build_investigation_graph_with_react()` 함수 추가 (선택적)
7. **메인 통합** (`main.py`)
   - ReAct 모드 추가 (선택적)

## 11. 주요 특징

### 11.1 유연성

- 독립 실행 가능
- 서브그래프로 통합 가능
- 기존 파이프라인과 호환

### 11.2 확장성

- 새로운 도구 쉽게 추가
- 다양한 LLM 지원 가능
- 전문가별 특화 에이전트 생성 가능

### 11.4 동적 의사결정

- 상황에 맞는 도구 자동 선택
- 복잡한 작업을 단계별로 분해하여 처리
- 중간 결과를 바탕으로 다음 행동 결정

### 11.3 일관성

- 현재 프로젝트 패턴 유지
- LangGraph 공식 권장사항 준수
- 기존 코드와 통합 용이

## 12. 참고사항

### 12.1 기존 그래프와의 관계

**현재 프로젝트의 그래프** (`src/agent.py`):

- `build_graph()`: 이미지 전처리 파이프라인 (고정 워크플로우)
  - `GraphState` 사용
  - `load → crop → enhance → [filter, metrics] → packaging`
- `build_investigation_graph()`: 멀티 에이전트 분석 (고정 워크플로우)
  - `InvestigationState` 사용
  - `[contact, dielectric, mechanical, tracking, strand_fracture] → chief_investigator`

**ReAct 에이전트 그래프** (신규):

- `build_react_agent_graph()`: ReAct 에이전트 (동적 의사결정)
  - `MessagesState` 또는 `ReActState` 사용
  - 도구를 동적으로 선택하여 실행

**모두 독립적으로 사용 가능하며, 필요시 통합 가능**

### 12.2 서브그래프 vs 독립 그래프

- **서브그래프로 사용**: 기존 파이프라인에 통합
- **독립 그래프로 사용**: 사용자 질문에 직접 응답

**두 방식 모두 지원하며, 용도에 따라 선택**

### 12.3 기존 서브그래프 빌더 vs ReAct 에이전트

**중요**: **옵션 1 (기존 방식 유지 + ReAct 추가)** 방식으로 설계됩니다.

#### 기존 서브그래프 빌더 (유지 - 변경 없음)

- `src/graphs/contact_expert_graph.py` → `build_contact_expert_graph()`
- `src/graphs/dielectric_expert_graph.py` → `build_dielectric_expert_graph()`
- `src/graphs/mechanical_expert_graph.py` → `build_mechanical_expert_graph()`
- `src/graphs/tracking_expert_graph.py` → `build_tracking_expert_graph()`
- `src/graphs/strand_fracture_expert_graph.py` → `build_strand_fracture_expert_graph()`
- **용도**: 고정된 순차 워크플로우 (step1 → step2 → step3 → ...)
- **사용**: `build_investigation_graph()`에서 병렬 실행
- **상태**: 그대로 유지, 변경 없음

#### ReAct 에이전트 (신규 추가)

- `src/agents/react_agent.py` → `build_react_agent_graph()` (통합 ReAct)
- **용도**: 동적 도구 선택 및 실행
- **사용**: 독립 실행 또는 기존 그래프에 추가
- **특징**: 기존 파이프라인 도구를 통해 기존 전문가 서브그래프를 간접적으로 호출 가능

#### 통합 방식 (옵션 1)

```python
# src/agent.py

# 기존 함수는 그대로 유지
def build_investigation_graph() -> StateGraph:
    """기존 조사 그래프 (변경 없음)"""
    builder = StateGraph(InvestigationState)

    # 기존 전문가 서브그래프들 (그대로 유지)
    builder.add_node("contact", build_contact_expert_graph())
    builder.add_node("dielectric", build_dielectric_expert_graph())
    builder.add_node("mechanical", build_mechanical_expert_graph())
    builder.add_node("tracking", build_tracking_expert_graph())
    builder.add_node("strand_fracture", build_strand_fracture_expert_graph())

    builder.add_node("chief_investigator", node_arbiter)
    add_investigation_edges(builder)

    return builder.compile()

# ReAct 에이전트를 포함한 새로운 함수 추가 (선택적)
def build_investigation_graph_with_react() -> StateGraph:
    """조사 그래프에 ReAct 에이전트 노드 추가"""
    builder = StateGraph(InvestigationState)

    # 기존 전문가 서브그래프들 (그대로 유지)
    builder.add_node("contact", build_contact_expert_graph())
    builder.add_node("dielectric", build_dielectric_expert_graph())
    builder.add_node("mechanical", build_mechanical_expert_graph())
    builder.add_node("tracking", build_tracking_expert_graph())
    builder.add_node("strand_fracture", build_strand_fracture_expert_graph())

    # ReAct 에이전트 추가 (신규)
    builder.add_node("react_agent", build_react_agent_graph())

    builder.add_node("chief_investigator", node_arbiter)
    add_investigation_edges_with_react(builder)  # ReAct 포함 엣지

    return builder.compile()
```

**장점**:

- ✅ 기존 코드 안정성 유지
- ✅ 기존 사용처에 영향 없음
- ✅ ReAct는 필요시에만 사용
- ✅ 점진적 마이그레이션 가능

### 12.4 통합 ReAct 에이전트 (기본)

**기본 설계**: 통합 ReAct 에이전트만 사용합니다.

- **통합 ReAct**: 모든 도구 사용, 범용적
  - 기존 파이프라인 도구를 통해 기존 전문가 서브그래프 호출 가능
  - 이미지 분석 도구 제공
  - 사용자 질문에 유연하게 응답

**전문가별 ReAct 에이전트**: 선택적 (필요시 추가)

- 특화 도구만 사용, 정확도 향상 가능
- 기본 설계에서는 포함하지 않음

### 12.5 도구 추가 방법

1. `BaseTool`을 상속받아 새 도구 클래스 생성
2. `ToolRegistry._initialize_tools()`에 추가
3. 자동으로 ReAct 에이전트에서 사용 가능

### 12.6 기존 서브그래프 빌더의 역할

**기존 서브그래프 빌더는 그대로 유지됩니다:**

- `src/graphs/contact_expert_graph.py`: Contact 전문가 고정 워크플로우
- `src/graphs/dielectric_expert_graph.py`: Dielectric 전문가 고정 워크플로우
- 등등...

**이유:**

1. **안정성**: 검증된 고정 워크플로우 유지
2. **성능**: 순차 실행이 예측 가능하고 최적화됨
3. **호환성**: 기존 코드와의 호환성 유지
4. **선택권**: 필요에 따라 기존 방식 또는 ReAct 방식 선택 가능

**ReAct 에이전트는 추가 기능으로 제공:**

- 동적 의사결정이 필요한 경우 사용
- 사용자 질문에 대한 유연한 응답 필요 시 사용
- 기존 서브그래프와 병행 사용 가능

## 13. 다음 단계

1. 각 컴포넌트 구현
2. 단위 테스트 작성
3. 통합 테스트 수행
4. 문서화 및 예제 작성
5. 프로덕션 배포

---

**작성일**: 2025-01-XX  
**버전**: 1.3  
**상태**: 설계 완료, LangGraph 공식 권장 방식 반영 완료, 구현 대기

## 변경 이력

- **v1.3**: LangGraph 공식 문서 권장 방식 반영
  - `MessagesState` 사용 방식 명확화 및 공식 권장사항 추가
  - `create_react_agent` 반환 타입 정정 (`CompiledGraph`)
  - 서브그래프 패턴 공식 권장 방식 명시
  - 상태 관리 공식 권장 방식 명시 (`Annotated` reducer 패턴)
  - Prebuilt Agent 사용 방식 상세화 (`ToolNode`, `tools_condition` 설명)
- **v1.2**: 현재 프로젝트 구조 반영
  - `src/agent.py` 구조 반영
  - `src/graphs/` 서브그래프 패턴 반영
  - `src/nodes/experts/node_factory.py` 패턴 반영
  - `google.genai` SDK 사용 방식 반영
  - `InvestigationState` 구조 반영
- **v1.1**: 스트리밍 기능 제거, agent 기능 집중
- **v1.0**: 초기 설계

## LangGraph 공식 문서 준수 사항

### ✅ 준수 사항

1. **서브그래프 패턴**: 컴파일된 그래프를 직접 노드로 추가하는 방식 사용
   - `builder.add_node("subgraph_name", compiled_subgraph)` 패턴
   - 같은 State 스키마 사용 시 상태 자동 공유
2. **MessagesState 사용**: `create_react_agent`의 기본 상태 사용
   - `MessagesState` 상속으로 `messages` 필드 자동 포함
   - `Annotated[List[BaseMessage], operator.add]` reducer 자동 적용
3. **Prebuilt Agent**: `create_react_agent` 사용 (공식 권장)
   - 내부적으로 `ToolNode`와 `tools_condition` 사용
   - 도구 호출 여부 자동 판단
4. **도구 형식**: LangChain `BaseTool` 형식 사용
   - `name`, `description`, `_run()` 메서드 구현
5. **Partial State**: 노드에서 업데이트할 필드만 반환
   - 상태 병합은 reducer 함수가 자동 처리
6. **Reducer 패턴**: `Annotated`와 reducer 함수 사용
   - `operator.add` (리스트 병합)
   - `merge_dicts` (딕셔너리 병합)
   - `keep_first`, `keep_last` (값 선택)

### 📝 참고 사항

- `create_react_agent`는 내부적으로 `StateGraph`를 생성하고 컴파일하여 `CompiledGraph`를 반환합니다
- `MessagesState`는 `messages` 필드의 reducer를 자동으로 제공합니다 (`operator.add`)
- 서브그래프는 같은 State 스키마를 사용하면 상태가 자동으로 공유됩니다
- 체크포인터는 부모 그래프에만 전달하면 자동으로 서브그래프에 전달됩니다
- `state_modifier`는 첫 번째 메시지로 자동 추가되어 시스템 메시지 역할을 합니다
