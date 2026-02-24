"""
Aging Expert 노드 정의 (Map-Reduce Pattern)
절연열화/트래킹 전문가
"""
# Standard library imports
import os
import json
import datetime
from typing import Dict, Any, List, Optional

# Third-party imports
import cv2
from google.genai import types

# Local imports - Config
from config import TOP_N_HOTSPOTS
import config

# [Mitigation] API 부하 방지를 위한 동시 실행 제한 세마포어
# 미리보기 모델(gemini-3-flash-preview)의 동시 요청 제한(Concurrency Limit)에 대응

# Define Project Root for centralized output
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Local imports - Utils and Tools
from src.utils import async_retry_with_backoff, validate_state_keys, get_genai_client
from src.utils.logging_config import setup_logger
from src.utils.expert_api_utils import call_evidence_api
from src.prompts.common_prompts import get_component_classifier_prompt
from src.prompts.aging_expert_prompts import (
    get_aging_wire_prompt,
    get_aging_PCB_prompt,
    get_aging_supervisor_prompt,
    get_analyst_initial_prompt,
    get_analyst_reanalysis_prompt,
    get_critic_prompt
)
from src.models.verdict_models import AgingSupervisorVerdict
from src.models.aging_models import AgingWireEvidenceResult, AgingPCBEvidenceResult
from src.nodes.verdict_debate_nodes import (
    create_supervisor_verdict_node,
    create_verdict_analyst_node,
    create_verdict_critic_node,
    create_verdict_finalize_node
)

from src.states.common_state import WorkerState
from src.states.aging_state import AgingExpertState
from src.nodes.expert_worker_utils import crop_and_enhance_roi, classify_component
from src.utils.expert_image_utils import load_expert_images

# Initialize logger
logger = setup_logger(__name__)

async def analyze_hotspot_worker(state: WorkerState) -> Dict[str, List[Dict]]:
    """
    Unified Worker Node (Map-Reduce Pattern)
    1. ROI Crop + Enhancement
    2. Component Classification (Async)
    3. Specialist Analysis (Wire/PCB)
    """
    # 🔥 Input State 검증 (LangGraph Best Practice)
    validate_state_keys(
        state,
        required_keys=["current_hotspot", "image_path"],
        context="Worker Input"
    )

    hotspot = state["current_hotspot"]
    image_path = state["image_path"]
    hotspot_id = hotspot.get("id", "unknown")

    logger.info(f"Worker {hotspot_id}: Evidence collection started")
    
    try:
        # [Gen 2] Preprocessor 세분화 플래그 호환성
        if hotspot.get("_preprocessed"):
            roi_image_path = hotspot.get("roi_image_path", image_path)
            connection_type = hotspot.get("component_type", "Unknown")
            logger.info(
                f"Worker {hotspot_id}: Using pre-processed (crop+classify+enhance): {roi_image_path}"
            )
            # 부분 실패 보정: 전처리기에서 분류 실패 시 재분류
            if not hotspot.get("_classify_done") and connection_type == "Unknown":
                logger.info(f"Worker {hotspot_id}: Re-classifying (preprocessor classification failed)")
                prompt = get_component_classifier_prompt(roi_image_path)
                connection_type = await classify_component(hotspot_id, roi_image_path, image_path, prompt)
        else:
            # Fallback: preprocessor_node를 거치지 않은 경우 직접 처리
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
        
        # Component Routing loosely based on component connection_type
        if "Wire" in connection_type or "전선" in connection_type:
            specialist_result = await _analyze_specialist(
                hotspot_id=hotspot_id,
                roi_image_path=roi_image_path,
                image_path=image_path,
                prompt_func=get_aging_wire_prompt,
                evidence_model=AgingWireEvidenceResult,
                component_type="Aging Wire"
            )
        elif "PCB" in connection_type or "기판" in connection_type:
            specialist_result = await _analyze_specialist(
                hotspot_id=hotspot_id,
                roi_image_path=roi_image_path,
                image_path=image_path,
                prompt_func=get_aging_PCB_prompt,
                evidence_model=AgingPCBEvidenceResult,
                component_type="Aging PCB"
            )
        else:
            observations = f"Aging 분석 대상 아님: {connection_type}"
            worker_verdict = observations
            logger.info(f"Worker {hotspot_id}: Skipped (Not Aging Component)")
            
        if specialist_result:
            # Pydantic model_dump() dict 호환 (Wire는 step6_verdict 존재, PCB는 직렬화된 dict에 접근)
            if "step6_verdict" in specialist_result:
                s6 = specialist_result["step6_verdict"]
                verdict_cat = s6.get("conclusion", "Unknown")
                report_reasoning = s6.get("final_reasoning", "")
                worker_verdict = f"[{verdict_cat}] {report_reasoning}"
                report_confidence = s6.get("confidence_score", 0)
                
                # 합성 Observations
                try:
                    s4 = specialist_result.get("step4_insulation_inspection", {})
                    z1 = s4.get("zone1_color_texture", {})
                    z2 = s4.get("zone2_mechanical", {})
                    z3 = s4.get("zone3_thermal_shrinkage", {})
                    obs_parts = [
                        f"Zone 1 (색상/질감): {z1.get('color_degradation', '')[:100]}...",
                        f"Zone 2 (기계적 물성): {z2.get('hardening_brittleness', '')[:100]}...",
                        f"Zone 3 (열수축/박리): {z3.get('shrinkage_exposure', '')[:100]}..."
                    ]
                    observations = " | ".join(obs_parts)
                except Exception:
                    observations = "관찰 결과 합성 실패"
            else:
                # PCB나 기존 방식
                observations = specialist_result.get("visual_observation", "N/A")
                verdict_cat = specialist_result.get("verdict", "Unknown")
                report_reasoning = specialist_result.get("reasoning", "")
                worker_verdict = f"[{verdict_cat}] {report_reasoning}"
                report_confidence = specialist_result.get("confidence", 0)
            
            # severity (경년열화/절연열화 판정 기준)
            if "경년열화" in verdict_cat and "아님" not in verdict_cat and "의심" not in verdict_cat:
                severity_score = 80
                is_critical = True
                evidence_quality = "high"
            elif "절연열화" in verdict_cat and "아님" not in verdict_cat and "의심" not in verdict_cat:
                severity_score = 80
                is_critical = True
                evidence_quality = "high"
            elif "열화 진행" in verdict_cat or "트래킹" in verdict_cat or "심각" in verdict_cat:
                severity_score = 80
                is_critical = True
                evidence_quality = "high"
            elif "경년열화 의심" in verdict_cat or "절연열화 의심" in verdict_cat or "의심" in verdict_cat:
                severity_score = 60
                evidence_quality = "medium"
            else:
                severity_score = 30
                evidence_quality = "low"
            
            if config.SAVE_INDIVIDUAL_HOTSPOT_JSON:
                try:
                    output_dir = os.path.join(PROJECT_ROOT, "output", "aging_analysis")
                    os.makedirs(output_dir, exist_ok=True)
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"hotspot_{hotspot_id}_{timestamp}.json"
                    file_path = os.path.join(output_dir, filename)
                    save_data = specialist_result if isinstance(specialist_result, dict) else specialist_result.model_dump()
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(save_data, f, ensure_ascii=False, indent=2)
                    logger.info(f"Worker {hotspot_id}: Analysis result saved to {file_path}")
                except Exception as save_err:
                    logger.error(f"Worker {hotspot_id}: Failed to save result: {save_err}")

            logger.info(f"Worker {hotspot_id}: Evidence: {observations} (Score: {severity_score})")

        logger.info(f"Worker {hotspot_id}: Evidence collection completed")

        worker_report = {
            "id": hotspot_id,
            "type": "WorkerReport",
            "facts": {"visual_description": observations},
            "opinion": {
                "verdict": verdict_cat if specialist_result else "Indeterminate",
                "confidence": report_confidence,
                "reasoning": report_reasoning if specialist_result else "Extraction failed"
            },
            "severity_score": severity_score,
            "evidence_quality": evidence_quality,
            "is_critical": is_critical,
            "_hotspot_info": hotspot,
            "_connection_type": connection_type,
            "_roi_image_path": roi_image_path
        }
        
        # [Added] Notebook 호환성을 위한 analysis_results 포맷 (Contact/Deform/Necking과 동일)
        sr_conclusion = verdict_cat if specialist_result else "판독 불가"
        reasoning_text = report_reasoning if specialist_result else ""
        if not reasoning_text:
            reasoning_text = "분석 근거 없음"

        analysis_entry = {
            "hotspot_id": hotspot_id,
            "hotspot_info": hotspot,
            "roi_image_path": roi_image_path,
            "specialist_result": {
                "conclusion": sr_conclusion,
                "verdict": worker_verdict,
                "confidence": report_confidence,
                "visual_description": observations,
                "reasoning": reasoning_text
            },
            "connection_type": connection_type
        }
        
        return {
            "preliminary_assessments": [worker_report],
            "analysis_results": [analysis_entry]
        }
        
    except Exception as e:
        logger.error(f"Worker Error on Hotspot {hotspot_id}: {str(e)}")
        # 에러 발생 시 구조화된 에러 리포트 반환
        error_report = {
            "id": hotspot_id,
            "type": "WorkerReport",
            "facts": {"error": "분석 실패"},
            "opinion": {"verdict": "판독 보류", "confidence": 0, "reasoning": "분석 불가 (시스템 데이터 부족)"},
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
) -> Optional[Dict[str, Any]]:
    """
    Specialist 분석 공통 로직 (Wire/PCB)
    Contact/Deform/Necking과 동일한 call_evidence_api 패턴
    """
    try:
        logger.info(f"Worker {hotspot_id}: Collecting {component_type} evidence...")
        logger.debug(f"Worker {hotspot_id}: Waiting for Evidence API via semaphore...")

        # Blocking I/O offloading to thread (공통 이미지 로더 사용)
        original_data, roi_data = await load_expert_images(roi_image_path, image_path)
        prompt = prompt_func(roi_image_path)

        # 이미지 파트 구성 (Contact/Deform/Necking과 동일)
        parts = [prompt]
        for img_data in [original_data, roi_data]:
            parts.append(types.Part.from_bytes(
                data=img_data,
                mime_type="image/jpeg"
            ))

        client = get_genai_client()
        model_name = os.environ.get("GEMINI_MODEL_NAME", config.GEMINI_MODEL_NAME)

        # 🔥 Centralized Retry Logic with Common API Function
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

        # Pydantic 안전 파싱
        evidence_result = evidence_model.model_validate_json(response.text)
        return evidence_result.model_dump()
    except Exception as e:
        logger.error(f"Worker {hotspot_id}: {component_type} evidence collection final failure: {e}", exc_info=True)
        return None

# ===== Final Verdict Nodes =====
supervisor_verdict = create_supervisor_verdict_node(
    expert_type="aging",
    get_supervisor_prompt_fn=get_aging_supervisor_prompt,
    SupervisorVerdict=AgingSupervisorVerdict
)

verdict_analyst_node = create_verdict_analyst_node(
    expert_type="aging",
    get_initial_prompt_fn=get_analyst_initial_prompt,
    get_reanalysis_prompt_fn=get_analyst_reanalysis_prompt
)

verdict_critic_node = create_verdict_critic_node(
    expert_type="aging",
    get_critic_prompt_fn=get_critic_prompt
)

verdict_finalize_node = create_verdict_finalize_node(
    expert_type="aging"
)
