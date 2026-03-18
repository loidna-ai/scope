"""
Contact (접촉불량) 전문가 노드
Map-Reduce 아키텍처 with Send API (Component Type별 Specialist)
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
from src.prompts.contact_expert_prompts import (
    get_terminal_prompt,
    get_splice_prompt,
    get_plug_prompt,
    get_contact_supervisor_prompt,
    get_analyst_initial_prompt,
    get_analyst_reanalysis_prompt,
    get_critic_prompt
)

# Local imports - Models
from src.models.contact_models import (
    TerminalEvidenceResult,
    SpliceEvidenceResult,
    PlugEvidenceResult
)
from src.models.debate_models import (
    AnalystHypothesis,
    CritiqueResult,
    HypothesisData,
    create_no_objection
)
from src.models.component_models import ComponentClassification
from src.models.verdict_models import ContactSupervisorVerdict
# from src.nodes.enhancement import ImageEnhancer

# Local imports - Expert Utils
from src.nodes.expert_worker_utils import crop_and_enhance_roi, classify_component

# Local imports - State
from src.states.contact_state import WorkerState, ContactExpertState
from src.nodes.verdict_debate_nodes import (
    create_supervisor_verdict_node,
    create_verdict_analyst_node,
    create_verdict_critic_node,
    create_verdict_finalize_node
)

# ===== Worker Node =====

# Helper functions for ROI crop and classification are now imported from src.nodes.expert_worker_utils


async def analyze_hotspot_worker(state: WorkerState) -> Dict[str, List[Dict]]:
    """
    Unified Worker Node (Map-Reduce Pattern) - Async for True Parallel Execution
    
    통합 작업:
    1. ROI Crop + Enhancement
    2. Component Classification (Async)
    3. Specialist Analysis (Async, Component Type별 분기)
       - Terminal: get_terminal_prompt()
       - Splice: get_splice_prompt()
       - Plug: get_plug_prompt()
       - None: Skip
    
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
        # [#5 Preprocessor] current_hotspot에 _preprocessed=True가 있으면
        # 메인 그래프의 preprocessor_node가 Crop+Classification+Enhancement 완료
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

        # ===== Step 3: Specialist Analysis (Component Type별 분기 - Async) =====

    
        observations = ""
        severity_score = 0
        report_confidence = 0
        evidence_quality = "low"
        is_critical = False
        evidence_result = None  # [Fix] Initialize to prevent UnboundLocalError
        worker_verdict = ""
        
        # Component Type별 분기 처리
        if "Terminal" in connection_type or "단자" in connection_type:
            # Terminal Specialist 분석
            evidence_result = await _analyze_specialist(
                hotspot_id=hotspot_id,
                roi_image_path=roi_image_path,
                image_path=image_path,
                prompt_func=get_terminal_prompt,
                evidence_model=TerminalEvidenceResult,
                component_type="Terminal"
            )
            
        elif "Splice" in connection_type or "전선" in connection_type:
            # Splice Specialist 분석
            evidence_result = await _analyze_specialist(
                hotspot_id=hotspot_id,
                roi_image_path=roi_image_path,
                image_path=image_path,
                prompt_func=get_splice_prompt,
                evidence_model=SpliceEvidenceResult,
                component_type="Splice"
            )
            
        elif "Plug" in connection_type or "플러그" in connection_type:
            # Plug Specialist 분석
            evidence_result = await _analyze_specialist(
                hotspot_id=hotspot_id,
                roi_image_path=roi_image_path,
                image_path=image_path,
                prompt_func=get_plug_prompt,
                evidence_model=PlugEvidenceResult,
                component_type="Plug"
            )
            
        else:
            observations = f"Contact 분석 대상 아님: {connection_type}"
            worker_verdict = observations
            logger.info(f"Worker {hotspot_id}: Skipped (Not Contact Component)")
        
        # Evidence Result 처리 (공통 로직)
        if evidence_result:
            # 데이터 추출
            # SpliceEvidenceResult는 @property로 하위 호환성 제공
            observations = evidence_result.visual_description
            worker_verdict = f"[{evidence_result.verdict}] {evidence_result.reasoning}"
            report_confidence = evidence_result.confidence
            
            # Severity Score 계산
            # Splice의 경우 step6_verdict.conclusion 직접 확인 (더 정확)
            if hasattr(evidence_result, 'step6_verdict'):
                # 6단계 구조 (Splice)
                conclusion = evidence_result.step6_verdict.conclusion
                if conclusion == "접촉불량":
                    severity_score = 80
                    is_critical = True
                    evidence_quality = "high"
                elif conclusion == "접촉불량 의심":
                    severity_score = 60
                    is_critical = False
                    evidence_quality = "medium"
                elif conclusion == "접촉불량 아님":
                    severity_score = 30
                    evidence_quality = "low"
                else:  # 판독 불가
                    severity_score = 30
                    evidence_quality = "low"
            else:
                # Legacy 구조 (Terminal, Plug)
                if evidence_result.verdict == "접촉 불량":
                    severity_score = 80
                    is_critical = True
                    evidence_quality = "high"
                elif evidence_result.verdict == "외부 화재":
                    severity_score = 30
                    evidence_quality = "low"
                else:  # 판단 불가
                    severity_score = 30
                    evidence_quality = "low"
            
            # 개별 분석 결과 파일 저장 (Persistence) - config.SAVE_INDIVIDUAL_HOTSPOT_JSON=True일 때만
            if config.SAVE_INDIVIDUAL_HOTSPOT_JSON:
                try:
                    output_dir = os.path.join(PROJECT_ROOT, "output", "contact_analysis")
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
        
        # ===== Return Assessment (Detailed Worker Report) =====
        # [Refactored] "Reasoned Opinion" 구조에 맞춰 상세 데이터 반환
        
        worker_report = {
            "id": hotspot_id,
            "type": "WorkerReport",
            
            # 1. 근거 (Facts) - 관찰 사실
            "facts": {},
            
            # 2. 의견 (Opinion) - 판단 및 상세 논리
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
            # 6-Step 구조 (Splice / Terminal) → Zone 상세 데이터 전부 facts에 저장 (#11)
            if hasattr(evidence_result, 'step4_geometric_measurement'):
                m = evidence_result.step4_geometric_measurement
                # Zone1 (공통)
                z1 = m.zone1_reference_conductor_area
                # Zone3: Splice vs Terminal 분기
                z3_splice = getattr(m, 'zone3_splice_area', None)
                z3_term   = getattr(m, 'zone3_terminal_area', None)
                # Zone4 (공통)
                z4 = m.zone4_melted_marks_beads

                worker_report["facts"] = {
                    "visual_description": evidence_result.visual_description,
                    # Zone 1: 기준 도체
                    "conductor_shape": z1.conductor_shape,
                    "conductor_discoloration": z1.conductor_discoloration,
                    # Zone 2: 이행 구간
                    "transition_shape": getattr(m.zone2_transition_area, 'transition_shape', 'N/A'),
                    "transition_discoloration": getattr(m.zone2_transition_area, 'transition_discoloration', 'N/A'),
                    # Zone 3: 접속부 / 터미널
                    "contact_shape": (z3_splice.splice_shape if z3_splice else (z3_term.terminal_shape if z3_term else 'N/A')),
                    "contact_discoloration": (z3_splice.splice_discoloration if z3_splice else (z3_term.terminal_discoloration if z3_term else 'N/A')),
                    # Zone 4: 용융 흔적
                    "bead_scan": z4.bead_scan,
                    # Logic Contrast
                    "supporting_logic": evidence_result.step5_logic_contrast.logic_supporting,
                    "refuting_logic": evidence_result.step5_logic_contrast.logic_refuting,
                }
            else:
                # Legacy (Plug): visual_description만
                worker_report["facts"] = {
                    "visual_description": evidence_result.visual_description
                }
            worker_report["opinion"] = {
                "verdict": evidence_result.verdict,
                "confidence": evidence_result.confidence,
                "reasoning": evidence_result.reasoning,
            }
        else:
            # 분석 실패 또는 Contact Component 아님 등의 경우 빈 값 처리
            worker_report["facts"] = {"error": "No evidence collected"}
            worker_report["opinion"] = {"verdict": "Indeterminate", "confidence": 0, "reasoning": "Extraction failed"}
    
        # [Added] Notebook 호환성을 위한 analysis_results 포맷 (Reordered)
        # Splice의 경우 step6_verdict.conclusion 사용, Legacy는 verdict 사용
        if evidence_result and hasattr(evidence_result, 'step6_verdict'):
            sr_conclusion = evidence_result.step6_verdict.conclusion
        else:
            sr_conclusion = evidence_result.verdict if evidence_result else "판독 불가"
        
        # reasoning 추출
        reasoning_text = ""
        if evidence_result:
            reasoning_text = evidence_result.reasoning if hasattr(evidence_result, 'reasoning') else ""
        if not reasoning_text:
            reasoning_text = "분석 근거 없음"
        
        analysis_entry = {
            "hotspot_id": hotspot_id,
            "hotspot_info": hotspot,
            "roi_image_path": roi_image_path,
            "specialist_result": {
                "conclusion": sr_conclusion,      # conclusion만 (시각화 제목용)
                "verdict": worker_verdict,        # 판정 결론 (Conclusion + Reasoning, .md 저장용)
                "confidence": report_confidence,  # confidence_score (0–100)
                "visual_description": observations, # 시각적 특징
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


async def _analyze_specialist(
    hotspot_id: str,
    roi_image_path: str,
    image_path: str,
    prompt_func,
    evidence_model,
    component_type: str
) -> Optional[Any]:
    """
    Specialist 분석 공통 로직 (Terminal/Splice/Plug)
    
    Args:
        hotspot_id: Hotspot ID
        roi_image_path: ROI 이미지 경로
        image_path: 원본 이미지 경로
        prompt_func: 프롬프트 함수 (get_terminal_prompt, get_splice_prompt, get_plug_prompt)
        evidence_model: EvidenceResult Pydantic 모델
        component_type: Component 타입 이름 (로깅용)
    
    Returns:
        EvidenceResult Pydantic 객체 또는 None
    """
    try:
        logger.info(f"Worker {hotspot_id}: Collecting {component_type} evidence...")
        logger.debug(f"Worker {hotspot_id}: Waiting for Evidence API via semaphore...")
        
        # Blocking I/O offloading to thread (공통 이미지 로더 사용)
        original_data, roi_data = await load_expert_images(roi_image_path, image_path)
        
        prompt = prompt_func(roi_image_path)
        
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
        return evidence_result
        
    except Exception as e:
        # Fallback: 오류 메시지 기록
        logger.error(f"Worker {hotspot_id}: {component_type} evidence collection final failure: {e}", exc_info=True)
        return None


# ===== Final Verdict Nodes =====
supervisor_verdict = create_supervisor_verdict_node(
    expert_type="contact",
    get_supervisor_prompt_fn=get_contact_supervisor_prompt,
    SupervisorVerdict=ContactSupervisorVerdict
)

verdict_analyst_node = create_verdict_analyst_node(
    expert_type="contact",
    get_initial_prompt_fn=get_analyst_initial_prompt,
    get_reanalysis_prompt_fn=get_analyst_reanalysis_prompt
)

verdict_critic_node = create_verdict_critic_node(
    expert_type="contact",
    get_critic_prompt_fn=get_critic_prompt
)

verdict_finalize_node = create_verdict_finalize_node(
    expert_type="contact"
)
