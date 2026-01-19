"""
그래프 빌더 (Agent)
LangGraph StateGraph를 조립하고 컴파일합니다.

LangGraph 공식 문서 권장 구조:
- State: src/state.py에 정의
- Node: src/nodes/ 폴더에 정의
- Edge: src/edges/ 폴더에 정의
- Agent: 이 파일에서 노드와 엣지를 조합하여 그래프 생성 (agent.py가 공식 권장 이름)
- Subgraph: src/graphs/ 폴더의 {expert}_expert_graph.py에 정의, 래퍼 노드로 연결
"""
from typing import List, Any
from langgraph.graph import StateGraph
from src.state import InvestigationState
from src.nodes.arbiter_node import node_arbiter
from src.nodes.common_nodes import hotspot_detector_node
from src.nodes.visualization_node import draw_annotation_node
from src.edges.investigation_edges import add_investigation_edges
from src.graphs.contact_expert_graph import contact_expert_wrapper_node
from src.graphs.aging_expert_graph import aging_expert_wrapper_node
from src.graphs.deform_expert_graph import deform_expert_wrapper_node
from src.graphs.tracking_expert_graph import tracking_expert_wrapper_node
from src.graphs.necking_expert_graph import necking_expert_wrapper_node

def build_investigation_graph() -> StateGraph:
    """
    화재조사 멀티 에이전트 그래프 빌드
    
    그래프 구조:
    START → hotspot_detector (공통)
         → [contact, aging, deform, tracking, necking] (병렬)
         → chief_investigator → END
    
    Returns:
        컴파일된 멀티 에이전트 분석 그래프
    """
    builder = StateGraph(InvestigationState)
    
    # 공통 Hotspot Detector 노드 추가
    builder.add_node("hotspot_detector", hotspot_detector_node)
    
    # 전문가 래퍼 노드 추가 (ReAct 패턴 서브그래프를 InvestigationState와 연결)
    builder.add_node("contact", contact_expert_wrapper_node)
    builder.add_node("aging", aging_expert_wrapper_node)
    builder.add_node("deform", deform_expert_wrapper_node)
    builder.add_node("tracking", tracking_expert_wrapper_node)
    builder.add_node("necking", necking_expert_wrapper_node)
    
    # Arbiter Agent 노드 추가
    builder.add_node("chief_investigator", node_arbiter)
    
    # Visualization Node 추가
    builder.add_node("visualizer", draw_annotation_node)
    
    # 엣지 추가
    add_investigation_edges(builder)
    
    # Arbiter -> Visualizer -> END 연결 수정이 필요함
    # 기존 add_investigation_edges에서는 chief_investigator -> END 였을 것임.
    # 이를 수동으로 재설정하거나, edges 파일 수정 필요.
    # 여기서는 edges 파일 수정 없이, 그래프 빌더 레벨에서 덮어쓰기/추가 시도.
    # 하지만 langgraph는 edge 재정의를 경고할 수 있음.
    # 가장 깔끔한 방법은 src/edges/investigation_edges.py를 수정하는 것임.
    # 일단 여기서는 edge 추가를 시도.
    
    # 주의: add_investigation_edges 내부 구현을 모르므로, 
    # visualizer 연결은 edges 파일에서 처리하는 것이 맞음.
    # 따라서 이 파일에서는 add_node만 하고, edges 파일 수정을 별도로 진행해야 함.
    
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
    
    # [Memory Optimization]
    # Payload에서 이미지를 추출하여 임시 파일로 저장하고, State에는 경로만 전달
    from src.tools.experts.expert_utils import extract_image_from_payload, save_bytes_to_temp_file
    
    image_data = extract_image_from_payload(payload_data)
    temp_image_path = None
    
    if image_data:
        try:
            temp_image_path = save_bytes_to_temp_file(image_data)
            print(f"💾 [System] Initial Image Saved to: {temp_image_path}")
        except Exception as e:
            print(f"⚠️ [System] Failed to save initial image: {e}")
    
    initial_state = {
        "payload": [], # [Optimization] 바이너리 데이터 제거 (빈 리스트 전달)
        "image_path": temp_image_path, # 파일 경로 전달
        "hotspots": None,
        "expert_reports": [],
        "expert_analysis_results": {},
        "expert_confidence_scores": {},
        "expert_evidence": {},
        "final_verdict": None,
        "errors": [],
    }
    
    invoke_start_time = time.time()
    
    try:
        result = graph.invoke(initial_state)
    except Exception as e:
        
        raise
    finally:
        # [Memory Optimization] 임시 파일 정리 (visualization 완료 후)
        # visualization_node가 실행된 후에 정리하므로, 여기서는 정리하지 않음.
        # 대신, 임시 파일은 OS가 자동으로 정리하거나, 명시적으로 정리하려면
        # visualization_node 실행 후에 정리하는 것이 좋음.
        # 하지만 여러 노드가 공유하므로, 여기서는 정리하지 않고 유지.
        # 필요시 main.py나 호출 측에서 정리할 수 있도록 경로를 반환하는 것도 고려 가능.
        pass
    
    invoke_duration_ms = (time.time() - invoke_start_time) * 1000
    
    return {
        "final_verdict": result.get("final_verdict", "분석 실패"),
        "expert_reports": result.get("expert_reports", []),
        "errors": result.get("errors", []),
        "image_path": temp_image_path  # 호출 측에서 정리할 수 있도록 경로 반환
    }
