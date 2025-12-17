"""
그래프 빌더
LangGraph StateGraph를 조립하고 컴파일합니다.
"""
from typing import List, Any
from langgraph.graph import StateGraph, START, END
from src.state import GraphState, InvestigationState
from src.nodes.load import load_node
from src.nodes.crop import crop_node
from src.nodes.enhancement import enhancement_node
from src.nodes.filter import filter_node
from src.nodes.metrics import metrics_node
from src.nodes.packaging import packaging_node
from src.nodes.investigation import (
    node_tracking,
    node_short_circuit,
    node_severed,
    node_contact,
    node_overcurrent,
    node_chief_investigator
)


def build_graph() -> StateGraph:
    """
    LangGraph StateGraph를 빌드하고 컴파일합니다.
    
    그래프 구조:
    START -> load -> crop -> enhance -> [filter, metrics] (병렬) -> packaging -> END
    
    Returns:
        컴파일된 그래프
    """
    # StateGraph 초기화
    builder = StateGraph(GraphState)
    
    # 노드 추가 (명시적 이름 지정)
    builder.add_node("load", load_node)
    builder.add_node("crop", crop_node)
    builder.add_node("enhance", enhancement_node)
    builder.add_node("filter", filter_node)
    builder.add_node("metrics", metrics_node)
    builder.add_node("packaging", packaging_node)
    
    # 순차 처리: START -> load -> crop -> enhance
    builder.add_edge(START, "load")
    builder.add_edge("load", "crop")
    builder.add_edge("crop", "enhance")
    
    # 병렬 처리 (Fan-out): enhance -> filter, enhance -> metrics
    builder.add_edge("enhance", "filter")
    builder.add_edge("enhance", "metrics")
    
    # 수집 (Fan-in): filter, metrics -> packaging
    builder.add_edge("filter", "packaging")
    builder.add_edge("metrics", "packaging")
    
    # 종료: packaging -> END
    builder.add_edge("packaging", END)
    
    # 그래프 컴파일
    graph = builder.compile()
    
    return graph


def build_investigation_graph() -> StateGraph:
    """
    화재조사 멀티 에이전트 그래프 빌드
    
    그래프 구조:
    START → [tracking, short_circuit, severed, contact, overcurrent] (병렬)
         → chief_investigator → END
    
    Returns:
        컴파일된 그래프
    """
    builder = StateGraph(InvestigationState)
    
    # 노드 추가
    builder.add_node("tracking", node_tracking)
    builder.add_node("short_circuit", node_short_circuit)
    builder.add_node("severed", node_severed)
    builder.add_node("contact", node_contact)
    builder.add_node("overcurrent", node_overcurrent)
    builder.add_node("chief_investigator", node_chief_investigator)
    
    # Fan-out: START → 모든 전문가 노드 (병렬 실행)
    builder.add_edge(START, "tracking")
    builder.add_edge(START, "short_circuit")
    builder.add_edge(START, "severed")
    builder.add_edge(START, "contact")
    builder.add_edge(START, "overcurrent")
    
    # Fan-in: 모든 전문가 노드 → Chief
    builder.add_edge("tracking", "chief_investigator")
    builder.add_edge("short_circuit", "chief_investigator")
    builder.add_edge("severed", "chief_investigator")
    builder.add_edge("contact", "chief_investigator")
    builder.add_edge("overcurrent", "chief_investigator")
    
    # 종료
    builder.add_edge("chief_investigator", END)
    
    return builder.compile()


def analyze_fire_evidence(payload_data: List[Any]) -> dict:
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
    graph = build_investigation_graph()
    
    initial_state = {
        "payload": payload_data,
        "expert_reports": [],
        "final_verdict": None,
        "errors": []
    }
    
    result = graph.invoke(initial_state)
    return {
        "final_verdict": result.get("final_verdict", "분석 실패"),
        "expert_reports": result.get("expert_reports", []),
        "errors": result.get("errors", [])
    }

