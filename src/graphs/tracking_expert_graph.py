"""
Tracking 전문가 서브그래프 빌더 (Map-Reduce Pattern with Send API)
"""
import os
from typing import Dict, Any, Optional, Literal, List, Union

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from src.state import InvestigationState
from src.utils.logging_config import setup_logger
from src.nodes.tracking_nodes import (
    TrackingExpertState,
    analyze_hotspot_worker,
    supervisor_verdict,
    verdict_analyst_node,
    verdict_critic_node,
    verdict_finalize_node
)
from src.graphs.graph_utils import (
    distribute_work_generic,
    route_supervisor_decision_generic,
    route_verdict_debate_generic,
    create_expert_wrapper_node
)

logger = setup_logger(__name__)

# ===== Send API Fan-Out Function =====

def distribute_work(state: TrackingExpertState) -> Union[str, List[Send]]:
    """Fan-Out to Workers"""
    return distribute_work_generic(state, "Tracking")

# ===== Conditional Routing Functions =====

def route_supervisor_decision(state: TrackingExpertState) -> Literal["debate", "finalize"]:
    return route_supervisor_decision_generic(state)

def route_verdict_debate(state: TrackingExpertState) -> Literal["back_to_analyst", "finalize"]:
    return route_verdict_debate_generic(state)

# ===== Graph Builder =====

def build_tracking_expert_graph():
    """Tracking 전문가 서브그래프 빌드 - Map-Reduce Pattern"""
    builder = StateGraph(TrackingExpertState)
    
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

def _tracking_initial_state_factory(temp_image_path, hotspots, preprocessed_hotspots, **kwargs) -> TrackingExpertState:
    return {
        "messages": [],
        "image_path": temp_image_path,
        "hotspots": hotspots,
        "preprocessed_hotspots": preprocessed_hotspots,
        "analysis_results": [],
        "preliminary_assessments": [],
        
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

tracking_expert_wrapper_node = create_expert_wrapper_node(
    expert_name="Tracking",
    expert_id="tracking",
    build_graph_fn=build_tracking_expert_graph,
    default_initial_state_factory=_tracking_initial_state_factory
)
