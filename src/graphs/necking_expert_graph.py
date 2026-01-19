"""
Necking 전문가 서브그래프 빌더 (Map-Reduce Pattern with Send API)
"""
from typing import Dict, Any, Optional, Literal, List, Union
import os

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from src.state import InvestigationState
from src.nodes.necking_nodes import (
    NeckingExpertState,
    WorkerState,
    analyze_hotspot_worker,
    supervisor_verdict,
    verdict_analyst_node,
    verdict_critic_node,
    verdict_finalize_node
)
from src.tools.experts.expert_utils import extract_image_from_payload, save_bytes_to_temp_file
from config import TOP_N_HOTSPOTS

# ===== Send API Fan-Out Function =====

def distribute_work(state: NeckingExpertState) -> Union[str, List[Send]]:
    """
    Fan-out: Distribute hotspots to parallel workers using Send API
    
    Returns:
        - List[Send]: If hotspots exist, fan-out to workers
        - str: If no hotspots, skip to supervisor
    """
    hotspots = state.get("hotspots", [])
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
        print("[Router] 🔄 Supervisor: Debate 필요 → Analyst 호출")
        return "debate"
    
    print("[Router] ✅ Supervisor: Fast Path 결론 → Finalize")
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
    
    # 🔥 Phase 2: Pydantic 객체 우선, 문자열은 Fallback
    critique_result = state.get("critique_result")
    critique_points = state.get("critique_points", "")
    
    # 1. Critic 합의 체크 (is_approved bool 우선)
    if critique_result is not None:
        # Pydantic 객체가 있으면 is_approved bool 직접 체크
        if critique_result.is_approved:
            print("[Debate Supervisor] ✅ Critic agreed (is_approved=True). Proceeding to finalize.")
            return "finalize"
    elif "NO_OBJECTION" in critique_points:
        # Fallback: Legacy 문자열 검색
        print("[Debate Supervisor] ✅ Critic agreed (NO_OBJECTION found). Proceeding to finalize.")
        return "finalize"
    
    # 2. Timeout
    if debate_iter >= MAX_ITERATIONS:
        print(f"[Debate Supervisor] ⏱️ Max iterations ({MAX_ITERATIONS}) reached. Forcing finalize.")
        return "finalize"
    
    # 3. 계속 토론
    print(f"[Debate Supervisor] 🔄 Debate continues (Round {debate_iter + 1}/{MAX_ITERATIONS})")
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

def _cleanup_temp_files(temp_image_path: Optional[str], final_state: Optional[Dict[str, Any]]):
    """임시 파일 정리"""
    try:
        # 1. 원본 임시 파일 삭제
        if temp_image_path and os.path.exists(temp_image_path):
            os.remove(temp_image_path)
    except Exception:
        pass

    if not final_state:
        return

    # 2. Loop 과정에서 생성된 모든 ROI 파일 정리
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
    import traceback
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
            "hotspots": hotspots,  # 메인 그래프에서 생성된 공통 hotspots 사용
            "hotspot_queue": None, # Manager가 초기화함
            "analysis_results": [],
            "preliminary_assessments": [], # 병렬 증거 수집 결과 (Annotated List)
            
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
        # 🔥 LangGraph 공식 권장: Send API 병렬 처리를 위해 ainvoke 사용 필수
        # invoke는 순차 실행되지만, ainvoke는 병렬 실행을 보장합니다
        import asyncio
        final_state = asyncio.run(graph.ainvoke(initial_state, config={"recursion_limit": 50}))
        
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
        if should_cleanup_input:
            _cleanup_temp_files(temp_image_path, final_state)
        elif final_state:
            # Shared Path인 경우, ROI 파일들만 정리
            analysis_results = final_state.get("analysis_results", [])
            for res in analysis_results:
                roi_path = res.get("roi_image_path")
                if roi_path and roi_path != temp_image_path and os.path.exists(roi_path):
                    try:
                        os.remove(roi_path)
                    except Exception:
                        pass
