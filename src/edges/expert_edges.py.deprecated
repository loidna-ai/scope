"""
전문가 서브그래프 엣지 정의
각 전문가의 서브그래프 노드 간 연결을 정의합니다.
"""
from langgraph.graph import START, END, StateGraph

def add_contact_expert_edges(builder: StateGraph) -> None:
    """
    Contact 전문가 서브그래프에 엣지를 추가합니다.
    
    그래프 구조:
    START -> step1_location -> step2_spectral -> step3_thermal -> step4_surface -> finalize -> END
    
    Args:
        builder: StateGraph 빌더 객체
    """
    builder.add_edge(START, "step1_location")
    builder.add_edge("step1_location", "step2_spectral")
    builder.add_edge("step2_spectral", "step3_thermal")
    builder.add_edge("step3_thermal", "step4_surface")
    builder.add_edge("step4_surface", "finalize")
    builder.add_edge("finalize", END)

def add_aging_expert_edges(builder: StateGraph) -> None:
    """
    Aging 전문가 서브그래프에 엣지를 추가합니다.
    
    그래프 구조:
    START -> step1_carbonization -> step2_swelling -> step3_global_aging -> finalize -> END
    
    Args:
        builder: StateGraph 빌더 객체
    """
    builder.add_edge(START, "step1_carbonization")
    builder.add_edge("step1_carbonization", "step2_swelling")
    builder.add_edge("step2_swelling", "step3_global_aging")
    builder.add_edge("step3_global_aging", "finalize")
    builder.add_edge("finalize", END)

def add_deform_expert_edges(builder: StateGraph) -> None:
    """
    Deform 전문가 서브그래프에 엣지를 추가합니다.
    
    그래프 구조:
    START -> step1_deformation -> step2_splaying -> step3_confinement -> finalize -> END
    
    Args:
        builder: StateGraph 빌더 객체
    """
    builder.add_edge(START, "step1_deformation")
    builder.add_edge("step1_deformation", "step2_splaying")
    builder.add_edge("step2_splaying", "step3_confinement")
    builder.add_edge("step3_confinement", "finalize")
    builder.add_edge("finalize", END)

def add_tracking_expert_edges(builder: StateGraph) -> None:
    """
    Tracking 전문가 서브그래프에 엣지를 추가합니다.
    
    그래프 구조:
    START -> step1_dendritic_pattern -> step2_luster -> step3_erosion -> finalize -> END
    
    Args:
        builder: StateGraph 빌더 객체
    """
    builder.add_edge(START, "step1_dendritic_pattern")
    builder.add_edge("step1_dendritic_pattern", "step2_luster")
    builder.add_edge("step2_luster", "step3_erosion")
    builder.add_edge("step3_erosion", "finalize")
    builder.add_edge("finalize", END)

def add_necking_expert_edges(builder: StateGraph) -> None:
    """
    Necking 전문가 서브그래프에 엣지를 추가합니다.
    
    그래프 구조:
    START -> step1_tip_morphology -> step2_bead_distribution -> step3_fatigue -> finalize -> END
    
    Args:
        builder: StateGraph 빌더 객체
    """
    builder.add_edge(START, "step1_tip_morphology")
    builder.add_edge("step1_tip_morphology", "step2_bead_distribution")
    builder.add_edge("step2_bead_distribution", "step3_fatigue")
    builder.add_edge("step3_fatigue", "finalize")
    builder.add_edge("finalize", END)
