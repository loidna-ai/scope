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
import os
from langgraph.graph import StateGraph
from src.state import InvestigationState
# from src.nodes.arbiter_node import node_arbiter  # [Disabled] 논쟁 시스템으로 교체
from src.nodes.common_nodes import hotspot_detector_node
from src.nodes.visualization_node import draw_annotation_node
from src.edges.investigation_edges import add_investigation_edges
from src.graphs.contact_expert_graph import contact_expert_wrapper_node
# from src.graphs.aging_expert_graph import aging_expert_wrapper_node  # [Disabled] Loop Pattern - Map-Reduce만 사용
from src.graphs.deform_expert_graph import deform_expert_wrapper_node
# from src.graphs.tracking_expert_graph import tracking_expert_wrapper_node  # [Disabled] Loop Pattern - Map-Reduce만 사용
from src.graphs.necking_expert_graph import necking_expert_wrapper_node
from src.graphs.arbiter_expert_graph import arbiter_expert_wrapper_node  # [New] 논쟁 시스템 서브그래프
from src.utils.logging_config import setup_logger

logger = setup_logger("agent")

def build_investigation_graph() -> StateGraph:
    """
    화재조사 멀티 에이전트 그래프 빌드
    
    그래프 구조:
    START → hotspot_detector (공통)
         → [contact, deform, necking] (병렬, Map-Reduce Pattern만 사용)
         → chief_investigator → END
    
    Note: Aging, Tracking은 Loop Pattern이므로 주석처리됨
    
    Returns:
        컴파일된 멀티 에이전트 분석 그래프
    """
    builder = StateGraph(InvestigationState)
    
    # 공통 Hotspot Detector 노드 추가
    builder.add_node("hotspot_detector", hotspot_detector_node)
    
    # 전문가 래퍼 노드 추가 (Map-Reduce Pattern만 사용)
    builder.add_node("contact", contact_expert_wrapper_node)
    # builder.add_node("aging", aging_expert_wrapper_node)  # [Disabled] Loop Pattern
    builder.add_node("deform", deform_expert_wrapper_node)
    # builder.add_node("tracking", tracking_expert_wrapper_node)  # [Disabled] Loop Pattern
    builder.add_node("necking", necking_expert_wrapper_node)
    
    # Arbiter Expert 서브그래프 추가 (다른 전문가와 동일한 패턴)
    builder.add_node("arbiter", arbiter_expert_wrapper_node)  # [Changed] 서브그래프 패턴으로 변경
    
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
        "arbiter_debate_messages": None,  # 아비터 토론 메시지 초기화
        "errors": [],
    }
    
    invoke_start_time = time.time()
    
    # #region agent log
    import json
    from pathlib import Path
    log_path = Path(__file__).parent.parent / ".cursor" / "debug.log"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"agent.py:119","message":"graph.invoke entry","data":{"initial_state_keys":list(initial_state.keys())},"timestamp":int(time.time()*1000)})+"\n")
    except: pass
    # #endregion
    
    try:
        result = graph.invoke(initial_state)
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"agent.py:125","message":"graph.invoke completed","data":{"result_keys":list(result.keys()) if result else None,"has_final_verdict":bool(result.get("final_verdict")),"has_arbiter_debate_messages":"arbiter_debate_messages" in result if result else False,"arbiter_debate_messages_count":len(result.get("arbiter_debate_messages", [])) if result else 0,"arbiter_debate_messages_type":type(result.get("arbiter_debate_messages")).__name__ if result and result.get("arbiter_debate_messages") else "None"},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
    except Exception as e:
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"agent.py:131","message":"graph.invoke exception","data":{"error_type":type(e).__name__,"error_message":str(e)},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        raise
    invoke_duration_ms = (time.time() - invoke_start_time) * 1000
    
    # 반환값 준비 (image_path는 graph 결과에서 가져옴)
    return_dict = {
        "final_verdict": result.get("final_verdict", "분석 실패"),
        "final_verdict_structured": result.get("final_verdict_structured"),  # 구조화된 최종 판정 데이터
        "expert_reports": result.get("expert_reports", []),
        "arbiter_debate_messages": result.get("arbiter_debate_messages", []),  # 아비터 토론 메시지 추가
        "errors": result.get("errors", []),
    }
    
    # image_path는 graph 결과에서 가져오거나, 없으면 초기 temp_image_path 사용
    # (graph 내부에서 hotspot_detector_node가 업데이트한 image_path가 우선)
    final_image_path = result.get("image_path") or temp_image_path
    if final_image_path:
        return_dict["image_path"] = final_image_path
    
    # 임시 파일 정리: graph 실행 완료 후 정리
    # 주의: graph 결과의 image_path와 다른 경우에만 정리 (graph 내부에서 사용 중일 수 있음)
    if temp_image_path:
        should_cleanup = False
        try:
            # 경로 비교: os.path.samefile 사용 (심볼릭 링크, 대소문자 차이 등 고려)
            if final_image_path and os.path.exists(temp_image_path) and os.path.exists(final_image_path):
                if os.path.samefile(temp_image_path, final_image_path):
                    # 같은 파일이면 정리하지 않음
                    should_cleanup = False
                else:
                    # 다른 파일이면 정리 가능
                    should_cleanup = True
            elif final_image_path and temp_image_path != final_image_path:
                # final_image_path가 있지만 samefile 비교 실패 시 문자열 비교
                should_cleanup = True
            elif not final_image_path:
                # final_image_path가 없으면 정리 가능
                should_cleanup = True
        except (OSError, ValueError):
            # samefile 실패 시 (파일이 없거나 경로 문제) 문자열 비교로 폴백
            if not final_image_path or temp_image_path != final_image_path:
                should_cleanup = True
        
        if should_cleanup:
            try:
                import tempfile
                temp_dir = tempfile.gettempdir()
                # Windows 경로 정규화 (대소문자 구분 없이 비교)
                temp_path_normalized = os.path.normpath(temp_image_path).lower()
                temp_dir_normalized = os.path.normpath(temp_dir).lower()
                
                if temp_path_normalized.startswith(temp_dir_normalized) and os.path.exists(temp_image_path):
                    os.remove(temp_image_path)
                    logger.debug(f"임시 파일 정리 완료: {temp_image_path}")
            except Exception as e:
                logger.warning(f"임시 파일 정리 실패: {e}")
    
    return return_dict
