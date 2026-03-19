"""
Deform (압착·손상) 전문가 노드
Map-Reduce 아키텍처 with Send API (Wire Focused)
"""
# Standard library imports
import json
import os
import asyncio
import re
import datetime
from typing import Dict, Any, List, Optional, TypedDict, Annotated
import operator

# Third-party imports
import cv2
from google.genai import types

# Local imports - Config
import config
from config import TOP_N_HOTSPOTS

# [Mitigation] API 부하 방지를 위한 동시 실행 제한 세마포어
# Gemini 2.5 Flash의 동시 요청 제한(Concurrency Limit)에 대응


# Define Project Root for centralized output
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Local imports - Utils and Tools
from src.utils import crop_roi_from_box, async_retry_with_backoff, validate_state_keys, get_genai_client
from src.utils.logging_config import setup_logger
from src.utils.expert_config import get_safety_settings, THINKING_SUPPORTED_MODELS, LARGE_ROI_THRESHOLD, MAX_DEBATE_ITERATIONS
from src.utils.expert_api_utils import validate_gemini_response, extract_finish_reason, call_classifier_api, call_evidence_api, call_supervisor_api, call_analyst_api, call_critic_vision_api, call_critic_text_api
from src.utils.expert_image_utils import load_expert_images, ExpertImageLoader
from src.utils.expert_report_utils import format_report_summary, extract_critiqued_hotspots

# Initialize logger
logger = setup_logger(__name__)

# Local imports - Prompts
from src.prompts.common_prompts import get_component_classifier_prompt
from src.prompts.deform_expert_prompts import (
    get_deform_supervisor_prompt,
    get_deform_wire_prompt,
    get_analyst_initial_prompt,
    get_analyst_reanalysis_prompt,
    get_critic_prompt
)

# Local imports - Models
from src.models.deform_models import DeformEvidenceResult
from src.models.verdict_models import DeformSupervisorVerdict
from src.models.component_models import ComponentClassification

# Local imports - State
from src.states.deform_state import WorkerState, DeformExpertState
from src.nodes.verdict_debate_nodes import (
    create_supervisor_verdict_node,
    create_verdict_analyst_node,
    create_verdict_critic_node,
    create_verdict_finalize_node
)

# Local imports - Expert Utils
from src.nodes.expert_worker_utils import crop_and_enhance_roi, classify_component

# ===== Worker Node =====

# Helper functions for ROI crop and classification are now imported from src.nodes.expert_worker_utils


async def _collect_evidence(
    hotspot_id: str,
    connection_type: str,
    roi_image_path: str,
    image_path: str
) -> Dict[str, Any]:
    """
    증거 수집 로직 (Wire 타입일 때만)
    
    Args:
        hotspot_id: Hotspot ID (로깅용)
        connection_type: 컴포넌트 타입
        roi_image_path: ROI 이미지 경로
        image_path: 원본 이미지 경로
        
    Returns:
        증거 수집 결과 딕셔너리 (observations, severity_score, report_confidence, evidence_quality, is_critical, evidence_result, worker_verdict)
    """
    observations = ""
    severity_score = 0
    report_confidence = 0
    evidence_quality = "low"
    is_critical = False
    evidence_result = None
    worker_verdict = ""
    
    if "Wire" not in connection_type:
        observations = f"Wire가 아님: {connection_type}"
        worker_verdict = observations
        logger.info(f"Worker {hotspot_id}: Skipped (Not Wire)")
        return {
            "observations": observations,
            "severity_score": severity_score,
            "report_confidence": report_confidence,
            "evidence_quality": evidence_quality,
            "is_critical": is_critical,
            "evidence_result": evidence_result,
            "worker_verdict": worker_verdict
        }
    
    try:
        logger.info(f"Worker {hotspot_id}: Collecting Wire evidence...")
        logger.debug(f"Worker {hotspot_id}: Waiting for Evidence API via semaphore...")
        
        # Blocking I/O offloading to thread (공통 이미지 로더 사용)
        original_data, roi_data = await load_expert_images(roi_image_path, image_path)
        
        prompt = get_deform_wire_prompt(roi_image_path)
        
        client = get_genai_client()
        model_name = os.environ.get("GEMINI_MODEL_NAME", config.GEMINI_MODEL_NAME)
        
        # 이미지 파트 구성
        parts = [prompt]
        for img_data in [original_data, roi_data]:
            parts.append(types.Part.from_bytes(
                data=img_data,
                mime_type="image/jpeg"
            ))
        
        # 🔥 Centralized Retry Logic with Common API Function
        async def _call_evidence_wrapper(**kwargs):
            return await call_evidence_api(
                client=kwargs["client"],
                model_name=kwargs["model_name"],
                parts=kwargs["parts"],
                response_schema=DeformEvidenceResult,
                thinking_level="high",
                temperature=1.0,
                context_name=kwargs.get("context_name", f"Worker #{hotspot_id} Evidence")
            )
        
        response = await async_retry_with_backoff(
            _call_evidence_wrapper,
            client=client,
            model_name=model_name,
            parts=parts,
            context_name=f"Worker #{hotspot_id} Evidence",
            max_retries=5
        )
        
        # Pydantic 안전 파싱
        evidence_result = DeformEvidenceResult.model_validate_json(response.text)
        
        # Extract Evidence (Pydantic 객체에서 추출)
        step4 = evidence_result.step4_geometric_measurement
        
        # Observations Summary (Zone 2, 3, 4 정보 조합)
        geometric_features = []
        if step4.zone2_transition_gradient.width_change_observation:
            geometric_features.append(f"Width Change: {step4.zone2_transition_gradient.width_change_observation}")
        if step4.zone3_terminal_apex.terminal_shape_observation:
            geometric_features.append(f"Terminal Shape: {step4.zone3_terminal_apex.terminal_shape_observation}")
        if step4.zone4_melted_marks_beads.bead_scan:
            geometric_features.append(f"Bead: {step4.zone4_melted_marks_beads.bead_scan}")

        observations = " | ".join(geometric_features) if geometric_features else "기하학적 계측 완료"
        
        if hasattr(evidence_result, 'step5_extracted_evidence'):
            # 5단계 구조 (Evidence-First)
            severity_score = hotspot.get("severity_score", 50)  # 탐지 단계의 심각도 점수 유지 (v0.5.3)
            is_critical = False
            evidence_quality = "medium"
            report_confidence = 0
            worker_verdict = "판독 보류 (Evidence Collected)"
        else:
            # 기존 레거시 코드 대응 (오류 방지)
            severity_score = 0
            is_critical = False
            evidence_quality = "low"
            report_confidence = 0
            worker_verdict = "판단 불가"
        
        # [Phase 9] 개별 분석 결과 파일 저장 (Persistence) - config.SAVE_INDIVIDUAL_HOTSPOT_JSON=True일 때만
        if config.SAVE_INDIVIDUAL_HOTSPOT_JSON:
            try:
                output_dir = os.path.join(PROJECT_ROOT, "output", "deform_analysis")
                os.makedirs(output_dir, exist_ok=True)
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"hotspot_{hotspot_id}_{timestamp}.json"
                file_path = os.path.join(output_dir, filename)
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(evidence_result.model_dump(), f, ensure_ascii=False, indent=2)
                logger.info(f"Worker {hotspot_id}: Analysis result saved to {file_path}")
            except Exception as save_err:
                logger.error(f"Worker {hotspot_id}: Failed to save result: {save_err}")

        logger.info(f"Worker {hotspot_id}: Evidence: {observations} (Score: {severity_score})")
        
    except Exception as e:
        # Fallback: 오류 메시지 기록
        logger.error(f"Worker {hotspot_id}: Evidence collection final failure: {e}", exc_info=True)
        observations = f"분석 최종 실패: {str(e)}"
        worker_verdict = observations
    
    return {
        "observations": observations,
        "severity_score": severity_score,
        "report_confidence": report_confidence,
        "evidence_quality": evidence_quality,
        "is_critical": is_critical,
        "evidence_result": evidence_result,
        "worker_verdict": worker_verdict
    }


async def analyze_hotspot_worker(state: WorkerState) -> Dict[str, List[Dict]]:
    """
    Unified Worker Node (Map-Reduce Pattern) - Async for True Parallel Execution
    
    통합 작업:
    1. ROI Crop + Enhancement
    2. Component Classification (Async)
    3. Evidence Collection (Async, Wire Only)
    
    Returns:
        {"preliminary_assessments": [assessment_dict]}
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
        # ===== Step 1 & 2: ROI Crop + Enhancement + Classification =====
        if hotspot.get("_preprocessed"):
            # [#5 Preprocessor] 메인 그래프 전처리 결과 사용 (Crop+Classification+Enhancement 완료)
            roi_image_path = hotspot.get("roi_image_path", image_path)
            connection_type = hotspot.get("component_type", "Unknown")
            logger.info(
                f"Worker {hotspot_id}: Using pre-processed (crop+classify+enhance): {roi_image_path}"
            )
            # 부분 실패 보정: 전처리기에서 분류 실패 시 재분류
            if not hotspot.get("_classify_done") and connection_type == "Unknown":
                logger.info(f"Worker {hotspot_id}: Re-classifying (preprocessor classification failed)")
                prompt = get_component_classifier_prompt(roi_image_path, box_2d=hotspot.get("box_2d"))
                connection_type = await classify_component(hotspot_id, roi_image_path, image_path, prompt)
        else:
            # Fallback (직접 처리)
            box_2d = hotspot.get("box_2d")
            roi_image_path = await crop_and_enhance_roi(hotspot_id, image_path, box_2d)
            prompt = get_component_classifier_prompt(roi_image_path, box_2d=box_2d)
            connection_type = await classify_component(hotspot_id, roi_image_path, image_path, prompt)

        # ===== Step 3: Evidence Collection (Wire Only - Async) =====
        evidence_data = await _collect_evidence(hotspot_id, connection_type, roi_image_path, image_path)
        observations = evidence_data["observations"]
        severity_score = evidence_data["severity_score"]
        report_confidence = evidence_data["report_confidence"]
        evidence_quality = evidence_data["evidence_quality"]
        is_critical = evidence_data["is_critical"]
        evidence_result = evidence_data["evidence_result"]
        worker_verdict = evidence_data["worker_verdict"]
        
        # ===== Return Assessment (Detailed Worker Report) =====
        # [Refactored] "Reasoned Opinion" 구조에 맞춰 상세 데이터 반환
        
        worker_report = {
            "id": hotspot_id,
            "type": "WorkerReport",
            
            # 1. 근거 (Facts) - 측정값 전체 (Step 1~4)
            "facts": {},
            
            # 2. 의견 (Opinion) - 판단 및 상세 논리 (Step 5, 6)
            "opinion": {},
            
            # Compatibility fields (기존 로직 호환성 유지)
            "severity_score": severity_score,
            "evidence_quality": evidence_quality,
            "is_critical": is_critical,
            "_hotspot_info": hotspot,
            "_connection_type": connection_type,
            "_roi_image_path": roi_image_path
        }
    
        if evidence_result:
            worker_report["facts"] = {
                "global_arrangement": evidence_result.step1_context_analysis.global_arrangement,
                "fire_pattern": evidence_result.step1_context_analysis.fire_pattern,
                "identified_location": evidence_result.step2_location_mapping.identified_location,
                "crop_description": evidence_result.step3_crop_identification.crop_description,
                "reference_shaft_shape_observation": evidence_result.step4_geometric_measurement.zone1_reference_shaft.reference_shaft_shape_observation,
                "surface_visual_check": evidence_result.step4_geometric_measurement.zone1_reference_shaft.surface_visual_check,
                "width_change_observation": evidence_result.step4_geometric_measurement.zone2_transition_gradient.width_change_observation,
                "boundary_visual_check": evidence_result.step4_geometric_measurement.zone2_transition_gradient.boundary_visual_check,
                "terminal_shape_observation": evidence_result.step4_geometric_measurement.zone3_terminal_apex.terminal_shape_observation,
                "terminal_width_comparison": evidence_result.step4_geometric_measurement.zone3_terminal_apex.terminal_width_comparison,
                "strand_state_observation": evidence_result.step4_geometric_measurement.zone3_terminal_apex.strand_state_observation,
                "bead_scan": evidence_result.step4_geometric_measurement.zone4_melted_marks_beads.bead_scan
            }
            worker_report["opinion"] = {
                "verdict": "판독 보류 (Evidence Collected)",
                "confidence": 0,
                "reasoning": "자세한 증거 목록이 생성되었습니다."
            }
            # Extracted Evidence 데이터 패스-스루
            worker_report["facts"]["extracted_evidence"] = [ev.model_dump() for ev in evidence_result.step5_extracted_evidence] if hasattr(evidence_result, 'step5_extracted_evidence') else []
        else:
            # 분석 실패 또는 Wire 아님 등의 경우 빈 값 처리
            worker_report["facts"] = {"error": "No evidence collected"}
            worker_report["opinion"] = {"verdict": "Indeterminate", "confidence": 0, "reasoning": "Extraction failed"}
    
        # [Added] Notebook 호환성을 위한 analysis_results 포맷 (Reordered)
        sr_conclusion = "판독 보류"
        
        # reasoning 추출
        reasoning_text = "자세한 증거 목록이 생성되었습니다."
        
        analysis_entry = {
            "hotspot_id": hotspot_id,
            "hotspot_info": hotspot,
            "roi_image_path": roi_image_path,
            "specialist_result": {
                "conclusion": sr_conclusion,      # conclusion만 (시각화 제목용)
                "verdict": worker_verdict,        # 판정 결론 (Conclusion + Reasoning, .md 저장용)
                "confidence": report_confidence,  # confidence_score (0–100)
                "visual_description": observations, # 시각적 특징 (Taper, Apex 등)
                "reasoning": reasoning_text       # 논리적 근거 (Arbiter Fact Check용)
            },
            "connection_type": connection_type
        }
    
        logger.info(f"Worker {hotspot_id}: Evidence collection completed")
    
        # LangGraph Map-Reduce를 위한 리스트 포장
        return {
            "preliminary_assessments": [worker_report],
            "analysis_results": [analysis_entry] # 노트북/리포트용 로그
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



# ===== Final Verdict Nodes =====
supervisor_verdict = create_supervisor_verdict_node(
    expert_type="deform",
    get_supervisor_prompt_fn=get_deform_supervisor_prompt,
    SupervisorVerdict=DeformSupervisorVerdict
)

verdict_analyst_node = create_verdict_analyst_node(
    expert_type="deform",
    get_initial_prompt_fn=get_analyst_initial_prompt,
    get_reanalysis_prompt_fn=get_analyst_reanalysis_prompt
)

verdict_critic_node = create_verdict_critic_node(
    expert_type="deform",
    get_critic_prompt_fn=get_critic_prompt
)

verdict_finalize_node = create_verdict_finalize_node(
    expert_type="deform"
)
