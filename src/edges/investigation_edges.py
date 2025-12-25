"""
화재조사 멀티 에이전트 그래프 엣지 정의
전문가 노드 간 연결을 정의합니다.
"""
from langgraph.graph import START, END, StateGraph


def add_investigation_edges(builder: StateGraph) -> None:
    """
    화재조사 멀티 에이전트 그래프에 엣지를 추가합니다.
    
    그래프 구조:
    START → [전문가1, 전문가2, 전문가3, 전문가4, 전문가5] (병렬)
         → chief_investigator → END
    
    Args:
        builder: StateGraph 빌더 객체
    """
    # Fan-out: START → 모든 전문가 (병렬 실행)
    builder.add_edge(START, "contact")
    builder.add_edge(START, "dielectric")
    builder.add_edge(START, "mechanical")
    builder.add_edge(START, "tracking")
    builder.add_edge(START, "strand_fracture")
    
    # Fan-in: 모든 전문가 → 수석 조사관
    builder.add_edge("contact", "chief_investigator")
    builder.add_edge("dielectric", "chief_investigator")
    builder.add_edge("mechanical", "chief_investigator")
    builder.add_edge("tracking", "chief_investigator")
    builder.add_edge("strand_fracture", "chief_investigator")
    
    # 종료
    builder.add_edge("chief_investigator", END)


def add_investigation_edges_with_react(builder: StateGraph) -> None:
    """
    화재조사 멀티 에이전트 그래프에 ReAct 에이전트를 포함한 엣지를 추가합니다.
    
    그래프 구조:
    START → [전문가1, 전문가2, 전문가3, 전문가4, 전문가5, react_agent] (병렬)
         → chief_investigator → END
    
    Args:
        builder: StateGraph 빌더 객체
    """
    # Fan-out: START → 모든 전문가 및 ReAct 에이전트 (병렬 실행)
    builder.add_edge(START, "contact")
    builder.add_edge(START, "dielectric")
    builder.add_edge(START, "mechanical")
    builder.add_edge(START, "tracking")
    builder.add_edge(START, "strand_fracture")
    builder.add_edge(START, "react_agent")
    
    # Fan-in: 모든 전문가 및 ReAct 에이전트 → 수석 조사관
    builder.add_edge("contact", "chief_investigator")
    builder.add_edge("dielectric", "chief_investigator")
    builder.add_edge("mechanical", "chief_investigator")
    builder.add_edge("tracking", "chief_investigator")
    builder.add_edge("strand_fracture", "chief_investigator")
    builder.add_edge("react_agent", "chief_investigator")
    
    # 종료
    builder.add_edge("chief_investigator", END)
