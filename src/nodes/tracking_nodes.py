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
from src.prompts.tracking_expert_prompts import (
    get_tracking_terminal_prompt,
    get_tracking_plug_prompt,
    get_tracking_pcb_prompt,
    get_tracking_supervisor_prompt,
    get_analyst_initial_prompt,
    get_analyst_reanalysis_prompt,
    get_critic_prompt
)
from src.models.tracking_models import (
    TrackingTerminalEvidenceResult,
    TrackingPlugEvidenceResult,
    TrackingPCBEvidenceResult
)
from src.utils.expert_api_utils import (
    call_evidence_api,
    call_supervisor_api
)
from src.nodes.verdict_debate_nodes import (
    create_supervisor_verdict_node,
    create_verdict_analyst_node,
    create_verdict_critic_node,
    create_verdict_finalize_node
)
from src.models.verdict_models import TrackingSupervisorVerdict

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
                prompt = get_component_classifier_prompt(roi_image_path, box_2d=hotspot.get("box_2d"))
                connection_type = await classify_component(hotspot_id, roi_image_path, image_path, prompt)
        else:
            box_2d = hotspot.get("box_2d")
            roi_image_path = await crop_and_enhance_roi(hotspot_id, image_path, box_2d)
            prompt = get_component_classifier_prompt(roi_image_path, box_2d=box_2d)
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
                hotspot_id, roi_image_path, image_path, get_tracking_terminal_prompt, TrackingTerminalEvidenceResult, "Tracking Terminal"
            )
        elif "Plug" in connection_type or "플러그" in connection_type:
            specialist_result = await _analyze_specialist(
                hotspot_id, roi_image_path, image_path, get_tracking_plug_prompt, TrackingPlugEvidenceResult, "Tracking Plug"
            )
        elif "PCB" in connection_type or "기판" in connection_type:
            specialist_result = await _analyze_specialist(
                hotspot_id, roi_image_path, image_path, get_tracking_pcb_prompt, TrackingPCBEvidenceResult, "Tracking PCB"
            )
        else:
            observations = f"Tracking 분석 대상 아님: {connection_type}"
            worker_verdict = observations
            logger.info(f"Worker {hotspot_id}: Skipped (Not Tracking Component)")
            
        if specialist_result:
            observations = specialist_result.visual_description
            worker_verdict = f"[{specialist_result.verdict}] {specialist_result.reasoning}"
            report_confidence = specialist_result.confidence
            
            # Evidence-First: Bypass severity logic, set default
            severity_score = 50
            is_critical = False
            evidence_quality = "medium"
                    
            if config.SAVE_INDIVIDUAL_HOTSPOT_JSON:
                try:
                    output_dir = os.path.join(PROJECT_ROOT, "output", "tracking_analysis")
                    os.makedirs(output_dir, exist_ok=True)
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    file_path = os.path.join(output_dir, f"hotspot_{hotspot_id}_{timestamp}.json")
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(specialist_result.model_dump(), f, ensure_ascii=False, indent=2)
                except Exception as save_err:
                    logger.error(f"Worker {hotspot_id}: Failed to save result: {save_err}")
                    
        worker_report = {
            "id": hotspot_id,
            "type": "WorkerReport",
            "facts": {
                "visual_description": observations,
                "extracted_evidence": [ev.model_dump() for ev in specialist_result.step5_extracted_evidence] if specialist_result and hasattr(specialist_result, "step5_extracted_evidence") else []
            },
            "opinion": {
                "verdict": "판독 보류 (Evidence Collected)",
                "confidence": 0,
                "reasoning": "자세한 증거 목록이 생성되었습니다."
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
    evidence_model,
    component_type: str
) -> Optional[Any]:
    try:
        logger.info(f"Worker {hotspot_id}: Collecting {component_type} evidence...")
        original_data, roi_data = await load_expert_images(roi_image_path, image_path)
        prompt = prompt_func(roi_image_path)
        
        client = get_genai_client()
        model_name = os.environ.get("GEMINI_MODEL_NAME", config.GEMINI_MODEL_NAME)
        
        parts = [prompt]
        for img_data in [original_data, roi_data]:
            parts.append(types.Part.from_bytes(data=img_data, mime_type="image/jpeg"))
        
        async def _call_evidence_wrapper(**kwargs):
            return await call_evidence_api(
                client=kwargs["client"],
                model_name=kwargs["model_name"],
                parts=kwargs["parts"],
                response_schema=evidence_model,
                thinking_level="high",
                temperature=1.0,
                context_name=kwargs.get("context_name", f"Worker #{hotspot_id} {component_type} Evidence")
            )
        
        response = await async_retry_with_backoff(
            _call_evidence_wrapper,
            client=client,
            model_name=model_name,
            parts=parts,
            context_name=f"Worker #{hotspot_id} {component_type} Evidence",
            max_retries=5
        )
        
        evidence_result = evidence_model.model_validate_json(response.text)
        return evidence_result
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
