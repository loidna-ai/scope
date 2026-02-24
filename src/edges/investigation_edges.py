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
    
    Note: Aging, Tracking은 작업 미완료로 비활성화됨
    
    Args:
        builder: StateGraph 빌더 객체
    """
    # 공통 Hotspot Detector 실행
    builder.add_edge(START, "hotspot_detector")

    # [#5] hotspot_detector → preprocessor (Crop+Enhancement+Classification 1회)
    builder.add_edge("hotspot_detector", "preprocessor")

    # Fan-out: preprocessor → Map-Reduce 전문가들 (병렬 실행)
    builder.add_edge("preprocessor", "contact")
    builder.add_edge("preprocessor", "aging")
    builder.add_edge("preprocessor", "deform")
    # builder.add_edge("preprocessor", "tracking")
    builder.add_edge("preprocessor", "necking")

    # Fan-in: Map-Reduce 전문가들 → Arbiter (논쟁 시스템 서브그래프)
    builder.add_edge("contact", "arbiter")
    builder.add_edge("aging", "arbiter")
    builder.add_edge("deform", "arbiter")
    # builder.add_edge("tracking", "arbiter")
    builder.add_edge("necking", "arbiter")

    # 종료
    builder.add_edge("arbiter", "visualizer")
    builder.add_edge("visualizer", END)



