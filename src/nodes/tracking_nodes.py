"""
Tracking 전문가 노드 정의 (Multi-Hotspot Loop Mode)
"""
from typing import Dict, Any, Optional, List, Annotated
import os
import operator
import json
import cv2
import numpy as np

from config import TOP_N_HOTSPOTS
from src.utils.logging_config import setup_logger

from src.tools.experts.expert_utils import (
    call_gemini_vision,
    parse_json_response,
    call_gemini_text,
    _load_image_data
)

from src.utils import crop_roi_from_box
from src.nodes.enhancement import ImageEnhancer

# Prompts Import
from src.prompts.common_prompts import (
    get_component_classifier_prompt
)
from src.prompts.tracking_expert_prompts import (
    get_tracking_terminal_prompt,
    get_tracking_plug_prompt,
    get_tracking_pcb_prompt,
    get_final_verdict_prompt
)

from src.states.tracking_state import TrackingExpertState

logger = setup_logger(__name__)



# --------------------------------------------------------------------------------
# 워크플로우 노드 구현 (Contact Expert 구조 도입)
# --------------------------------------------------------------------------------

# hotspot_detector_node는 이제 src/nodes/common_nodes.py에서 공통으로 사용됩니다.

def hotspot_manager_node(state: TrackingExpertState) -> Dict[str, Any]:
    """
    Middleware: Hotspot Manager
    - Hotspot 리스트를 점수순 정렬
    - Top-N 선별하여 Queue에 적재
    - Queue에서 하나씩 꺼내어 처리 준비 (Loop 제어)
    """
    hotspots = state.get("hotspots", [])
    queue = state.get("hotspot_queue")
    
    # 1. 초기화 로직 (큐가 없으면 생성)
    if queue is None:
        logger.info("Hotspot Manager: Prioritizing hotspots")
        # severity_score 0인 hotspot 제외 (분석 불가 상태)
        valid_hotspots = [h for h in hotspots if h.get("severity_score", 0) > 0]
        if len(valid_hotspots) < len(hotspots):
            excluded_count = len(hotspots) - len(valid_hotspots)
            excluded_ids = [h.get('id') for h in hotspots if h.get("severity_score", 0) == 0]
            logger.warning(f"Hotspot Manager: Excluded {excluded_count} hotspots with 0 score: {excluded_ids}")
        
        # Score 내림차순 정렬
        sorted_hotspots = sorted(
            valid_hotspots, 
            key=lambda x: x.get("severity_score", 0), 
            reverse=True
        )
        # Top N 선별 (config.py에서 설정)
        queue = sorted_hotspots[:TOP_N_HOTSPOTS]
        logger.info(f"Hotspot Manager: Selected Hotspots: {[h.get('id') for h in queue]}")
        
        # 첫 번째 Hotspot 바로 Pop (Loop 시작을 위해)
        if not queue:
             logger.info("Hotspot Manager: No hotspots to process")
             return {"hotspot_queue": [], "current_hotspot": None}
             
        current = queue[0]
        remaining = queue[1:]
        
        logger.info(f"Hotspot Manager: Processing Hotspot ID {current.get('id')} ({current.get('damage_type')})")
        
        # downstream 호환성을 위해 detector_result에 매핑
        detector_result_mapping = {
            "box_2d": current.get("box_2d"),
            "feature_name": current.get("damage_type"),
            "confidence": current.get("severity_score")
        }
        
        # State 업데이트 (큐 초기화 + 첫 아이템 로드)
        return {
            "hotspot_queue": remaining,
            "current_hotspot": current,
            "detector_result": detector_result_mapping,
            "analysis_results": []
        }



    # 2. Loop 로직 (큐에서 꺼내기)
    if not queue:
        logger.info("Hotspot Manager: All hotspots processed")
        return {"current_hotspot": None}  # Loop 종료 신호

    current = queue[0]
    remaining = queue[1:]
    
    logger.info(f"Hotspot Manager: Processing Hotspot ID {current.get('id')} ({current.get('damage_type')})")
    
    # downstream 호환성을 위해 detector_result에 매핑
    detector_result_mapping = {
        "box_2d": current.get("box_2d"),
        "feature_name": current.get("damage_type"),
        "confidence": current.get("severity_score")
    }
    
    return {
        "hotspot_queue": remaining,
        "current_hotspot": current,
        "detector_result": detector_result_mapping, # for roi_crop_node
        "connection_type": None, # Reset for new loop
        "tracking_terminal_result": None,
        "tracking_plug_result": None,
        "tracking_pcb_result": None
    }

def roi_crop_node(state: TrackingExpertState) -> Dict[str, Any]:
    """
    ROI 크롭 노드
    detector_result(current_hotspot)에서 box_2d 추출하여 크롭
    후처리로 2배 초해상도 향상 적용
    """
    detector_result = state.get("detector_result")
    image_path = state.get("image_path")
    
    if not detector_result or not image_path:
        return {"roi_image_path": image_path}
    
    box_2d = detector_result.get("box_2d")
    if not box_2d:
        return {"roi_image_path": image_path}
    
    logger.debug(f"ROI Crop: Cropping hotspot area {box_2d}")
    try:
        cropped_path = crop_roi_from_box(image_path, box_2d)
        
        # 이미지 향상 적용
        logger.debug("ROI Crop: Enhancing ROI image...")
        try:
            # 1. 크롭된 이미지 로드
            cropped_img = cv2.imread(cropped_path)
            if cropped_img is None:
                raise ValueError("크롭된 이미지를 읽을 수 없습니다.")
                
            # 2. Enhancement Node 직접 호출 (State 구성 불필요)
            # ImageEnhancer 클래스 직접 사용이 더 깔끔할 수 있으나, 기존 구조 활용
            enhancer = ImageEnhancer()
            enhanced_img = enhancer.upscale(cropped_img)
            
            # 3. 향상된 이미지 저장 (덮어쓰기)
            cv2.imwrite(cropped_path, enhanced_img)
            logger.debug(f"ROI Crop: Enhancement complete: {cropped_path}")
            
        except Exception as enh_err:
             logger.warning(f"ROI Crop: Enhancement Failed: {enh_err}")
             # 향상 실패해도 원본 크롭 이미지는 유지됨


             
        return {"roi_image_path": cropped_path}
    except Exception as e:
        logger.error(f"ROI Crop: Failed: {e}", exc_info=True)
        return {"roi_image_path": image_path}

def component_classifier_node(state: TrackingExpertState) -> Dict[str, Any]:
    """
    Node 1: Component Classifier
    - 크롭된 이미지를 분석하여 접속부 유형(Terminal/Splice/Plug/None) 식별
    """
    roi_image_path = state.get("roi_image_path")
    if not roi_image_path:
        return {"connection_type": "None"}
        
    logger.info(f"Classifier: Identifying component type (ROI: {roi_image_path})")
    
    try:
        # Dual Image Load
        roi_image_data = _load_image_data(roi_image_path)
        original_image_path = state.get("image_path")
        original_image_data = _load_image_data(original_image_path) if original_image_path else roi_image_data
        
        # 순서: [Original(Context), Crop(Detail)]
        image_payload = [original_image_data, roi_image_data]
        
    except Exception:
        return {"connection_type": "None"}
        
    prompt = get_component_classifier_prompt(roi_image_path)
    
    try:
        # Temperature 0.0 for deterministic classification
        response_text, _ = call_gemini_vision(
            prompt, 
            image_payload, 
            "Component Classifier", 
            temperature=0.0,
            thinking_level="high",
            media_resolution="MEDIA_RESOLUTION_HIGH"
        )
        result = parse_json_response(response_text)
        
        # New Schema: deduced_type, visual_description
        deduced_type = result.get("deduced_type", "None")
        visual_description = result.get("visual_description", "")
        confidence = result.get("confidence", 0)
        reasoning = result.get("reasoning", "")
        
        logger.debug(f"Classifier Observation: {visual_description}")
        logger.info(f"Classifier Result: {deduced_type} (Confidence: {confidence}%)")
        
        return {
            "connection_type": deduced_type,
            "classifier_result": result
        }
    except Exception as e:
        logger.error(f"Component Classifier Error: {e}", exc_info=True)
        return {
            "connection_type": "None",
            "classifier_result": {"error": str(e)}
        }

def tracking_terminal_node(state: TrackingExpertState) -> Dict[str, Any]:
    """Tracking Specialist: Terminal Analysis"""
    roi_image_path = state.get("roi_image_path")
    original_image_path = state.get("image_path") # 원본 이미지 경로
    
    logger.info("Tracking Terminal: Starting analysis")
    
    try:
        # 두 장의 이미지를 모두 로드
        roi_data = _load_image_data(roi_image_path)
        original_data = _load_image_data(original_image_path)
        
        # 리스트로 전달 [원본(Context), ROI(Detail)]
        image_data_list = [original_data, roi_data]
        
        prompt = get_tracking_terminal_prompt(roi_image_path)
        response_text, _ = call_gemini_vision(
            prompt, 
            image_data_list, 
            "Tracking Terminal Expert", 
            verbose=True,
            temperature=1.0,
            thinking_level="high",
            media_resolution="MEDIA_RESOLUTION_HIGH"
        )
        result = parse_json_response(response_text)
        return {"tracking_terminal_result": result}
    except Exception as e:
        logger.error(f"Terminal Node Error: {e}", exc_info=True)
        return {"tracking_terminal_result": {"error": str(e)}}



def tracking_plug_node(state: TrackingExpertState) -> Dict[str, Any]:
    """Tracking Specialist: Plug Analysis"""
    roi_image_path = state.get("roi_image_path")
    original_image_path = state.get("image_path")
    
    logger.info("Tracking Plug: Starting analysis")
    
    try:
        # 두 장의 이미지를 모두 로드
        roi_data = _load_image_data(roi_image_path)
        original_data = _load_image_data(original_image_path)
        
        # 리스트로 전달 [원본(Context), ROI(Detail)]
        image_data_list = [original_data, roi_data]
        
        prompt = get_tracking_plug_prompt(roi_image_path)
        response_text, _ = call_gemini_vision(
            prompt, 
            image_data_list, 
            "Tracking Plug Expert",
            verbose=True,
            temperature=1.0,
            thinking_level="high",
            media_resolution="MEDIA_RESOLUTION_HIGH"
        )
        result = parse_json_response(response_text)
        return {"tracking_plug_result": result}
    except Exception as e:
        logger.error(f"Plug Node Error: {e}", exc_info=True)
        return {"tracking_plug_result": {"error": str(e)}}

def tracking_pcb_node(state: TrackingExpertState) -> Dict[str, Any]:
    """Tracking Specialist: PCB Analysis"""
    roi_image_path = state.get("roi_image_path")
    original_image_path = state.get("image_path")
    
    logger.info("Tracking PCB: Starting analysis")
    
    try:
        # 두 장의 이미지를 모두 로드
        roi_data = _load_image_data(roi_image_path)
        original_data = _load_image_data(original_image_path)
        
        # 리스트로 전달 [원본(Context), ROI(Detail)]
        image_data_list = [original_data, roi_data]
        
        prompt = get_tracking_pcb_prompt(roi_image_path)
        response_text, _ = call_gemini_vision(
            prompt, 
            image_data_list, 
            "Tracking PCB Expert", 
            verbose=True,
            temperature=1.0,
            thinking_level="high",
            media_resolution="MEDIA_RESOLUTION_HIGH"
        )
        result = parse_json_response(response_text)
        return {"tracking_pcb_result": result}
    except Exception as e:
        logger.error(f"PCB Node Error: {e}", exc_info=True)
        return {"tracking_pcb_result": {"error": str(e)}}

def result_aggregator_node(state: TrackingExpertState) -> Dict[str, Any]:
    """개별 Hotspot의 분석 결과를 종합 (Component Type 별 결과 처리)"""
    h_info = state.get("current_hotspot", {})
    conn_type = state.get("connection_type")
    
    # 해당되는 결과 추출
    result_data = {}
    if conn_type == "Terminal":
        result_data = state.get("tracking_terminal_result") or {}
    elif conn_type == "Plug":
        result_data = state.get("tracking_plug_result") or {}
    elif conn_type == "PCB":
        result_data = state.get("tracking_pcb_result") or {}
        
    conf = result_data.get("confidence", 0)
    verdict = result_data.get("verdict", "Unknown")
    reasoning = result_data.get("reasoning", "")
    visual_desc = result_data.get("visual_description", "")
    
    final_entry = {
        "hotspot_id": h_info.get("id"),
        "hotspot_info": h_info,
        "connection_type": conn_type,
        "specialist_result": result_data,
        "confidence": conf,
        "verdict": verdict,
        "reasoning": reasoning,
        "visual_description": visual_desc,
        "roi_image_path": state.get("roi_image_path")
    }
    
    logger.info(f"Aggregator: Recording result for Hotspot {h_info.get('id')} (Type: {conn_type}, Verdict: {verdict})")
    return {"analysis_results": [final_entry]}

def format_report_summary(analysis_results: list) -> str:
    """
    Node 3를 위한 구조화된 요약 보고서 생성 (Node 2 의견 강조)
    """
    summary = ""
    for res in analysis_results:
        hotspot = res.get('hotspot_info', {})
        # result_aggregator에서 'analysis_result' 키 사용
        specialist = res.get('specialist_result', {})
        conn_type = res.get('connection_type', 'None')
        
        if not specialist:
            summary += f"""
--- [Spot ID: {hotspot.get('id')}] ---
1. 발견된 특징 (Node 0 - Detection): {hotspot.get('suspected_feature', 'Unknown')}
2. 전문가 정밀 분석 (Node 2 - Specialist): 
   - 분석 불가 또는 특이사항 없음 ({conn_type})
-----------------------------------
"""
            continue

        summary += f"""
--- [Spot ID: {hotspot.get('id')}] ---
1. 발견된 특징 (Node 0 - Detection): {hotspot.get('suspected_feature', 'Unknown')}
2. 전문가 정밀 분석 (Node 2 - Specialist): 
   - **시각적 특징:** {specialist.get('visual_description', 'N/A')}
   - **전문가 판정:** {specialist.get('verdict', 'N/A')} (신뢰도: {specialist.get('confidence', 0)}%)
   - **판정 근거:** {specialist.get('reasoning', 'N/A')}
-----------------------------------
"""
    return summary

def verdict_node(state: TrackingExpertState) -> Dict[str, Any]:
    """모든 Hotspot 분석 결과를 종합하여 최종 리포트 생성 (LLM-based Verdict)"""
    results = state.get("analysis_results", [])
    
    if not results:
        return {
            "verdict_report": "트래킹 분석 결과 특이사항이 없습니다. (No Hotspots Detected)",
            "verdict_confidence": 0,
            "verdict_result": {}
        }
    
    # 1. Report Summary 작성 (LLM 입력용)
    report_summary = format_report_summary(results)
    
    # Max Confidence 찾기 (대표 결과 선정용)
    max_confidence = 0
    best_result = {}
    
    for res in results:
        h_info = res.get("hotspot_info", {})
        c_type = res.get("connection_type", "None")
        s_res = res.get("analysis_result", {})
        
        conf = 0
        if c_type != "None" and s_res:
            conf = s_res.get("confidence", 0)
        elif h_info:
            conf = h_info.get("severity_score", 0) * 0.5
            
        if conf > max_confidence:
            max_confidence = conf
            best_result = s_res
    
    # 2. LLM 호출
    prompt = get_final_verdict_prompt(report_summary)
    response_text, thinking_info = call_gemini_text(
        prompt=prompt,
        step_name="Tracking Verdict",
        verbose=True,
        temperature=1.0,
        thinking_level="high"
    )
    
    # 3. 결과 파싱
    llm_result = parse_json_response(response_text)
    
    # 4. 최종 리포트 구성
    conclusion = llm_result.get("conclusion", "판독 불가")
    probability = llm_result.get("probability", "None")
    key_evidence = llm_result.get("key_evidence", [])
    reasoning = llm_result.get("reasoning", "")
    
    # 최종 리포트 문자열 생성
    final_report_lines = [
        "[Tracking 전문가 최종 판정]",
        f"## 결론: {conclusion} ({probability})",
        "",
        "## 핵심 증거",
    ]
    for ev in key_evidence:
        final_report_lines.append(f"- {ev}")
    
    final_report_lines.append("")
    final_report_lines.append("## 종합 소견")
    final_report_lines.append(reasoning)
    
    # 디버깅용 정보
    final_report_lines.append("")
    final_report_lines.append("---")
    final_report_lines.append(f"(분석된 Spot 수: {len(results)}개, 최고 신뢰도: {max_confidence}%)")
    
    # 신뢰도 보정
    final_confidence = 0
    if "High" in probability:
        final_confidence = max(80, max_confidence)
    elif "Medium" in probability:
        final_confidence = max(50, max_confidence)
    else:
        final_confidence = max_confidence
        
    return {
        "verdict_report": "\n".join(final_report_lines),
        "verdict_confidence": final_confidence,
        "verdict_result": best_result # 대표 결과는 여전히 가장 점수 높은 Spot의 정보
    }
