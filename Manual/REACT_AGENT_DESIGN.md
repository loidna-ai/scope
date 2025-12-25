# ReAct 에이전트 통합 설계 문서

## 개요

이 문서는 LangGraph의 Prebuilt Agent를 활용한 ReAct(Reasoning+Acting) 에이전트 통합 설계를 설명합니다. ReAct 패턴을 통해 에이전트가 동적으로 도구를 선택하고 실행하여 사용자 질문에 답변합니다.

## 설계 원칙

1. **서브그래프 패턴**: 현재 프로젝트의 `node_contact` 패턴과 동일하게 적용
2. **Prebuilt Agent**: LangGraph의 `create_react_agent` 사용
3. **도구 기반 실행**: 기존 파이프라인과 함수를 도구로 제공하여 ReAct가 호출 가능
4. **독립 실행**: ReAct 에이전트를 독립적으로도 실행 가능
5. **모듈화**: 각 컴포넌트를 독립적으로 유지
6. **전문가별 특화**: 각 전문가마다 특화된 도구와 ReAct 에이전트 제공 가능

## 디렉토리 구조

```
src/
├── state.py                    # ReActState 추가
├── graph_builder.py           # build_react_agent_graph 추가
│
├── agents/                    # ReAct 에이전트 관련
│   ├── __init__.py
│   ├── gemini_chatmodel.py    # Gemini ChatModel 래퍼
│   ├── react_agent.py         # ReAct 서브그래프 빌더
│   ├── contact_react_agent.py # Contact 전문가용 ReAct (선택적)
│   ├── tracking_react_agent.py # Tracking 전문가용 ReAct (선택적)
│   └── ...                    # 기타 전문가별 ReAct 에이전트
│
├── tools/                     # 도구 정의
│   ├── __init__.py
│   ├── registry.py           # 도구 레지스트리
│   └── tools/                # 구체적인 도구들
│       ├── image_tools.py    # 이미지 분석 도구
│       ├── pipeline_tools.py # 기존 파이프라인 도구
│       ├── contact_tools.py  # Contact 전문가 특화 도구 (선택적)
│       └── ...               # 기타 전문가별 특화 도구
│
└── nodes/
    └── react/                # ReAct 노드 (서브그래프 사용)
        ├── __init__.py
        └── react_agent_node.py  # 서브그래프를 호출하는 노드
```

## 1. ReActState 정의

`src/state.py`에 추가할 상태 정의:

```python
from langchain_core.messages import BaseMessage

class ReActState(TypedDict):
    """
    ReAct 에이전트 상태 (LangGraph 메시지 기반)
    
    LangGraph의 prebuilt agent는 메시지 기반 상태를 사용합니다.
    """
    # 메시지 히스토리 (LangGraph 표준)
    messages: Annotated[List[BaseMessage], operator.add]
    
    # 추가 컨텍스트
    task: Optional[str]  # 수행할 작업 설명
    context: Optional[Dict[str, Any]]  # 컨텍스트 정보
    
    # 에러
    errors: Annotated[List[str], operator.add]
```

## 2. Gemini ChatModel 래퍼

**파일**: `src/agents/gemini_chatmodel.py`

Google Gemini를 LangChain ChatModel 인터페이스로 래핑하여 LangGraph와 통합합니다.

### 주요 기능

- LangChain ChatModel 인터페이스 구현
- Gemini Function Calling 지원
- 메시지 형식 변환 (LangChain ↔ Gemini)

### 핵심 메서드

- `_generate()`: 동기 생성
- `_convert_messages()`: LangChain 메시지를 Gemini 형식으로 변환
- `_convert_response_to_message()`: Gemini 응답을 AIMessage로 변환
- `_create_function_declarations()`: LangChain Tool을 Gemini Function Declaration로 변환

## 3. 도구 정의

### 3.1 이미지 분석 도구

**파일**: `src/tools/tools/image_tools.py`

- `ImageAnalyzerTool`: 이미지 형태학적 분석 (원형도, 고형도, 면적)
- `ImageEnhancerTool`: Real-ESRGAN 기반 이미지 향상

### 3.2 파이프라인 도구

**파일**: `src/tools/tools/pipeline_tools.py`

- `RunPreprocessingPipelineTool`: 기존 전처리 파이프라인을 도구로 제공
- `RunInvestigationPipelineTool`: 기존 조사 파이프라인을 도구로 제공

### 3.3 전문가별 특화 도구 (선택적)

**파일**: `src/tools/tools/contact_tools.py`, `tracking_tools.py`, etc.

각 전문가의 step 함수를 도구로 래핑:

- `AnalyzeLocationContextTool`: Contact 전문가 Step 1
- `AnalyzeSpectralPatternTool`: Contact 전문가 Step 2
- `AnalyzeDendriticPatternTool`: Tracking 전문가 Step 1
- 등등...

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

### 4.1 통합 ReAct 에이전트

**파일**: `src/agents/react_agent.py`

모든 도구를 사용하는 통합 ReAct 에이전트:

```python
def build_react_agent_graph() -> StateGraph:
    """ReAct 에이전트 서브그래프 빌드 (통합)"""
    llm = GeminiChatModel()
    tools = registry.get_tools()  # 모든 도구
    
    agent = create_react_agent(
        llm=llm,
        tools=tools,
        state_modifier="당신은 ReAct 패턴을 따르는 AI 에이전트입니다. "
                      "사용자의 작업을 수행하기 위해 필요한 도구를 사용하세요."
    )
    
    return agent
```

### 4.2 전문가별 ReAct 에이전트 (선택적)

**파일**: `src/agents/contact_react_agent.py`

각 전문가마다 특화된 ReAct 에이전트 생성:

```python
def build_contact_react_agent_graph() -> StateGraph:
    """
    Contact 전문가용 ReAct 에이전트 서브그래프
    
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

현재 프로젝트의 `_get_contact_graph()` 패턴과 동일하게 구현:

```python
_react_agent_graph = None
_contact_react_agent_graph = None
_graph_lock = threading.Lock()

def _get_react_agent_graph() -> StateGraph:
    """ReAct 에이전트 서브그래프를 싱글톤으로 반환 (Thread-safe)"""
    global _react_agent_graph
    if _react_agent_graph is None:
        with _graph_lock:
            if _react_agent_graph is None:
                _react_agent_graph = build_react_agent_graph()
    return _react_agent_graph
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

현재 프로젝트의 `node_contact` 패턴을 따릅니다:

```python
def react_agent_node(state: InvestigationState) -> Dict[str, Any]:
    """
    ReAct 에이전트 노드 (서브그래프 사용)
    
    현재 프로젝트의 node_contact 패턴을 따릅니다.
    """
    # 서브그래프 가져오기
    react_graph = _get_react_agent_graph()
    
    # 서브그래프 실행을 위한 상태 준비
    subgraph_state: ReActState = {
        "messages": state.get("messages", []),
        "task": state.get("task"),
        "context": state.get("context", {}),
        "errors": []
    }
    
    # 서브그래프 실행
    result = react_graph.invoke(subgraph_state)
    
    # 결과를 InvestigationState 형식으로 변환
    final_message = result.get("messages", [])[-1] if result.get("messages") else None
    
    return {
        "react_result": final_message.content if final_message else "",
        "errors": result.get("errors", [])
    }
```

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

### 7.2 서브그래프로 통합

기존 `build_investigation_graph()`에 ReAct 노드 추가:

```python
def build_investigation_graph_with_react() -> StateGraph:
    """조사 그래프에 ReAct 에이전트 노드 추가"""
    builder = StateGraph(InvestigationState)
    
    # 기존 전문가 노드들
    builder.add_node("contact", node_contact)
    # ...
    
    # ReAct 에이전트 노드 추가
    builder.add_node("react_agent", react_agent_node)
    
    # 조건부 라우팅으로 선택적 사용
    def route_after_experts(state: InvestigationState) -> str:
        if state.get("needs_react_agent", False):
            return "react_agent"
        return "chief_investigator"
    
    builder.add_conditional_edges(
        "contact",
        route_after_experts,
        {
            "react_agent": "react_agent",
            "chief_investigator": "chief_investigator"
        }
    )
    
    return builder.compile()
```

### 7.3 기존 파이프라인을 도구로 제공

ReAct 에이전트가 필요할 때 기존 파이프라인을 호출:

```python
class RunPreprocessingPipelineTool(BaseTool):
    """기존 전처리 파이프라인을 ReAct 도구로 제공"""
    
    def _run(self, image_path: str) -> str:
        graph = build_graph()  # 기존 그래프 사용
        result = graph.invoke(initial_state)
        return "전처리 완료..."
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

### 8.3 전문가별 ReAct 사용

```python
# Contact 전문가용 ReAct 에이전트 사용
contact_react_graph = build_contact_react_agent_graph()
result = contact_react_graph.invoke({
    "messages": [HumanMessage(content="접촉불량을 분석하세요")],
    "task": "접촉불량 분석",
    "context": {"image_path": "data/image.png"},
    "errors": []
})
```

### 8.4 기존 파이프라인과 통합

```python
# ReAct 에이전트가 자동으로 필요한 도구를 선택
# 예: "전처리 파이프라인을 실행하고 결과를 분석하세요"
# → ReAct가 run_preprocessing_pipeline 도구를 호출
```

## 9. LangGraph 권장 패턴 준수

### 9.1 서브그래프 패턴

- ✅ 서브그래프를 노드에서 호출하는 방식 (현재 프로젝트 패턴)
- ✅ 싱글톤 패턴으로 서브그래프 재사용
- ✅ Thread-safe 초기화

### 9.2 Prebuilt Agent 사용

- ✅ `create_react_agent` 사용 (LangGraph 권장)
- ✅ 자동으로 ReAct 패턴 구현
- ✅ 도구 호출 및 반복 로직 자동 처리

### 9.3 상태 관리

- ✅ 메시지 기반 상태 (LangGraph 표준)
- ✅ Annotated reducer 패턴 사용
- ✅ Partial State 반환

## 10. 구현 순서

1. **ReActState 정의** (`src/state.py`)
2. **Gemini ChatModel 래퍼** (`src/agents/gemini_chatmodel.py`)
3. **도구 정의** (`src/tools/tools/`)
   - 공통 도구 (image_tools.py, pipeline_tools.py)
   - 전문가별 특화 도구 (선택적)
4. **도구 레지스트리** (`src/tools/registry.py`)
5. **ReAct 서브그래프 빌더** (`src/agents/react_agent.py`)
   - 통합 ReAct 에이전트
   - 전문가별 ReAct 에이전트 (선택적)
6. **ReAct 노드** (`src/nodes/react/react_agent_node.py`)
7. **그래프 통합** (`src/graph_builder.py`)
8. **메인 통합** (`main.py`)

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

- `build_graph()`: 이미지 전처리 파이프라인 (고정 워크플로우)
- `build_investigation_graph()`: 멀티 에이전트 분석 (고정 워크플로우)
- `build_react_agent_graph()`: ReAct 에이전트 (동적 의사결정)

**모두 독립적으로 사용 가능하며, 필요시 통합 가능**

### 12.2 서브그래프 vs 독립 그래프

- **서브그래프로 사용**: 기존 파이프라인에 통합
- **독립 그래프로 사용**: 사용자 질문에 직접 응답

**두 방식 모두 지원하며, 용도에 따라 선택**

### 12.3 통합 vs 전문가별 ReAct

- **통합 ReAct**: 모든 도구 사용, 범용적
- **전문가별 ReAct**: 특화 도구만 사용, 정확도 향상

**용도에 따라 선택: 일반 질문은 통합, 전문가별 분석은 특화 ReAct**

### 12.4 도구 추가 방법

1. `BaseTool`을 상속받아 새 도구 클래스 생성
2. `ToolRegistry._initialize_tools()`에 추가
3. 자동으로 ReAct 에이전트에서 사용 가능

## 13. 다음 단계

1. 각 컴포넌트 구현
2. 단위 테스트 작성
3. 통합 테스트 수행
4. 문서화 및 예제 작성
5. 프로덕션 배포

---

**작성일**: 2025-01-XX  
**버전**: 1.1  
**상태**: 설계 완료, 구현 대기

