"""
화재조사 멀티 에이전트 그래프 엣지 정의
전문가 노드 간 연결을 정의합니다.
"""
from langgraph.graph import START, END, StateGraph

def add_investigation_edges(builder: StateGraph) -> None:
    """
    화재조사 멀티 에이전트 그래프에 엣지를 추가합니다.
    
    그래프 구조:
    START → hotspot_detector (공통)
         → [contact, deform, necking] (병렬, Map-Reduce Pattern만 사용)
         → arbiter (논쟁 시스템 서브그래프) → visualizer → END
    
    Note: Aging, Tracking은 Loop Pattern이므로 주석처리됨
    
    Args:
        builder: StateGraph 빌더 객체
    """
    # 공통 Hotspot Detector 실행
    builder.add_edge(START, "hotspot_detector")
    
    # Fan-out: Hotspot Detector → Map-Reduce 전문가들 (병렬 실행)
    builder.add_edge("hotspot_detector", "contact")
    # builder.add_edge("hotspot_detector", "aging")  # [Disabled] Loop Pattern
    builder.add_edge("hotspot_detector", "deform")
    # builder.add_edge("hotspot_detector", "tracking")  # [Disabled] Loop Pattern
    builder.add_edge("hotspot_detector", "necking")
    
    # Fan-in: Map-Reduce 전문가들 → Arbiter (논쟁 시스템 서브그래프)
    builder.add_edge("contact", "arbiter")
    # builder.add_edge("aging", "arbiter")  # [Disabled] Loop Pattern
    builder.add_edge("deform", "arbiter")
    # builder.add_edge("tracking", "arbiter")  # [Disabled] Loop Pattern
    builder.add_edge("necking", "arbiter")
    
    # 종료
    # Visualization
    builder.add_edge("arbiter", "visualizer")
    builder.add_edge("visualizer", END)

def add_investigation_edges_with_react(builder: StateGraph) -> None:
    """
    화재조사 멀티 에이전트 그래프에 ReAct 에이전트를 포함한 엣지를 추가합니다.
    
    그래프 구조:
    START → [contact, deform, necking, react_agent] (병렬, Map-Reduce Pattern만 사용)
         → chief_investigator → END
    
    Note: Aging, Tracking은 Loop Pattern이므로 주석처리됨
    
    Args:
        builder: StateGraph 빌더 객체
    """
    # Fan-out: START → Map-Reduce 전문가들 및 ReAct 에이전트 (병렬 실행)
    builder.add_edge(START, "contact")
    # builder.add_edge(START, "aging")  # [Disabled] Loop Pattern
    builder.add_edge(START, "deform")
    # builder.add_edge(START, "tracking")  # [Disabled] Loop Pattern
    builder.add_edge(START, "necking")
    builder.add_edge(START, "react_agent")
    
    # Fan-in: Map-Reduce 전문가들 및 ReAct 에이전트 → Arbiter
    builder.add_edge("contact", "arbiter")
    # builder.add_edge("aging", "arbiter")  # [Disabled] Loop Pattern
    builder.add_edge("deform", "arbiter")
    # builder.add_edge("tracking", "arbiter")  # [Disabled] Loop Pattern
    builder.add_edge("necking", "arbiter")
    builder.add_edge("react_agent", "arbiter")
    
    # 종료
    builder.add_edge("arbiter", END)
