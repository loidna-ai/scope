"""
Necking 전문가 서브그래프 빌더 (Map-Reduce Pattern with Send API)
"""
# Standard library imports
import os
import asyncio
import traceback
from typing import Dict, Any, Optional, Literal, List, Union

# Third-party imports
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

# Local imports
from config import TOP_N_HOTSPOTS
from src.state import InvestigationState
from src.utils.logging_config import setup_logger
from src.nodes.necking_nodes import (
    NeckingExpertState,
    WorkerState,
    analyze_hotspot_worker,
    supervisor_verdict,
    verdict_analyst_node,
    verdict_critic_node,
    verdict_finalize_node
)

logger = setup_logger(__name__)
from src.tools.experts.expert_utils import (
    extract_image_from_payload,
    save_bytes_to_temp_file
)


# ===== Send API Fan-Out Function =====

def distribute_work(state: NeckingExpertState) -> Union[str, List[Send]]:
    """
    Fan-out: Distribute hotspots to parallel workers using Send API
    
    Returns:
        - List[Send]: If hotspots exist, fan-out to workers
        - str: If no hotspots, skip to supervisor
    """
    # [Fast Path] analysis_status 체크 (빠른 종료)
    analysis_status = state.get("analysis_status")
    if analysis_status == "NO_HOTSPOTS_DETECTED":
        logger.info("Necking Expert: No hotspots detected by detector, skipping analysis")
        return "supervisor_verdict"
    if analysis_status == "ERROR":
        logger.warning("Necking Expert: Detector returned ERROR status, skipping analysis")
        return "supervisor_verdict"
    
    hotspots = state.get("hotspots") or []  # None-safe: None일 경우 빈 리스트로 처리
    image_path = state.get("image_path")
    
    # Filter and sort hotspots (Top-N Selection Logic)
    # [Config] severity_score 50 미만은 분석 가치가 낮으므로 제외
    valid_hotspots = [h for h in hotspots if h.get("severity_score", 0) >= 50]
    
    if not valid_hotspots:
        print("\n🏁 [Distribute Work] 처리할 Hotspot이 없습니다.")
        return "supervisor_verdict"
    
    # Sort by severity and take Top-N
    sorted_hotspots = sorted(
        valid_hotspots,
        key=lambda x: x.get("severity_score", 0),
        reverse=True
    )
    selected_hotspots = sorted_hotspots[:TOP_N_HOTSPOTS]
    
    print(f"\n🚀 [Distribute Work] {len(selected_hotspots)}개 Worker에 병렬 분산 (Top-{TOP_N_HOTSPOTS})")
    print(f"   선택된 Hotspot IDs: {[h.get('id') for h in selected_hotspots]}")
    
    # Send API: Create parallel worker invocations
    return [
        Send(
            "analyze_hotspot_worker",
            {
                "current_hotspot": hotspot,
                "image_path": image_path
            }
        )
        for hotspot in selected_hotspots
    ]


# ===== Conditional Routing Functions =====

def route_supervisor_decision(state: NeckingExpertState) -> Literal["debate", "finalize"]:
    """
    Supervisor 결과에 따라 Debate 필요 여부 결정
    """
    debate_context = state.get("debate_context")
    
    if debate_context and debate_context.get("requires_debate"):
        logger.info("Router: Supervisor requested debate -> Proceeding to Analyst")
        return "debate"
    
    logger.info("Router: Supervisor Fast Path verdict -> Proceeding to Finalize")
    return "finalize"


def route_verdict_debate(state: NeckingExpertState) -> Literal["back_to_analyst", "finalize"]:
    """
    Verdict Debate Supervisor (흐름 제어)
    - Critic이 is_approved=True → finalize
    - 3턴 초과 → finalize (timeout)
    - 그 외 → back_to_analyst (재검토)
    """
    debate_iter = state.get("debate_iteration", 0)
    MAX_ITERATIONS = 3
    
    # 🔥 Pydantic 객체 우선 사용 (Legacy 문자열 로직 제거)
    critique_result = state.get("critique_result")

    # 1. Critic 합의 체크 (is_approved bool 직접 체크)
    if critique_result and critique_result.is_approved:
        logger.info("Debate Supervisor: Critic agreed (is_approved=True). Proceeding to finalize.")
        return "finalize"
    
    # 2. Timeout
    if debate_iter >= MAX_ITERATIONS:
        logger.warning(f"Debate Supervisor: Max iterations ({MAX_ITERATIONS}) reached. Forcing finalize.")
        return "finalize"
    
    # 3. 계속 토론
    logger.info(f"Debate Supervisor: Debate continues (Round {debate_iter + 1}/{MAX_ITERATIONS})")
    return "back_to_analyst"


# ===== Graph Builder =====

def build_necking_expert_graph():
    """Necking 전문가 서브그래프 빌드 - Map-Reduce Pattern with Send API"""
    builder = StateGraph(NeckingExpertState)
    
    # ===== Add Nodes =====
    # Map Phase: Worker
    builder.add_node("analyze_hotspot_worker", analyze_hotspot_worker)
    
    # Reduce Phase: Supervisor
    builder.add_node("supervisor_verdict", supervisor_verdict)
    
    # Debate Nodes (Conditional)
    builder.add_node("verdict_analyst", verdict_analyst_node)
    builder.add_node("verdict_critic", verdict_critic_node)
    builder.add_node("verdict_finalize", verdict_finalize_node)
    
    # ===== Add Edges =====
    
    # 1. Fan-Out: START → distribute_work → Workers (Parallel) OR Supervisor (No hotspots)
    builder.add_conditional_edges(
        START,
        distribute_work,
        ["analyze_hotspot_worker", "supervisor_verdict"]
    )
    
    # 2. Fan-In: Workers → Supervisor (Auto-aggregation via operator.add)
    builder.add_edge("analyze_hotspot_worker", "supervisor_verdict")
    
    # 3. Supervisor → Debate OR Finalize (Conditional)
    builder.add_conditional_edges(
        "supervisor_verdict",
        route_supervisor_decision,
        {
            "debate": "verdict_analyst",
            "finalize": "verdict_finalize"
        }
    )
    
    # 4. Debate Flow: Analyst → Critic → (Loop OR Finalize)
    builder.add_edge("verdict_analyst", "verdict_critic")
    builder.add_conditional_edges(
        "verdict_critic",
        route_verdict_debate,
        {
            "back_to_analyst": "verdict_analyst",
            "finalize": "verdict_finalize"
        }
    )
    
    # 5. Finalize → END
    builder.add_edge("verdict_finalize", END)
    
    return builder.compile()

def _cleanup_temp_files(
    temp_image_path: Optional[str], 
    final_state: Optional[Dict[str, Any]],
    cleanup_original: bool = True
):
    """
    임시 파일 정리
    
    Args:
        temp_image_path: 원본 이미지 경로
        final_state: 최종 상태 (ROI 경로 추출용)
        cleanup_original: True이면 원본도 삭제, False면 ROI만 삭제
    """
    # 1. 원본 임시 파일 삭제 (cleanup_original=True일 때만)
    if cleanup_original and temp_image_path and os.path.exists(temp_image_path):
        try:
            os.remove(temp_image_path)
        except Exception:
            pass

    if not final_state:
        return

    # 2. ROI 파일 정리 (항상 실행)
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


def necking_expert_wrapper_node(state: InvestigationState) -> Dict[str, Any]:
    """Necking Expert wrapper node for main investigation graph"""
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
                    "errors": ["Necking 전문가: 이미지를 추출할 수 없습니다."],
                    "expert_reports": [],
                    "expert_analysis_results": {},
                    "expert_confidence_scores": {},
                    "expert_evidence": {}
                }
            temp_image_path = save_bytes_to_temp_file(image_data)
            should_cleanup_input = True
        
        # InvestigationState에서 공통 hotspots 읽기
        hotspots = state.get("hotspots", [])
        
        initial_state: NeckingExpertState = {
            "messages": [],
            "image_path": temp_image_path,
            "hotspots": hotspots,
            "hotspot_queue": None,
            "analysis_results": [],
            "preliminary_assessments": [],
            # Hotspot Loop 필드 (매 Loop마다 갱신)
            "current_hotspot": None,
            "detector_result": None,
            "roi_image_path": None,
            "connection_type": None,
            "specialist_result": None,
            
            # Debate 필드 (Verdict Analyst-Critic)
            "debate_iteration": 0,
            "debate_messages": [],
            "current_hypothesis": None,
            "critique_points": None,

            # 최종 결과
            "verdict_report": None,
            "verdict_confidence": None,
            "verdict_result": None
        }
        graph = build_necking_expert_graph()
        # 🔥 LangGraph 공식 권장: astream으로 실시간 진행 상황 모니터링
        # Send API 병렬 처리와 max_concurrency 제한 적용
        import asyncio
        
        logger.info("Necking Expert: Starting analysis with streaming...")
        
        async def run_with_streaming():
            """Streaming으로 실행하며 진행 상황 출력"""
            final_state = None
            last_event_value = None
            
            async for event in graph.astream(
                initial_state,
                config={
                    "recursion_limit": 50,
                    "max_concurrency": 3  # 동시 실행 worker 제한
                }
            ):
                # 최종 상태 추출
                if "__end__" in event:
                    final_state = event["__end__"]
                else:
                    # 중간 노드 완료 시 로그 출력 및 마지막 이벤트 값 저장
                    for node_name in event.keys():
                        if node_name not in ["__start__", "__end__"]:
                            print(f"  ✓ Completed: {node_name}")
                            # 마지막 노드의 출력이 최종 상태일 수 있음
                            last_event_value = event.get(node_name)
            
            # __end__ 이벤트가 없으면 마지막 이벤트 값을 최종 상태로 사용
            if final_state is None and last_event_value is not None:
                final_state = last_event_value
            
            return final_state
        
        final_state = asyncio.run(run_with_streaming())
        
        # final_state가 None인 경우 처리
        if final_state is None:
            logger.warning("Necking Expert: final_state is None, using empty state")
            final_state = {
                "verdict_report": "",
                "verdict_confidence": 0,
                "verdict_result": {},
                "analysis_results": []
            }
        
        # 결과 추출
        verdict_report = final_state.get("verdict_report", "")
        verdict_confidence = final_state.get("verdict_confidence", 0)
        verdict_result = final_state.get("verdict_result", {})
        analysis_results = final_state.get("analysis_results", [])
        
        # 증거 수집 (Top 1 기준)
        evidence = []
        if verdict_result:
            visual_desc = verdict_result.get("visual_description", "")
            verdict = verdict_result.get("verdict", "")
            if verdict:
                evidence.append({
                    "evidence": verdict,
                    "details": visual_desc
                })
        
        return {
            "expert_reports": [verdict_report] if verdict_report else ["분석 결과 없음"],
            "expert_analysis_results": {
                "necking": {
                    "multi_hotspot_results": analysis_results,
                    "final_verdict_result": verdict_result
                }
            },
            "expert_confidence_scores": {"necking": verdict_confidence},
            "expert_evidence": {"necking": evidence}
        }
    except Exception as e:
        print(f"\n[ERROR] Necking Expert Wrapper Exception: {str(e)}")
        traceback.print_exc()
        return {
            "errors": [f"Necking 전문가 오류: {str(e)}"],
            "expert_reports": [],
            "expert_analysis_results": {},
            "expert_confidence_scores": {},
            "expert_evidence": {}
        }
    finally:
        # 🔥 일원화된 정리 로직
        if final_state:
            _cleanup_temp_files(
                temp_image_path, 
                final_state, 
                cleanup_original=should_cleanup_input  # True: 원본+ROI, False: ROI만
            )
