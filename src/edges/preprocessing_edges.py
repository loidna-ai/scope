"""
전처리 파이프라인 엣지 정의
이미지 전처리 그래프의 노드 간 연결을 정의합니다.
"""
from langgraph.graph import START, END, StateGraph


def add_preprocessing_edges(builder: StateGraph, has_enhancement: bool = True) -> None:
    """
    전처리 파이프라인 그래프에 엣지를 추가합니다.
    
    그래프 구조:
    - enhance가 있는 경우: START -> load -> crop -> enhance -> [filter, metrics] (병렬) -> packaging -> END
    - enhance가 없는 경우: START -> load -> crop -> [filter, metrics] (병렬) -> packaging -> END
    
    Args:
        builder: StateGraph 빌더 객체
        has_enhancement: enhancement 노드가 있는지 여부
    """
    # 순차 처리: START -> load -> crop
    builder.add_edge(START, "load")
    builder.add_edge("load", "crop")
    
    if has_enhancement:
        # enhance가 있는 경우: crop -> enhance -> [filter, metrics]
        builder.add_edge("crop", "enhance")
        builder.add_edge("enhance", "filter")
        builder.add_edge("enhance", "metrics")
    else:
        # enhance가 없는 경우: crop -> [filter, metrics]
        builder.add_edge("crop", "filter")
        builder.add_edge("crop", "metrics")
    
    # 수집 (Fan-in): filter, metrics -> packaging
    builder.add_edge("filter", "packaging")
    builder.add_edge("metrics", "packaging")
    
    # 종료: packaging -> END
    builder.add_edge("packaging", END)

