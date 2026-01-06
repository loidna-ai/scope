"""
Necking (반단선) 전문가 노드
멀티 핫스팟 루프 아키텍처 (Wire Focused)
"""
import json
import os
from typing import Dict, Any, List, Optional, TypedDict, Annotated
import operator

from langgraph.graph import MessagesState
from langchain_core.messages import SystemMessage, HumanMessage

from src.utils import crop_roi_from_box, load_image_safe, save_image_safe
from src.nodes.enhancement import ImageEnhancer
from src.tools.experts.expert_utils import (
    call_gemini_vision, 
    call_gemini_text, 
    parse_json_response,
    _load_image_data
)
from src.prompts.common_prompts import (
    get_multi_hotspot_prompt,
    get_component_classifier_prompt,
)
from src.prompts.necking_expert_prompts import (
    get_necking_wire_prompt,
    get_final_verdict_prompt
)



# --- State Definition ---
class NeckingExpertState(TypedDict):
    """Necking 전문가 그래프 상태"""
    # 기본 메시지 상태 (LangGraph 요구사항)
    messages: List[Any]
    
    # 이미지 경로
    image_path: str
    
    # 1. 탐지 단계 상태
    hotspots: List[Dict[str, Any]]  # 탐지된 모든 핫스팟
    hotspot_queue: Optional[List[Dict[str, Any]]] # 처리 대기 중인 핫스팟 큐
    
    # 2. 루프 처리 상태 (현재 핫스팟)
    current_hotspot: Optional[Dict[str, Any]]
    detector_result: Optional[Dict[str, Any]] # Raw detector output
    
    roi_image_path: Optional[str] # 현재 Crop된 이미지 경로
    
    # [Standardization]
    connection_type: Optional[str] # 부품 유형 문자열 (예: "Wire", "Terminal")
    
    # 3. 분석 결과 (개별)
    specialist_result: Optional[Dict[str, Any]]
    
    # 4. 결과 집계
    analysis_results: Annotated[List[Dict[str, Any]], operator.add] # 각 핫스팟별 분석 결과 누적
    
    # 5. 최종 판정
    verdict_report: Optional[str]
    verdict_confidence: Optional[float]
    verdict_result: Optional[Dict[str, Any]]

# --- Nodes ---

def hotspot_detector_node(state: NeckingExpertState) -> Dict[str, Any]:
    """
    Node 0: Hotspot Detector
    - 전체 이미지에서 다중 발화 지점(Hotspots) 탐색
    """
    image_path = state.get("image_path")
    if not image_path:
        return {"hotspots": []}
    
    print(f"\n📡 [Hotspot Detector] 다중 발화 지점 탐색 시작... (이미지: {image_path})")
    
    try:
        image_data = _load_image_data(image_path)
    except Exception as e:
        print(f"Error loading image: {e}")
        return {"hotspots": []}
    
    prompt = get_multi_hotspot_prompt(image_path)
    response_text, thinking_info = call_gemini_vision(
        prompt, 
        image_data, 
        "Hotspot Detector", 
        verbose=True,
        temperature=0.0
    )
    
    result = parse_json_response(response_text)
    hotspots = result.get("hotspots", [])
    
    # [Fix] Schema Mismatch Correction
    for h in hotspots:
        # Prompt returns 'suspected_feature', Node expects 'damage_type'
        if "damage_type" not in h and "suspected_feature" in h:
            h["damage_type"] = h["suspected_feature"]
        
        # Prompt might not return 'severity_score', set default
        if "severity_score" not in h:
            h["severity_score"] = 50 # Default priority score
            
    print(f"✅ [Hotspot Detector] 발견된 Hotspots: {len(hotspots)}개")
    for h in hotspots:
        print(f"   - ID {h.get('id')}: {h.get('damage_type')} (Score: {h.get('severity_score')})")
        
    return {"hotspots": hotspots}

def hotspot_manager_node(state: NeckingExpertState) -> Dict[str, Any]:
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
        print("\n⚖️ [Hotspot Manager] Hotspot 우선순위 정렬 및 Top-N 선별")
        # Score 내림차순 정렬
        sorted_hotspots = sorted(
            hotspots, 
            key=lambda x: x.get("severity_score", 0), 
            reverse=True
        )
        # Top 3 선별
        queue = sorted_hotspots[:3]
        print(f"✅ 선별된 Hotspots: {[h.get('id') for h in queue]}")
        
        # 첫 번째 Hotspot 바로 Pop (Loop 시작을 위해)
        if not queue:
             print("\n🏁 [Hotspot Manager] 처리할 Hotspot이 없습니다.")
             return {"hotspot_queue": [], "current_hotspot": None}
             
        current = queue[0]
        remaining = queue[1:]
        
        print(f"\n▶️ [Hotspot Manager] Processing Hotspot ID {current.get('id')} ({current.get('damage_type')})")
        
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
        print("\n🏁 [Hotspot Manager] 모든 Hotspot 처리 완료.")
        return {"current_hotspot": None}  # Loop 종료 신호

    current = queue[0]
    remaining = queue[1:]
    
    print(f"\n▶️ [Hotspot Manager] Processing Hotspot ID {current.get('id')} ({current.get('damage_type')})")
    
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

        "specialist_result": None # Reset for new loop
    }

def roi_crop_node(state: NeckingExpertState) -> Dict[str, Any]:
    """
    ROI 크롭 노드
    detector_result(current_hotspot)에서 box_2d 추출하여 크롭
    후처리로 2배 초해상도 향상 적용
    """
    from src.utils import crop_roi_from_box
    from src.nodes.enhancement import enhancement_node
    import cv2
    import numpy as np
    
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
        
        # 이미지 향상 적용
        print(f"✨ [Enhancement] ROI 이미지 2배 향상 적용 중...")
        try:
            # 1. 크롭된 이미지 로드
            cropped_img = cv2.imread(cropped_path)
            if cropped_img is None:
                raise ValueError("크롭된 이미지를 읽을 수 없습니다.")
                
            # 2. Enhancement Node 직접 호출 (State 구성 불필요)
            # ImageEnhancer 클래스 직접 사용이 더 깔끔할 수 있으나, 기존 구조 활용
            from src.nodes.enhancement import ImageEnhancer
            enhancer = ImageEnhancer()
            enhanced_img = enhancer.upscale(cropped_img)
            
            # 3. 향상된 이미지 저장 (덮어쓰기)
            cv2.imwrite(cropped_path, enhanced_img)
            print(f"✨ [Enhancement] 향상 완료: {cropped_path}")
            
        except Exception as enh_err:
             print(f"⚠️ Enhancement Failed: {enh_err}")
             # 향상 실패해도 원본 크롭 이미지는 유지됨
             
        return {"roi_image_path": cropped_path}
    except Exception as e:
        print(f"⚠️ Crop Failed: {e}")
        return {"roi_image_path": image_path}

def component_classifier_node(state: NeckingExpertState) -> Dict[str, Any]:
    """
    Node 1: Component Classifier
    - 크롭된 이미지를 분석하여 접속부 유형(Terminal/Splice/Plug/None) 식별
    """
    roi_image_path = state.get("roi_image_path")
    if not roi_image_path:
        return {"connection_type": "None"}
        
    print(f"\n🔍 [Component Classifier] 부품 유형 식별 중... (Dual Input: Context + Detail, ROI: {roi_image_path})")
    
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
            temperature=0.0
        )
        result = parse_json_response(response_text)
        
        # New Schema: deduced_type, visual_description
        deduced_type = result.get("deduced_type", "None")
        visual_description = result.get("visual_description", "")
        confidence = result.get("confidence", 0)
        reasoning = result.get("reasoning", "")
        
        print(f"👁️ [Observation] {visual_description}")
        print(f"✅ 판별 결과: {deduced_type} (신뢰도: {confidence}%)")
        
        return {
            "connection_type": deduced_type,
            "classifier_result": result
        }
    except Exception as e:
        print(f"⚠️ Component Classifier Error: {e}")
        return {
            "connection_type": "None",
            "classifier_result": {"error": str(e)}
        }

def necking_wire_node(state: NeckingExpertState) -> Dict[str, Any]:
    """
    Step 3: Specialist Analysis (통합 정밀 분석)
    """
    print(f"\n⚡ [Necking] Node 3: Wire Analysis (2 Images: Context + ROI)")
    roi_path = state.get("roi_image_path")
    original_image_path = state.get("image_path")
    
    prompt = get_necking_wire_prompt(roi_path)
    
    try:
        # 두 장의 이미지를 모두 로드
        roi_data = _load_image_data(roi_path)
        original_data = _load_image_data(original_image_path)
        
        # 리스트로 전달 [원본(Context), ROI(Detail)]
        image_data_list = [original_data, roi_data]

        response_text, _ = call_gemini_vision(
            prompt, 
            image_data_list, 
            "Necking Specialist Analysis", 
            verbose=True
        )
    except Exception as e:
        print(f"Error loading images: {e}")
        return {"specialist_result": {}}
    
    result = parse_json_response(response_text)
    
    return {"specialist_result": result}

def result_aggregator_node(state: NeckingExpertState) -> Dict[str, Any]:
    """
    Loop End: 현재 핫스팟의 모든 결과를 하나로 묶어서 리스트에 추가
    """
    current_hotspot = state.get("current_hotspot", {})
    conn_type = state.get("connection_type")
    specialist_res = state.get("specialist_result")
    
    # 종합 결과 딕셔너리 생성
    entry = {
        "hotspot_id": current_hotspot.get("id"),
        "hotspot_info": current_hotspot,
        "connection_type": conn_type,
        "specialist_result": specialist_res,
        "roi_image_path": state.get("roi_image_path") # 디버깅 시각화용
    }
    
    # analysis_results 리스트에 추가 (operator.add에 의해 append됨)
    return {"analysis_results": [entry]}

def format_report_summary(analysis_results: list) -> str:
    """
    Node 3를 위한 구조화된 요약 보고서 생성
    """
    summary = ""
    for res in analysis_results:
        hotspot = res.get('hotspot_info', {})
        specialist = res.get('specialist_result', {})
        conn_type = res.get('connection_type', 'None')
        
        # Specialist 결과가 없는 경우 처리
        if not specialist:
            summary += f"""
--- [Spot ID: {hotspot.get('id')}] ---
1. 발견된 특징 (Node 0 - Detection): {hotspot.get('damage_type', 'Unknown')}
2. 전문가 정밀 분석 (Node 2 - Specialist): 
   - 분석 불가 또는 특이사항 없음 ({conn_type})
-----------------------------------
"""
            continue

        summary += f"""
--- [Spot ID: {hotspot.get('id')}] ---
1. 발견된 특징 (Node 0 - Detection): {hotspot.get('damage_type', 'Unknown')}
2. 전문가 정밀 분석 (Node 2 - Specialist): 
   - **시각적 특징:** {specialist.get('visual_description', 'N/A')}
   - **전문가 판정:** {specialist.get('verdict', 'N/A')} (신뢰도: {specialist.get('confidence', 0)}%)
   - **판정 근거:** {specialist.get('reasoning', 'N/A')}
-----------------------------------
"""
    return summary

def verdict_node(state: NeckingExpertState) -> Dict[str, Any]:
    """
    Step 4: Final Verdict (최종 판정)
    """
    print("--- [Necking] Node 4: Final Verdict ---")
    
    results = state.get("analysis_results", [])
    
    if not results:
        return {
            "verdict_report": "분석된 특이점이 없습니다. (No Hotspots Detected)",
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
        s_res = res.get("specialist_result", {})
        
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
    response_text, _ = call_gemini_text(
        prompt=prompt,
        step_name="Necking Final Verdict",
        verbose=True
    )
    
    # 3. 결과 파싱
    llm_result = parse_json_response(response_text)
    
    conclusion = llm_result.get("conclusion", "판독 불가")
    probability = llm_result.get("probability", "None")
    key_evidence = llm_result.get("key_evidence", [])
    reasoning = llm_result.get("reasoning", "")
    
    # 4. 리포트 생성
    final_report_lines = [
        "[Necking 전문가 최종 판정]",
        f"## 결론: {conclusion} ({probability})",
        "",
        "## 핵심 증거",
    ]
    for ev in key_evidence:
        final_report_lines.append(f"- {ev}")
    
    final_report_lines.append("")
    final_report_lines.append("## 종합 소견")
    final_report_lines.append(reasoning)
    
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
        "verdict_result": best_result # 대표 결과
    }
