"""
그래프 공통 유틸리티 모듈

각 전문가 그래프에서 중복으로 사용되는 라우팅, 임시 파일 정리,
래퍼 노드 생성 등의 공통 기능을 제공합니다.
"""
import os
import asyncio
import traceback
from typing import Dict, Any, Optional, Literal, List, Union, Callable

from langgraph.graph import StateGraph
from langgraph.types import Send

from config import TOP_N_HOTSPOTS, MIN_SEVERITY_FOR_ANALYSIS
from src.state import InvestigationState
from src.utils.logging_config import setup_logger
from src.tools.experts.expert_utils import (
    extract_image_from_payload,
    save_bytes_to_temp_file
)

logger = setup_logger(__name__)


def distribute_work_generic(state: Dict[str, Any], expert_name: str) -> Union[str, List[Send]]:
    """
    Fan-out: Distribute hotspots to parallel workers using Send API
    
    [#5 Preprocessor] preprocessed_hotspots가 있으면 전처리 결과를 우선 사용.
    
    Args:
        state: 모델 상태 딕셔너리
        expert_name: 로깅용 전문가 이름 (예: "Contact", "Deform", "Necking", "Aging", "Tracking")
        
    Returns:
        - List[Send]: If hotspots exist, fan-out to workers
        - str: If no hotspots, skip to verdict node (노드 이름은 expert_name에 따라 결정)
    """
    # 모든 전문가 그래프가 "supervisor_verdict" 노드 사용 (Gen 2 통일)
    verdict_node_name = "supervisor_verdict"
    
    analysis_status = state.get("analysis_status")
    if analysis_status == "NO_HOTSPOTS_DETECTED":
        logger.info(f"{expert_name} Expert: No hotspots detected, skipping analysis")
        return verdict_node_name
    if analysis_status == "ERROR":
        logger.warning(f"{expert_name} Expert: Detector returned ERROR status, skipping analysis")
        return verdict_node_name

    image_path = state.get("image_path")

    # [#5] preprocessed_hotspots 우선 사용 (이미 Crop+Classify 완료)
    preprocessed = state.get("preprocessed_hotspots")
    if preprocessed:
        selected_hotspots = preprocessed
        logger.info(
            f"{expert_name} Expert: Using {len(selected_hotspots)} pre-processed hotspot(s)"
        )
    else:
        # Fallback: preprocessor_node가 없는 경우 기존 로직
        hotspots = state.get("hotspots") or []
        valid_hotspots = [
            h for h in hotspots
            if h.get("severity_score", 0) >= MIN_SEVERITY_FOR_ANALYSIS
        ]
        if not valid_hotspots:
            print(f"\n[Done] [{expert_name} Distribute Work] 처리할 Hotspot이 없습니다.")
            return verdict_node_name
        selected_hotspots = sorted(
            valid_hotspots, key=lambda x: x.get("severity_score", 0), reverse=True
        )[:TOP_N_HOTSPOTS]

    print(f"\n[Distribute] [{expert_name} Distribute] {len(selected_hotspots)}개 Worker 병렬 분산")
    print(f"   선택된 IDs: {[h.get('id') for h in selected_hotspots]}")

    return [
        Send(
            "analyze_hotspot_worker",
            {
                "current_hotspot": hotspot,
                "image_path": image_path,
            }
        )
        for hotspot in selected_hotspots
    ]


def route_supervisor_decision_generic(state: Dict[str, Any]) -> Literal["debate", "finalize"]:
    """
    Supervisor 결과에 따라 Debate 필요 여부 결정
    """
    debate_context = state.get("debate_context")
    
    if debate_context and debate_context.get("requires_debate"):
        logger.info("Router: Supervisor requested debate -> Proceeding to Analyst")
        return "debate"
    
    logger.info("Router: Supervisor Fast Path verdict -> Proceeding to Finalize")
    return "finalize"


def route_verdict_debate_generic(state: Dict[str, Any]) -> Literal["back_to_analyst", "finalize"]:
    """
    Verdict Debate Supervisor (흐름 제어)
    - Critic이 is_approved=True → finalize
    - Critic이 "시스템 오류" → finalize (무한 루프 방지)
    - 3턴 초과 → finalize (timeout)
    - 그 외 → back_to_analyst (재검토)
    """
    debate_iter = state.get("debate_iteration", 0)
    MAX_ITERATIONS = 3

    # Pydantic 객체 우선 사용
    critique_result = state.get("critique_result")

    # 1. Critic 합의 체크 (is_approved bool 직접 체크)
    if critique_result and critique_result.is_approved:
        logger.info("Debate Supervisor: Critic agreed (is_approved=True). Proceeding to finalize.")
        return "finalize"

    # 2. 시스템 오류 즉시 탈출
    if critique_result and getattr(critique_result, "objection_type", None) == "시스템 오류":
        logger.warning("Debate Supervisor: Critic reported system error. Forcing finalize.")
        return "finalize"

    # 3. Timeout
    if debate_iter >= MAX_ITERATIONS:
        logger.warning(f"Debate Supervisor: Max iterations ({MAX_ITERATIONS}) reached. Forcing finalize.")
        return "finalize"

    # 4. 계속 토론
    logger.info(f"Debate Supervisor: Debate continues (Round {debate_iter + 1}/{MAX_ITERATIONS})")
    return "back_to_analyst"


def cleanup_temp_files(
    temp_image_path: Optional[str], 
    final_state: Optional[Dict[str, Any]],
    cleanup_original: bool = True,
    cleanup_roi: bool = False
):
    """
    임시 파일 정리 공통 함수
    
    Args:
        temp_image_path: 원본 이미지 경로
        final_state: 최종 상태 (ROI 경로 추출용)
        cleanup_original: True이면 원본 임시 파일 삭제
        cleanup_roi: True이면 ROI 파일 삭제. **주의**: ROI는 preprocessed_hotspots에서
            공유되므로, 각 전문가 래퍼에서는 False로 호출해야 함. (다른 전문가의 Debate/Critic이
            아직 사용 중일 수 있음) ROI 정리는 메인 그래프 완료 후 1회만 수행 권장.
    """
    # 1. 원본 임시 파일 삭제 (cleanup_original=True일 때만)
    if cleanup_original and temp_image_path and os.path.exists(temp_image_path):
        try:
            os.remove(temp_image_path)
        except Exception:
            pass

    if not final_state or not cleanup_roi:
        return

    # 2. ROI 파일 정리 (cleanup_roi=True일 때만 — 공유 파일이므로 전문가 래퍼에서는 건너뜀)
    analysis_results = final_state.get("analysis_results", [])
    for res in analysis_results:
        roi_path = res.get("roi_image_path")
        if roi_path and roi_path != temp_image_path and os.path.exists(roi_path):
            try:
                os.remove(roi_path)
            except Exception:
                pass
    
    # 3. State에 마지막으로 남아있는 ROI 경로 정리 (Fallback)
    last_roi_path = final_state.get("roi_image_path")
    if last_roi_path and last_roi_path != temp_image_path and os.path.exists(last_roi_path):
        try:
            os.remove(last_roi_path)
        except Exception:
            pass


def create_expert_wrapper_node(
    expert_name: str,
    expert_id: str,
    build_graph_fn: Callable[[], Any],
    default_initial_state_factory: Callable[..., Dict[str, Any]]
):
    """
    제네릭 전문가 래퍼 노드 생성 함수
    
    Args:
        expert_name: 전문가 표시 이름 (예: "Contact", "Deform")
        expert_id: 결과 딕셔너리에 사용할 키 (예: "contact", "deform")
        build_graph_fn: 서브그래프를 빌드하는 함수
        default_initial_state_factory: 초기 상태를 생성하는 팩토리 함수. 
            signature: (temp_image_path, hotspots, preprocessed_hotspots, **kwargs) -> dict
            
    Returns:
        InvestigationState를 받아 실행 결과를 반환하는 래퍼 노드 함수
    """
    async def wrapper_node(state: InvestigationState) -> Dict[str, Any]:
        temp_image_path = None
        final_state = None
        try:
            # [Memory Optimization] Shared Image Path Check
            shared_image_path = state.get("image_path")
            should_cleanup_input = False
            
            if shared_image_path and os.path.exists(shared_image_path):
                temp_image_path = shared_image_path
            else:
                image_data = extract_image_from_payload(state.get("payload", []))
                if image_data is None:
                    return {
                        "errors": [f"{expert_name} 전문가: 이미지를 추출할 수 없습니다."],
                        "expert_reports": [],
                        "expert_analysis_results": {},
                        "expert_confidence_scores": {},
                        "expert_evidence": {}
                    }
                temp_image_path = save_bytes_to_temp_file(image_data)
                should_cleanup_input = True
            
            # InvestigationState에서 공통 데이터 읽기
            hotspots = state.get("hotspots", [])
            preprocessed_hotspots = state.get("preprocessed_hotspots")
            
            # 팩토리 함수를 통해 초기 상태 생성
            initial_state = default_initial_state_factory(
                temp_image_path=temp_image_path,
                hotspots=hotspots,
                preprocessed_hotspots=preprocessed_hotspots
            )
            
            graph = build_graph_fn()
            
            logger.info(f"{expert_name} Expert: Starting analysis with streaming...")
            
            async def run_with_streaming():
                """Streaming으로 실행하며 진행 상황 출력.
                stream_mode='values'로 전체 상태 수신 (analysis_results 포함).
                stream_mode='updates'는 노드별 delta만 반환하여 analysis_results 누락됨.
                """
                final_st = None
                try:
                    async for event in graph.astream(
                        initial_state,
                        config={
                            "recursion_limit": 50,
                            "max_concurrency": 3  # 동시 실행 worker 제한
                        },
                        stream_mode="values"  # 전체 상태 스트림 (analysis_results 포함)
                    ):
                        # values 모드: 각 chunk가 스텝 완료 후 전체 상태
                        if isinstance(event, tuple):
                            _, chunk = event
                        else:
                            chunk = event
                        if chunk:
                            final_st = chunk
                            # 진행 상황: updates 대신 state 키로 추론
                            if isinstance(chunk, dict) and "verdict_report" in chunk:
                                print(f"  ✓ [{expert_name}] Completed: verdict_finalize")
                            elif isinstance(chunk, dict) and any(k in chunk for k in ("preliminary_assessments", "analysis_results")):
                                n = len(chunk.get("analysis_results", []))
                                if n > 0:
                                    print(f"  ✓ [{expert_name}] Completed: analyze_hotspot_worker (x{n})")
                except Exception:
                    raise
                return final_st
            
            # wrapper_node가 async def이므로 직접 await 호출
            final_state = await run_with_streaming()
            
            # 결과 추출
            if final_state is None:
                verdict_report = ""
                verdict_confidence = 0
                verdict_result = {}
                analysis_results = []
            else:
                verdict_report = final_state.get("verdict_report", "")
                verdict_confidence = final_state.get("verdict_confidence", 0)
                verdict_result = final_state.get("verdict_result", {})
                analysis_results = final_state.get("analysis_results", [])
            
            # 증거 수집 (Top 1 기준)
            evidence = []
            if verdict_result:
                # visual_description 필드 이름 호환성 (Deform, Necking에서는 visual_observation을 사용하기도 함)
                visual_desc = verdict_result.get(
                    "visual_description", 
                    verdict_result.get("visual_observation", "")
                )
                verdict = verdict_result.get("verdict", "")
                if verdict:
                    evidence.append({
                        "evidence": verdict,
                        "details": visual_desc
                    })
            
            return {
                "expert_reports": [verdict_report] if verdict_report else ["분석 결과 없음"],
                "expert_analysis_results": {
                    expert_id: {
                        "multi_hotspot_results": analysis_results,
                        "final_verdict_result": verdict_result
                    }
                },
                "expert_confidence_scores": {expert_id: verdict_confidence},
                "expert_evidence": {expert_id: evidence}
            }
        except Exception as e:
            print(f"\n[ERROR] {expert_name} Expert Wrapper Exception: {str(e)}")
            traceback.print_exc()
            return {
                "errors": [f"{expert_name} 전문가 오류: {str(e)}"],
                "expert_reports": [],
                "expert_analysis_results": {},
                "expert_confidence_scores": {},
                "expert_evidence": {}
            }
        finally:
            if final_state:
                cleanup_temp_files(
                    temp_image_path, 
                    final_state, 
                    cleanup_original=should_cleanup_input,
                    cleanup_roi=False  # ROI는 공유 파일 — Debate/Critic이 사용 중일 수 있음
                )

    return wrapper_node
