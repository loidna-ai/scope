"""
그래프 빌더 (Agent)
LangGraph StateGraph를 조립하고 컴파일합니다.

LangGraph 공식 문서 권장 구조:
- State: src/state.py에 정의
- Node: src/nodes/ 폴더에 정의
- Edge: src/edges/ 폴더에 정의
- Agent: 이 파일에서 노드와 엣지를 조합하여 그래프 생성 (agent.py가 공식 권장 이름)
- Subgraph: src/graphs/ 폴더의 {expert}_expert_graph.py에 정의, 래퍼 노드로 연결

ReAct 패턴:
- 각 전문가 서브그래프는 순수 ReAct 패턴(agent <-> tools 루프)을 사용
- 래퍼 노드를 통해 InvestigationState와 연결
"""
from typing import List, Any
from langgraph.graph import StateGraph
from src.state import InvestigationState, GraphState
from src.nodes.arbiter_node import node_arbiter
from src.edges.investigation_edges import add_investigation_edges
from src.edges.preprocessing_edges import add_preprocessing_edges
from src.graphs.contact_expert_graph import contact_expert_wrapper_node
from src.graphs.dielectric_expert_graph import dielectric_expert_wrapper_node
from src.graphs.mechanical_expert_graph import mechanical_expert_wrapper_node
from src.graphs.tracking_expert_graph import tracking_expert_wrapper_node
from src.graphs.strand_fracture_expert_graph import strand_fracture_expert_wrapper_node

def build_graph() -> StateGraph:
    """
    이미지 전처리 파이프라인 그래프 빌드
    
    그래프 구조:
    START → load → crop → enhance → [filter, metrics] (병렬) → packaging → END
    
    Returns:
        컴파일된 전처리 파이프라인 그래프
    """
    # 지연 import로 순환 import 방지
    from src.nodes.load import load_node
    from src.nodes.crop import crop_node
    from src.nodes.filter import filter_node
    from src.nodes.metrics import metrics_node
    from src.nodes.packaging import packaging_node
    
    # enhancement_node는 선택적 (Real-ESRGAN이 없을 수 있음)
    try:
        from src.nodes.enhancement import enhancement_node
        has_enhancement = True
    except ImportError:
        has_enhancement = False
    
    builder = StateGraph(GraphState)
    
    # 노드 추가
    builder.add_node("load", load_node)
    builder.add_node("crop", crop_node)
    if has_enhancement:
        builder.add_node("enhance", enhancement_node)
    builder.add_node("filter", filter_node)
    builder.add_node("metrics", metrics_node)
    builder.add_node("packaging", packaging_node)
    
    # 엣지 추가
    add_preprocessing_edges(builder, has_enhancement=has_enhancement)
    
    return builder.compile()

def build_investigation_graph() -> StateGraph:
    """
    화재조사 멀티 에이전트 그래프 빌드 (ReAct 패턴)
    
    각 전문가 서브그래프는 순수 ReAct 패턴을 사용합니다:
    - START → agent <-> tools (루프) → Final Answer
    - LLM이 자유롭게 Step 도구와 이미지 편집 도구를 선택
    - 래퍼 노드를 통해 InvestigationState와 연결
    
    그래프 구조:
    START → [contact, dielectric, mechanical, tracking, strand_fracture] (병렬)
         → chief_investigator → END
    
    Returns:
        컴파일된 그래프
    """
    builder = StateGraph(InvestigationState)
    
    # 전문가 래퍼 노드 추가 (ReAct 패턴 서브그래프를 InvestigationState와 연결)
    builder.add_node("contact", contact_expert_wrapper_node)
    builder.add_node("dielectric", dielectric_expert_wrapper_node)
    builder.add_node("mechanical", mechanical_expert_wrapper_node)
    builder.add_node("tracking", tracking_expert_wrapper_node)
    builder.add_node("strand_fracture", strand_fracture_expert_wrapper_node)
    
    # Arbiter Agent 노드 추가
    builder.add_node("chief_investigator", node_arbiter)
    
    # 엣지 추가
    add_investigation_edges(builder)
    
    return builder.compile()

def build_investigation_graph_with_react() -> StateGraph:
    """
    화재조사 멀티 에이전트 그래프 빌드 (병렬 모드)
    
    각 전문가 서브그래프는 순수 ReAct 패턴을 사용합니다:
    - START → agent <-> tools (루프) → Final Answer
    - LLM이 자유롭게 Step 도구와 이미지 편집 도구를 선택
    - 래퍼 노드를 통해 InvestigationState와 연결
    
    그래프 구조:
    START → [contact, dielectric, mechanical, tracking, strand_fracture] (병렬)
         → chief_investigator → END
    
    Returns:
        컴파일된 그래프
    """
    builder = StateGraph(InvestigationState)
    
    # 전문가 래퍼 노드 추가 (ReAct 패턴 서브그래프를 InvestigationState와 연결)
    builder.add_node("contact", contact_expert_wrapper_node)
    builder.add_node("dielectric", dielectric_expert_wrapper_node)
    builder.add_node("mechanical", mechanical_expert_wrapper_node)
    builder.add_node("tracking", tracking_expert_wrapper_node)
    builder.add_node("strand_fracture", strand_fracture_expert_wrapper_node)
    
    # Arbiter Agent 노드 추가
    builder.add_node("chief_investigator", node_arbiter)
    
    # 엣지 추가 (일반 모드와 동일 - 5명 전문가만)
    add_investigation_edges(builder)
    
    return builder.compile()

def analyze_fire_evidence(payload_data: List[Any]) -> dict:
    """
    화재 증거물 분석 (외부 호출용)
    
    Args:
        payload_data: LLM 입력 데이터 (이미지 + 텍스트)
    
    Returns:
        {
            "final_verdict": str,  # 최종 결론
            "expert_reports": List[str],  # 전문가 리포트 리스트
            "errors": List[str]  # 에러 메시지 리스트
        }
    """
    import time
    
    graph = build_investigation_graph()
    
    initial_state = {
        "payload": payload_data,
        "expert_reports": [],
        "expert_analysis_results": {},  # Annotated[dict, merge_dicts]이므로 빈 dict로 초기화
        "expert_confidence_scores": {},  # Annotated[dict, merge_dicts]이므로 빈 dict로 초기화
        "expert_evidence": {},  # Annotated[dict, merge_dicts]이므로 빈 dict로 초기화
        "final_verdict": None,
        "errors": [],
        # 각 서브그래프별 독립 캐시 초기화
        "contact_cached_image_data": None,
        "dielectric_cached_image_data": None,
        "mechanical_cached_image_data": None,
        "tracking_cached_image_data": None,
        "strand_fracture_cached_image_data": None
    }
    
    invoke_start_time = time.time()
    
    try:
        result = graph.invoke(initial_state)
    except Exception as e:
        
        raise
    invoke_duration_ms = (time.time() - invoke_start_time) * 1000
    
    return {
        "final_verdict": result.get("final_verdict", "분석 실패"),
        "expert_reports": result.get("expert_reports", []),
        "errors": result.get("errors", [])
    }
