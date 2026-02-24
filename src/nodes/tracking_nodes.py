"""
Tracking 전문가 노드 정의 (Map-Reduce Pattern)
"""
from typing import Dict, Any, Optional, List
import os
import json
import asyncio

from config import TOP_N_HOTSPOTS
import config
from src.utils.logging_config import setup_logger

from src.tools.experts.expert_utils import (
    call_gemini_vision,
    parse_json_response,
    call_gemini_text
)
from src.utils import async_retry_with_backoff, validate_state_keys
from src.prompts.common_prompts import get_component_classifier_prompt
from src.prompts.tracking_expert_prompts import (
    get_tracking_terminal_prompt,
    get_tracking_plug_prompt,
    get_tracking_pcb_prompt,
    get_tracking_supervisor_prompt,
    get_analyst_initial_prompt,
    get_analyst_reanalysis_prompt,
    get_critic_prompt
)
from src.models.verdict_models import TrackingSupervisorVerdict
from src.nodes.verdict_debate_nodes import (
    create_supervisor_verdict_node,
    create_verdict_analyst_node,
    create_verdict_critic_node,
    create_verdict_finalize_node
)

from src.states.tracking_state import TrackingExpertState
from src.states.common_state import WorkerState
from src.nodes.expert_worker_utils import crop_and_enhance_roi, classify_component
from src.utils.expert_image_utils import load_expert_images
import datetime

logger = setup_logger(__name__)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

async def analyze_hotspot_worker(state: WorkerState) -> Dict[str, List[Dict]]:
    """
    Unified Worker Node (Map-Reduce Pattern)
    1. ROI Crop + Enhancement
    2. Component Classification (Async)
    3. Specialist Analysis (Terminal/Plug/PCB)
    """
    hotspot = state["current_hotspot"]
    image_path = state["image_path"]
    hotspot_id = hotspot.get("id", "unknown")
    
    logger.info(f"Worker {hotspot_id}: Evidence collection started")
    
    try:
        # [Gen 2] Preprocessor 세분화 플래그 호환성
        if hotspot.get("_preprocessed"):
            roi_image_path = hotspot.get("roi_image_path", image_path)
            
            if hotspot.get("_classify_done"):
                connection_type = hotspot.get("component_type", "Unknown")
                logger.info(f"Worker {hotspot_id}: Using pre-processed classification ({connection_type})")
            else:
                logger.info(f"Worker {hotspot_id}: Pre-processed crop found, but classification needed")
                prompt = get_component_classifier_prompt(roi_image_path)
                connection_type = await classify_component(hotspot_id, roi_image_path, image_path, prompt)
        else:
            box_2d = hotspot.get("box_2d")
            roi_image_path = await crop_and_enhance_roi(hotspot_id, image_path, box_2d)
            prompt = get_component_classifier_prompt(roi_image_path)
            connection_type = await classify_component(hotspot_id, roi_image_path, image_path, prompt)

        specialist_result = None
        severity_score = 30
        report_confidence = 0
        evidence_quality = "low"
        is_critical = False
        observations = "No observation"
        worker_verdict = "N/A"
        
        # Routing based on component connection_type
        if "Terminal" in connection_type or "단자" in connection_type:
            specialist_result = await _analyze_specialist(
                hotspot_id, roi_image_path, image_path, get_tracking_terminal_prompt, "Tracking Terminal"
            )
        elif "Plug" in connection_type or "플러그" in connection_type:
            specialist_result = await _analyze_specialist(
                hotspot_id, roi_image_path, image_path, get_tracking_plug_prompt, "Tracking Plug"
            )
        elif "PCB" in connection_type or "기판" in connection_type:
            specialist_result = await _analyze_specialist(
                hotspot_id, roi_image_path, image_path, get_tracking_pcb_prompt, "Tracking PCB"
            )
        else:
            observations = f"Tracking 분석 대상 아님: {connection_type}"
            worker_verdict = observations
            logger.info(f"Worker {hotspot_id}: Skipped (Not Tracking Component)")
            
        if specialist_result:
            observations = specialist_result.get("visual_observation", specialist_result.get("visual_description", "N/A"))
            worker_verdict = f"[{specialist_result.get('verdict', 'Unknown')}] {specialist_result.get('reasoning', '')}"
            report_confidence = specialist_result.get("confidence", 0)
            verdict_cat = specialist_result.get("verdict", "")
            
            if verdict_cat == "트래킹" or "트래킹 진행" in verdict_cat or "High" in verdict_cat:
                severity_score = 80
                is_critical = True
                evidence_quality = "high"
            elif "트래킹 의심" in verdict_cat or "의심" in verdict_cat:
                severity_score = 60
                evidence_quality = "medium"
            else:
                severity_score = 30
                evidence_quality = "low"
                
            if config.SAVE_INDIVIDUAL_HOTSPOT_JSON:
                try:
                    output_dir = os.path.join(PROJECT_ROOT, "output", "tracking_analysis")
                    os.makedirs(output_dir, exist_ok=True)
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    file_path = os.path.join(output_dir, f"hotspot_{hotspot_id}_{timestamp}.json")
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(specialist_result, f, ensure_ascii=False, indent=2)
                except Exception as save_err:
                    logger.error(f"Worker {hotspot_id}: Failed to save result: {save_err}")
                    
        worker_report = {
            "id": hotspot_id,
            "type": "WorkerReport",
            "facts": {"visual_description": observations},
            "opinion": {
                "verdict": specialist_result.get("verdict", "Unknown") if specialist_result else "Indeterminate",
                "confidence": report_confidence,
                "reasoning": specialist_result.get("reasoning", "") if specialist_result else "Extraction failed"
            },
            "severity_score": severity_score,
            "evidence_quality": evidence_quality,
            "is_critical": is_critical,
            "_hotspot_info": hotspot,
            "_connection_type": connection_type,
            "_roi_image_path": roi_image_path
        }
        
        analysis_entry = {
            "hotspot_id": hotspot_id,
            "hotspot_info": hotspot,
            "roi_image_path": roi_image_path,
            "specialist_result": specialist_result,
            "connection_type": connection_type
        }
        
        return {
            "preliminary_assessments": [worker_report],
            "analysis_results": [analysis_entry]
        }
        
    except Exception as e:
        logger.error(f"Worker Error on Hotspot {hotspot_id}: {str(e)}")
        error_report = {
            "id": hotspot_id,
            "type": "WorkerReport",
            "facts": {"error": "분석 실패"},
            "opinion": {"verdict": "판독 보류", "confidence": 0, "reasoning": "분석 불가"},
            "_connection_type": "Unknown",
            "severity_score": 0
        }
        return {
            "preliminary_assessments": [error_report],
            "analysis_results": []
        }

async def _analyze_specialist(
    hotspot_id: str,
    roi_image_path: str,
    image_path: str,
    prompt_func,
    component_type: str
) -> Optional[Dict[str, Any]]:
    try:
        logger.info(f"Worker {hotspot_id}: Collecting {component_type} evidence...")
        original_data, roi_data = await load_expert_images(roi_image_path, image_path)
        prompt = prompt_func(roi_image_path)
        image_payload = [original_data, roi_data]
        
        def run_sync_call():
            return call_gemini_vision(
                prompt, 
                image_payload, 
                f"Worker #{hotspot_id} {component_type} Specialist", 
                verbose=True,
                temperature=1.0,
                thinking_level="high",
                media_resolution="MEDIA_RESOLUTION_HIGH"
            )
        
        # Rate Limiter 적용을 위해 async_retry_with_backoff 사용
        response_text, _ = await async_retry_with_backoff(
            lambda: asyncio.to_thread(run_sync_call),
            max_retries=3,
            context_name=f"Worker #{hotspot_id} {component_type} Specialist"
        )
        result = parse_json_response(response_text)
        return result
    except Exception as e:
        logger.error(f"Worker {hotspot_id}: {component_type} evidence error: {e}", exc_info=True)
        return None

# ===== Final Verdict Nodes =====
supervisor_verdict = create_supervisor_verdict_node(
    expert_type="tracking",
    get_supervisor_prompt_fn=get_tracking_supervisor_prompt,
    SupervisorVerdict=TrackingSupervisorVerdict
)

verdict_analyst_node = create_verdict_analyst_node(
    expert_type="tracking",
    get_initial_prompt_fn=get_analyst_initial_prompt,
    get_reanalysis_prompt_fn=get_analyst_reanalysis_prompt
)

verdict_critic_node = create_verdict_critic_node(
    expert_type="tracking",
    get_critic_prompt_fn=get_critic_prompt
)

verdict_finalize_node = create_verdict_finalize_node(
    expert_type="tracking"
)
