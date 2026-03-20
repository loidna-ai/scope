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
# from src.nodes.arbiter_node import node_arbiter  # [Disabled] 논쟁 시스템으로 교체
from src.nodes.common_nodes import hotspot_detector_node
from src.nodes.visualization_node import draw_annotation_node
from src.nodes.preprocessor_node import preprocess_hotspots_node  # [#5] 공유 전처리 노드
from src.edges.investigation_edges import add_investigation_edges
from src.graphs.contact_expert_graph import contact_expert_wrapper_node
# from src.graphs.aging_expert_graph import aging_expert_wrapper_node
# from src.graphs.deform_expert_graph import deform_expert_wrapper_node
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
    # builder.add_node("aging", aging_expert_wrapper_node)
    # builder.add_node("deform", deform_expert_wrapper_node)
    # builder.add_node("tracking", tracking_expert_wrapper_node)
    builder.add_node("necking", necking_expert_wrapper_node)

    # Arbiter 서브그래프 + Visualizer
    builder.add_node("arbiter", arbiter_expert_wrapper_node)
    builder.add_node("visualizer", draw_annotation_node)

    # 엣지 추가 (investigation_edges.py에서 preprocessor 경유 경로 정의)
    add_investigation_edges(builder)

    return builder.compile()

async def analyze_fire_evidence(payload_data: List[Any], output_dir: str = None) -> dict:
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
    
<<<<<<< HEAD
    from src.utils.io_utils import process_payload_images, cleanup_temporary_resources
    temp_image_paths = process_payload_images(payload_data)
    temp_image_path = temp_image_paths[0] if temp_image_paths else None
    
=======
    # [Memory Optimization]
    # Payload에서 이미지를 추출하여 임시 파일로 저장하고, State에는 경로만 전달
    from src.tools.experts.expert_utils import extract_image_from_payload, save_bytes_to_temp_file
    import config
    
    def _resize_image_if_needed(img_bytes: bytes, max_dim: int, quality: int) -> bytes:
        """이미지가 max_dim 초과 시 리사이즈 후 bytes 반환. 작을 경우 통과."""
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        w, h = img.size
        if max(w, h) <= max_dim:
            return img_bytes
        scale = max_dim / max(w, h)
        new_w, new_h = int(w * scale), int(h * scale)
        img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img_resized.save(buf, "JPEG", quality=quality, optimize=True)
        return buf.getvalue()
    
    image_data = extract_image_from_payload(payload_data)
    temp_image_path = None
    
    if image_data:
        try:
            # === [추가된 로직] 파이프라인 진입 전 리사이즈 ===
            if getattr(config, 'PRE_RESIZE_ENABLED', True):
                image_data = _resize_image_if_needed(
                    image_data, 
                    getattr(config, 'PRE_RESIZE_MAX_DIMENSION', getattr(config, 'HOTSPOT_MAX_IMAGE_DIMENSION', 2048)),
                    getattr(config, 'PRE_RESIZE_JPEG_QUALITY', 88)
                )
            # ===============================================

            temp_image_path = save_bytes_to_temp_file(image_data)
            logger.info(f"💾 [System] Initial Image Saved to: {temp_image_path}")
        except Exception as e:
            logger.error(f"⚠️ [System] Failed to process and save initial image: {e}")
>>>>>>> origin
    
    initial_state = {
        "payload": [],             # [Optimization] 바이너리 데이터 제거
        "image_path": temp_image_path,
        "image_paths": temp_image_paths,
        "hotspots": None,
        "preprocessed_hotspots": None,  # [#5] 전처리 결과 초기화
        "expert_reports": [],
        "expert_analysis_results": {},
        "expert_confidence_scores": {},
        "expert_evidence": {},
        "final_verdict": None,
        "arbiter_debate_messages": None,
        "errors": [],
        "visual_report_path": None,
        "output_dir": output_dir,
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
        "visual_report_path": result.get("visual_report_path"),
    }
    
    # 최종 결과 이미지 경로
    final_image_path = result.get("image_path") or temp_image_path
    if final_image_path:
        return_dict["image_path"] = final_image_path
    
    # 6. 임시 자원 정리 (I/O 로직 이관됨)
    cleanup_temporary_resources(
        temp_image_paths=temp_image_paths,
        final_image_path=final_image_path,
        preprocessed_hotspots=result.get("preprocessed_hotspots")
    )
    
    return return_dict
