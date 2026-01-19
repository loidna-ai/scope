from typing import Dict, Any, List, Optional, Annotated
import operator
from langgraph.graph import MessagesState

class TrackingExpertState(MessagesState):
    """
    Tracking Expert State
    """
    # 원본 이미지
    image_path: Optional[str]
    
    # Phase 1: Hotspot Detection
    hotspots: Optional[List[Dict[str, Any]]]
    hotspot_queue: Optional[List[Dict[str, Any]]]
    
    # Loop Context
    current_hotspot: Optional[Dict[str, Any]]
    detector_result: Optional[Dict[str, Any]] # roi_crop_node 호환용
    roi_image_path: Optional[str]
    connection_type: Optional[str] # Component Classification 결과
    
    # Analysis Results (Specific Components)
    tracking_terminal_result: Optional[Dict[str, Any]]
    tracking_plug_result: Optional[Dict[str, Any]]
    tracking_pcb_result: Optional[Dict[str, Any]]
    
    # Final Aggregation
    analysis_results: Annotated[List[Dict[str, Any]], operator.add]
    
    # Verdict Results
    verdict_report: Optional[str]
    verdict_confidence: Optional[int]
    verdict_result: Optional[Dict[str, Any]]
