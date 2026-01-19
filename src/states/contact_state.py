from typing import Dict, Any, List, Optional, Annotated
import operator
from langgraph.graph import MessagesState

class ContactExpertState(MessagesState):
    """
    Contact Expert ReAct State
    """
    # 원본 이미지
    image_path: Optional[str]
    
    # Phase 1: Hotspot Detection
    hotspots: Optional[List[Dict[str, Any]]]  # Node 0 결과 (전체 리스트)
    hotspot_queue: Optional[List[Dict[str, Any]]]  # 처리 대기중인 Hotspots
    
    # Loop Context
    current_hotspot: Optional[Dict[str, Any]]  # 현재 처리 중인 Hotspot
    detector_result: Optional[Dict[str, Any]]  # 호환성을 위해 current_hotspot 정보를 매핑
    roi_image_path: Optional[str]  # 현재 ROI 이미지
    connection_type: Optional[str]  # 현재 Crop의 분류 결과
    
    # Analysis Results
    terminal_result: Optional[Dict[str, Any]]
    splice_result: Optional[Dict[str, Any]]
    plug_result: Optional[Dict[str, Any]]
    
    # Final Aggregation
    analysis_results: Annotated[List[Dict[str, Any]], operator.add]  # 최종 결과 리스트 누적
    
    # Verdict Results
    verdict_report: Optional[str]
    verdict_confidence: Optional[int]
    verdict_result: Optional[Dict[str, Any]]
