"""
Aging Expert 노드 정의 (Multi-Hotspot Loop Mode)
절연열화/트래킹 전문가
"""
import os
import cv2
from typing import Dict, Any, List, Optional, Annotated, TypedDict
import operator

from config import TOP_N_HOTSPOTS
from langgraph.graph import MessagesState
from langchain_core.messages import SystemMessage, HumanMessage

from src.utils import crop_roi_from_box
from src.nodes.enhancement import ImageEnhancer
from src.tools.experts.expert_utils import (
    call_gemini_vision, 
    call_gemini_text, 
    parse_json_response,
    _load_image_data
)
from src.prompts.common_prompts import (
    get_component_classifier_prompt,
)
from src.prompts.aging_expert_prompts import (
    get_aging_wire_prompt,
    get_aging_PCB_prompt,
    get_final_verdict_prompt
)

# --- State Definition ---
class AgingExpertState(TypedDict):
    """Aging 전문가 그래프 상태"""
    # 기본 메시지 상태
    messages: List[Any]
    
    # 이미지 경로
    image_path: str
    
    # 1. 탐지 단계 상태
    hotspots: List[Dict[str, Any]]
    hotspot_queue: Optional[List[Dict[str, Any]]]
    
    # 2. 루프 처리 상태
    current_hotspot: Optional[Dict[str, Any]]
    detector_result: Optional[Dict[str, Any]]
    roi_image_path: Optional[str]
    connection_type: Optional[str]
    
    # 3. 분석 결과 (개별)
    specialist_result: Optional[Dict[str, Any]]
    
    # 4. 결과 집계
    analysis_results: Annotated[List[Dict[str, Any]], operator.add]
    
    # 5. 최종 판정
    verdict_report: Optional[str]
    verdict_confidence: Optional[float]
    verdict_result: Optional[Dict[str, Any]]


# --- Nodes ---

# hotspot_detector_node는 이제 src/nodes/common_nodes.py에서 공통으로 사용됩니다.

def hotspot_manager_node(state: AgingExpertState) -> Dict[str, Any]:
    """Middleware: Hotspot Manager"""
    hotspots = state.get("hotspots", [])
    queue = state.get("hotspot_queue")
    
    if queue is None:
        # 초기화: Score 내림차순 정렬 및 Top N 선별 (config.py에서 설정)
        print("\n⚖️ [Manager] Hotspot 우선순위 정렬")
        # severity_score 0인 hotspot 제외 (분석 불가 상태)
        valid_hotspots = [h for h in hotspots if h.get("severity_score", 0) > 0]
        if len(valid_hotspots) < len(hotspots):
            excluded_count = len(hotspots) - len(valid_hotspots)
            excluded_ids = [h.get('id') for h in hotspots if h.get("severity_score", 0) == 0]
            print(f"⏭️ [Manager] severity_score 0인 Hotspot {excluded_count}개 제외: {excluded_ids}")
        
        sorted_hotspots = sorted(valid_hotspots, key=lambda x: x.get("severity_score", 0), reverse=True)
        queue = sorted_hotspots[:TOP_N_HOTSPOTS]
        
        if not queue:
             print("\n🏁 [Manager] 처리할 Hotspot이 없습니다.")
             return {"hotspot_queue": [], "current_hotspot": None}
             
        current = queue[0]
        remaining = queue[1:]
        
        print(f"\n▶️ [Manager] Processing Hotspot ID {current.get('id')} ({current.get('damage_type')})")
        
        return {
            "hotspot_queue": remaining,
            "current_hotspot": current,
            "detector_result": {
                "box_2d": current.get("box_2d"),
                "feature_name": current.get("damage_type"),
                "confidence": current.get("severity_score")
            },
            "analysis_results": []
        }

    # Loop Logic
    if not queue:
        print("\n🏁 [Manager] 모든 Hotspot 처리 완료.")
        return {"current_hotspot": None}

    current = queue[0]
    remaining = queue[1:]
    
    print(f"\n▶️ [Manager] Processing Hotspot ID {current.get('id')} ({current.get('damage_type')})")
    
    return {
        "hotspot_queue": remaining,
        "current_hotspot": current,
        "detector_result": {
            "box_2d": current.get("box_2d"),
            "feature_name": current.get("damage_type"),
            "confidence": current.get("severity_score")
        },
        "connection_type": None,
        "specialist_result": None
    }

def roi_crop_node(state: AgingExpertState) -> Dict[str, Any]:
    """ROI Crop & Enhancement"""
    detector_result = state.get("detector_result")
    image_path = state.get("image_path")
    
    if not detector_result or not image_path:
        return {"roi_image_path": image_path}
    
    box_2d = detector_result.get("box_2d")
    if not box_2d:
        return {"roi_image_path": image_path}
    
    print(f"✂️ [ROI Crop] Hotspot 영역 크롭... {box_2d}")
    try:
        cropped_path = crop_roi_from_box(image_path, box_2d)
        
        # Enhancement
        cropped_img = cv2.imread(cropped_path)
        if cropped_img is not None:
             enhancer = ImageEnhancer()
             enhanced_img = enhancer.upscale(cropped_img)
             cv2.imwrite(cropped_path, enhanced_img)
             print(f"✨ [Enhancement] 향상 완료")


             
        return {"roi_image_path": cropped_path}
    except Exception as e:
        print(f"⚠️ Crop Failed: {e}")
        return {"roi_image_path": image_path}

def component_classifier_node(state: AgingExpertState) -> Dict[str, Any]:
    """Node 1: Component Classifier"""
    roi_image_path = state.get("roi_image_path")
    if not roi_image_path:
        return {"connection_type": "None"}
        
    print(f"\n🔍 [Component Classifier] 부품 유형 식별 중... (Dual Input: Context + Detail)")
    try:
        roi_data = _load_image_data(roi_image_path)
        original_data = _load_image_data(state.get("image_path"))
        image_payload = [original_data, roi_data]
    except Exception:
        return {"connection_type": "None"}
        
    prompt = get_component_classifier_prompt(roi_image_path)
    response_text, _ = call_gemini_vision(
        prompt, 
        image_payload, 
        "Component Classifier", 
        temperature=0.0,
        thinking_level="high",
        media_resolution="MEDIA_RESOLUTION_HIGH"
    )
    result = parse_json_response(response_text)
    
    deduced_type = result.get("deduced_type", "None")
    print(f"✅ 판별 결과: {deduced_type} (신뢰도: {result.get('confidence', 0)}%)")
    
    return {"connection_type": deduced_type}

def aging_wire_node(state: AgingExpertState) -> Dict[str, Any]:
    """Node 3A: Aging Wire Analysis (Arc/Severed End)"""
    print(f"\n⚡ [Aging] Wire Analysis (Dual Input: Context + Detail)")
    roi_path = state.get("roi_image_path")
    original_image_path = state.get("image_path")
    
    prompt = get_aging_wire_prompt(roi_path)
    
    try:
        roi_data = _load_image_data(roi_path)
        original_data = _load_image_data(original_image_path)
        image_payload = [original_data, roi_data]
        
        response_text, _ = call_gemini_vision(
            prompt, 
            image_payload, 
            "Aging Wire Specialist", 
            verbose=True,
            temperature=1.0,
            thinking_level="high",
            media_resolution="MEDIA_RESOLUTION_HIGH"
        )
        result = parse_json_response(response_text)
        return {"specialist_result": result}
    except Exception as e:
        print(f"⚠️ Wire Specialist Error: {e}")
        return {"specialist_result": {}}

def aging_pcb_node(state: AgingExpertState) -> Dict[str, Any]:
    """Node 3B: Aging PCB Analysis (Tracking/Insulation)"""
    print(f"\n⚡ [Aging] PCB Analysis (Dual Input: Context + Detail)")
    roi_path = state.get("roi_image_path")
    original_image_path = state.get("image_path")
    
    prompt = get_aging_PCB_prompt(roi_path)
    
    try:
        roi_data = _load_image_data(roi_path)
        original_data = _load_image_data(original_image_path)
        image_payload = [original_data, roi_data]
        
        response_text, _ = call_gemini_vision(
            prompt, 
            image_payload, 
            "Aging PCB Specialist", 
            verbose=True,
            temperature=1.0,
            thinking_level="high",
            media_resolution="MEDIA_RESOLUTION_HIGH"
        )
        result = parse_json_response(response_text)
        return {"specialist_result": result}
    except Exception as e:
        print(f"⚠️ PCB Specialist Error: {e}")
        return {"specialist_result": {}}

def result_aggregator_node(state: AgingExpertState) -> Dict[str, Any]:
    """Loop End: 결과 집계"""
    entry = {
        "hotspot_id": state.get("current_hotspot", {}).get("id"),
        "hotspot_info": state.get("current_hotspot"),
        "connection_type": state.get("connection_type"),
        "specialist_result": state.get("specialist_result"),
        "roi_image_path": state.get("roi_image_path")
    }
    return {"analysis_results": [entry]}

def format_report_summary(analysis_results: list) -> str:
    summary = ""
    for res in analysis_results:
        hotspot = res.get('hotspot_info', {})
        specialist = res.get('specialist_result', {})
        conn_type = res.get('connection_type', 'None')
        
        # Specialist 결과가 없는 경우 처리
        if not specialist:
            summary += f"""
--- [Spot ID: {hotspot.get('id')}] ---
1. 발견된 특징 (Node 0): {hotspot.get('damage_type', 'Unknown')}
2. 전문가 정밀 분석 (Node 2): 
   - 분석 불가 또는 특이사항 없음 ({conn_type})
-----------------------------------
"""
            continue
        
        summary += f"""
--- [Spot ID: {hotspot.get('id')}] ---
1. 발견된 특징 (Node 0): {hotspot.get('damage_type', 'Unknown')}
2. 전문가 정밀 분석 (Node 2): ({conn_type})
   - 시각적 특징: {specialist.get('visual_observation', 'N/A')}
   - 전문가 판정: {specialist.get('verdict', 'N/A')}
   - 판정 근거: {specialist.get('reasoning', 'N/A')}
-----------------------------------
"""
    return summary

def verdict_node(state: AgingExpertState) -> Dict[str, Any]:
    """Step 4: Final Verdict"""
    print("--- [Aging] Node 4: Final Verdict ---")
    results = state.get("analysis_results", [])
    
    if not results:
        return {
            "verdict_report": "분석된 특이점이 없습니다.",
            "verdict_confidence": 0,
            "verdict_result": {}
        }
        
    report_summary = format_report_summary(results)
    
    # Max Confidence Evidence Selection
    max_conf = 0
    best_res = {}
    for res in results:
        s_res = res.get("specialist_result", {})
        if s_res and s_res.get("confidence", 0) > max_conf:
            max_conf = s_res.get("confidence", 0)
            best_res = s_res
            
    prompt = get_final_verdict_prompt(report_summary)
    response_text, _ = call_gemini_text(
        prompt, 
        step_name="Aging Final Verdict", 
        verbose=True,
        temperature=1.0,
        thinking_level="high"
    )
    
    llm_result = parse_json_response(response_text)
    
    final_report = f"""[Aging 전문가 최종 판정]
## 결론: {llm_result.get('conclusion')} ({llm_result.get('probability')})

## 핵심 증거
{chr(10).join(['- '+e for e in llm_result.get('key_evidence', [])])}

## 종합 소견
{llm_result.get('reasoning')}
"""
    
    return {
        "verdict_report": final_report,
        "verdict_confidence": max_conf, # Use highest finding confidence
        "verdict_result": best_res
    }
