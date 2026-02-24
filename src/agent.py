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
from src.nodes.preprocessor_node import preprocess_hotspots_node  # [#5] 공유 전처리 노드
from src.edges.investigation_edges import add_investigation_edges
from src.graphs.contact_expert_graph import contact_expert_wrapper_node
from src.graphs.aging_expert_graph import aging_expert_wrapper_node
from src.graphs.deform_expert_graph import deform_expert_wrapper_node
# from src.graphs.tracking_expert_graph import tracking_expert_wrapper_node
from src.graphs.necking_expert_graph import necking_expert_wrapper_node
from src.graphs.arbiter_expert_graph import arbiter_expert_wrapper_node
from src.utils.logging_config import setup_logger

logger = setup_logger("agent")

def build_investigation_graph() -> StateGraph:
    """
    화재조사 멀티 에이전트 그래프 빌드
    
    그래프 구조:
    START → hotspot_detector (공통)
         → [contact, deform, necking] (병렬, Map-Reduce Pattern만 사용)
         → chief_investigator → END
    
    Note: Aging, Tracking은 작업 미완료로 비활성화됨
    
    Returns:
        컴파일된 멀티 에이전트 분석 그래프
    """
    builder = StateGraph(InvestigationState)
    
    # 공통 Hotspot Detector 노드 추가
    builder.add_node("hotspot_detector", hotspot_detector_node)

    # [#5] 공유 전처리 노드 (Crop + Enhancement + Classification 1회)
    builder.add_node("preprocessor", preprocess_hotspots_node)

    # 전문가 래퍼 노드 추가 (Map-Reduce Pattern)
    builder.add_node("contact", contact_expert_wrapper_node)
    builder.add_node("aging", aging_expert_wrapper_node)
    builder.add_node("deform", deform_expert_wrapper_node)
    # builder.add_node("tracking", tracking_expert_wrapper_node)
    builder.add_node("necking", necking_expert_wrapper_node)

    # Arbiter 서브그래프 + Visualizer
    builder.add_node("arbiter", arbiter_expert_wrapper_node)
    builder.add_node("visualizer", draw_annotation_node)

    # 엣지 추가 (investigation_edges.py에서 preprocessor 경유 경로 정의)
    add_investigation_edges(builder)

    return builder.compile()

async def analyze_fire_evidence(payload_data: List[Any]) -> dict:
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
        "payload": [],             # [Optimization] 바이너리 데이터 제거
        "image_path": temp_image_path,
        "hotspots": None,
        "preprocessed_hotspots": None,  # [#5] 전처리 결과 초기화
        "expert_reports": [],
        "expert_analysis_results": {},
        "expert_confidence_scores": {},
        "expert_evidence": {},
        "final_verdict": None,
        "arbiter_debate_messages": None,
        "errors": [],
    }
    
    invoke_start_time = time.time()

    try:
        result = await graph.ainvoke(initial_state)
    except Exception:
        raise
    logger.info(f"Graph execution: {(time.time() - invoke_start_time)*1000:.0f}ms")


    # 반환값 준비 (image_path는 graph 결과에서 가져옴)
    arbiter_debate_messages = result.get("arbiter_debate_messages")
    if arbiter_debate_messages is None:
        arbiter_debate_messages = []
    
    return_dict = {
        "final_verdict": result.get("final_verdict", "분석 실패"),
        "final_verdict_structured": result.get("final_verdict_structured"),  # 구조화된 최종 판정 데이터
        "expert_reports": result.get("expert_reports", []),
        "arbiter_debate_messages": arbiter_debate_messages,  # 아비터 토론 메시지 추가 (None 체크 완료)
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
    
    # [OOM/Resource Leak Fix] 전처리된 핫스팟의 모든 임시 ROI 이미지 삭제
    preprocessed_hotspots = result.get("preprocessed_hotspots", [])
    if preprocessed_hotspots:
        try:
            import tempfile
            temp_dir = tempfile.gettempdir()
            temp_dir_normalized = os.path.normpath(temp_dir).lower()
            for hp in preprocessed_hotspots:
                roi_path = hp.get("roi_image_path")
                # 메인 이미지나 원본 임시파일과 경로가 다르고 실제로 존재하는 경우
                if roi_path and roi_path != final_image_path and roi_path != temp_image_path and os.path.exists(roi_path):
                    roi_path_normalized = os.path.normpath(roi_path).lower()
                    if roi_path_normalized.startswith(temp_dir_normalized):
                        os.remove(roi_path)
                        logger.debug(f"전처리 임시 파일 정리 완료: {roi_path}")
        except Exception as e:
            logger.warning(f"전처리 임시 파일 정리 실패: {e}")
    
    return return_dict
