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
# 미리보기 모델(gemini-3-flash-preview)의 동시 요청 제한(Concurrency Limit)에 대응


# Define Project Root for centralized output
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Local imports - Utils and Tools
from src.utils import crop_roi_from_box, async_retry_with_backoff, validate_state_keys, get_genai_client
from src.utils.logging_config import setup_logger
from src.tools.experts.expert_utils import _load_image_data

# Initialize logger
logger = setup_logger(__name__)

# Local imports - Prompts
from src.prompts.common_prompts import get_component_classifier_prompt
from src.prompts.deform_expert_prompts import (
    get_deform_wire_prompt,
    get_analyst_initial_prompt,
    get_analyst_reanalysis_prompt,
    get_critic_prompt,
    get_deform_supervisor_prompt
)

# Local imports - Models
from src.models.deform_models import DeformEvidenceResult, SupervisorVerdict
from src.models.debate_models import (
    AnalystHypothesis,
    CritiqueResult,
    HypothesisData,
    create_no_objection
)
from src.models.component_models import ComponentClassification
from src.nodes.enhancement import ImageEnhancer

# Local imports - State
from src.states.deform_state import WorkerState, DeformExpertState


# ===== Worker Node =====

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
        # ===== Step 1: ROI Crop + Enhancement =====
        detector_result = {
            "box_2d": hotspot.get("box_2d"),
            "confidence": hotspot.get("severity_score")
        }
        
        box_2d = detector_result.get("box_2d")
        roi_image_path = image_path  # Default fallback
        
        if box_2d:
            logger.debug(f"Worker {hotspot_id}: ROI crop coordinates: {box_2d}")
            try:
                # 임시 파일로 크롭 (output/crops 미사용)
                cropped_path = await asyncio.to_thread(crop_roi_from_box, image_path, box_2d)
                
                # Enhancement (Async to prevent blocking)
                logger.info(f"Worker {hotspot_id}: Applying 2x image enhancement...")
                # 대형 ROI 안내 (Enhancement 1~2분 소요 가능)
                try:
                    xmin, xmax = box_2d.get("xmin", 0), box_2d.get("xmax", 0)
                    ymin, ymax = box_2d.get("ymin", 0), box_2d.get("ymax", 0)
                    area = (xmax - xmin) * (ymax - ymin) if all([xmin, xmax, ymin, ymax]) else 0
                    if area > 80_000:
                        logger.warning(f"Worker {hotspot_id}: Large ROI ({xmax-xmin}x{ymax-ymin}px) detected - Enhancement may take 1-2 mins")
                except Exception:
                    pass
                try:
                    # 1. 크롭된 이미지 로드 (Async I/O)
                    cropped_img = await asyncio.to_thread(cv2.imread, cropped_path)
                    if cropped_img is None:
                        raise ValueError("크롭된 이미지를 읽을 수 없습니다.")
                    
                    # 2. Enhancement (Blocking 작업을 thread로 offload)
                    def enhance_image(img, path):
                        # #region agent log
                        import json
                        import time
                        from pathlib import Path
                        log_path = Path(PROJECT_ROOT) / ".cursor" / "debug.log"
                        log_path.parent.mkdir(parents=True, exist_ok=True)
                        enhance_start = time.time()
                        img_h, img_w = img.shape[:2]
                        try:
                            with open(log_path, "a", encoding="utf-8") as f:
                                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"deform_nodes.py:123","message":"enhance_image entry","data":{"hotspot_id":hotspot_id,"image_size_h":img_h,"image_size_w":img_w,"pixels":img_h*img_w},"timestamp":int(time.time()*1000)})+"\n")
                        except: pass
                        # #endregion
                        
                        enhancer = ImageEnhancer()
                        enhanced_img = enhancer.upscale(img)
                        cv2.imwrite(path, enhanced_img)
                        
                        # #region agent log
                        enhance_duration = time.time() - enhance_start
                        try:
                            with open(log_path, "a", encoding="utf-8") as f:
                                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"deform_nodes.py:129","message":"enhance_image exit","data":{"hotspot_id":hotspot_id,"duration_seconds":enhance_duration},"timestamp":int(time.time()*1000)})+"\n")
                        except: pass
                        # #endregion
                        
                        return path
                    
                    enhanced_path = await asyncio.to_thread(enhance_image, cropped_img, cropped_path)
                    logger.info(f"Worker {hotspot_id}: Enhancement completed: {enhanced_path}")
                    
                except Exception as enh_err:
                    logger.warning(f"Worker {hotspot_id}: Enhancement Failed: {enh_err}")
                    # 향상 실패해도 원본 크롭 이미지는 유지됨
                
                roi_image_path = cropped_path
            except Exception as e:
                logger.error(f"Worker {hotspot_id}: Crop Failed: {e}")
        
        # ===== Step 2: Component Classification (Async) =====
        connection_type = "None"
        
        # API 호출 함수 분리
        async def _call_classifier_api(client, model_name, parts, safety_settings):
            """Component Classification API 호출"""
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model_name,
                contents=parts,
                config={
                    "response_mime_type": "application/json",
                    "response_json_schema": ComponentClassification.model_json_schema(),
                    "safety_settings": safety_settings,
                }
            )
            
            # [Debug/Safety] 응답 텍스트 확인 및 안전 파싱
            response_text = getattr(response, 'text', None)
            if not response_text:
                finish_reason = "Unknown"
                if hasattr(response, 'candidates') and response.candidates:
                    finish_reason = getattr(response.candidates[0], 'finish_reason', "Unknown")
                raise ValueError(f"Classifier 응답이 비어있습니다. (Finish Reason: {finish_reason})")
            
            return response
        
        try:
            logger.info(f"Worker {hotspot_id}: Identifying component type...")
            
            # Blocking I/O offloading to thread
            roi_image_data = await asyncio.to_thread(_load_image_data, roi_image_path)
            original_image_data = await asyncio.to_thread(_load_image_data, image_path)
            
            prompt = get_component_classifier_prompt(roi_image_path)
            
            # 🔥 Pydantic Structured Output (Gemini Official Best Practice)
            client = get_genai_client()
            model_name = os.environ.get("GEMINI_MODEL_NAME", config.GEMINI_MODEL_NAME)
            
            # 이미지 파트 구성
            parts = [prompt]
            for img_data in [original_image_data, roi_image_data]:
                parts.append(types.Part.from_bytes(
                    data=img_data,
                    mime_type="image/jpeg"
                ))
            
            # [Gemini Official Best Practice] Safety settings BLOCK_NONE
            safety_settings_block_none = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
            
            # 🔥 Centralized Retry Logic
            response = await async_retry_with_backoff(
                _call_classifier_api,
                client=client,
                model_name=model_name,
                parts=parts,
                safety_settings=safety_settings_block_none,
                max_retries=5,
                context_name=f"Worker #{hotspot_id} Classifier"
            )
            
            # Pydantic 안전 파싱 (공식 권장 방식)
            classification = ComponentClassification.model_validate_json(response.text)
            connection_type = classification.deduced_type
            logger.info(f"Worker {hotspot_id}: Component classified as {connection_type} (Confidence: {classification.confidence}%)")
            
        except Exception as e:
            # Fallback: Unknown으로 설정 (Wire가 아님)
            logger.error(f"Worker {hotspot_id}: Classifier final failure: {e}", exc_info=True)
            logger.warning(f"Worker {hotspot_id}: Classification failed, setting type to Unknown")
            connection_type = "Unknown"
    
        
        # ===== Step 3: Evidence Collection (Wire Only - Async) =====
    
        observations = ""
        severity_score = 0
        report_confidence = 0
        evidence_quality = "low"
        is_critical = False
        evidence_result = None # [Fix] Initialize to prevent UnboundLocalError
        worker_verdict = ""
        
        if "Wire" in connection_type:
            # API 호출 함수 분리
            async def _call_evidence_api(client, model_name, parts, config):
                """Evidence Collection API 호출"""
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model_name,
                    contents=parts,
                    config=config
                )
                
                # [Debug/Safety] 응답 텍스트 확인 및 안전 파싱
                response_text = getattr(response, 'text', None)
                if not response_text:
                    finish_reason = "Unknown"
                    if hasattr(response, 'candidates') and response.candidates:
                        finish_reason = getattr(response.candidates[0], 'finish_reason', "Unknown")
                    raise ValueError(f"Evidence Collection 응답이 비어있습니다. (Finish Reason: {finish_reason})")
                return response
            
            try:
                logger.info(f"Worker {hotspot_id}: Collecting Wire evidence...")
                logger.debug(f"Worker {hotspot_id}: Waiting for Evidence API via semaphore...")
                
                # Blocking I/O offloading to thread
                roi_data = await asyncio.to_thread(_load_image_data, roi_image_path)
                original_data = await asyncio.to_thread(_load_image_data, image_path)
                
                prompt = get_deform_wire_prompt(roi_image_path)
                
                # [Gemini Official Best Practice] Pydantic Structured Output
                # [Gemini Official Best Practice] Safety settings BLOCK_NONE
                safety_settings_block_none = [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                ]
                
                client = get_genai_client()
                model_name = os.environ.get("GEMINI_MODEL_NAME", config.GEMINI_MODEL_NAME)
                
                # 이미지 파트 구성
                parts = [prompt]
                for img_data in [original_data, roi_data]:
                    parts.append(types.Part.from_bytes(
                        data=img_data,
                        mime_type="image/jpeg"
                    ))
                
                # API 설정 - thinking_config는 일부 모델에서 지원하지 않으므로 조건부 추가
                # gemini-3-flash-preview는 thinking level 미지원
                api_config = {
                    "temperature": 1.0,
                    "response_mime_type": "application/json",
                    "response_json_schema": DeformEvidenceResult.model_json_schema(),
                    "safety_settings": safety_settings_block_none
                }
                
                # thinking level 지원 모델에만 추가
                thinking_supported_models = ["gemini-2.0-flash-exp", "gemini-2.5-flash", "gemini-2.5-pro"]
                if any(m in model_name for m in thinking_supported_models):
                    api_config["thinking_config"] = types.ThinkingConfig(thinking_level="high")
                
                # 🔥 Centralized Retry Logic (기본 retriable_errors 사용)
                response = await async_retry_with_backoff(
                    _call_evidence_api,
                    client=client,
                    model_name=model_name,
                    parts=parts,
                    config=api_config,
                    max_retries=5,
                    context_name=f"Worker #{hotspot_id} Evidence"
                )
                
                # Pydantic 안전 파싱
                evidence_result = DeformEvidenceResult.model_validate_json(response.text)
                
                # Extract Evidence (Pydantic 객체에서 추출)
                step4 = evidence_result.step4_geometric_measurement
                step5 = evidence_result.step5_logic_contrast
                
                # Observations Summary (Zone 2, 3, 4 정보 조합)
                geometric_features = []
                if step4.zone2_transition_gradient.width_change_observation:
                    geometric_features.append(f"Width Change: {step4.zone2_transition_gradient.width_change_observation}")
                if step4.zone3_terminal_apex.terminal_shape_observation:
                    geometric_features.append(f"Terminal Shape: {step4.zone3_terminal_apex.terminal_shape_observation}")
                if step4.zone4_melted_marks_beads.bead_scan:
                    geometric_features.append(f"Bead: {step4.zone4_melted_marks_beads.bead_scan}")
    
                observations = " | ".join(geometric_features) if geometric_features else "기하학적 계측 완료"
                
                # Severity Score (Rule-based from evidence)
                logic_supporting = step5.logic_supporting
                
                # [AI-Centric Logic] 
                # LLM의 최종 결론(Conclusion)에 따라 위험 등급을 결정하며, 신뢰도 조건은 배제합니다.
                conclusion = evidence_result.step6_verdict.conclusion
                ai_confidence = evidence_result.step6_verdict.confidence_score
                
                # 1. High-risk: 확정적 "압착, 손상" 판정
                if conclusion == "압착, 손상":
                    severity_score = 80
                    is_critical = True
                    evidence_quality = "high"
                
                # 2. Medium-risk: "압착, 손상 의심" 판정
                elif conclusion == "압착, 손상 의심":
                    severity_score = 50
                    evidence_quality = "medium"
                    
                # 3. Low-risk: 그 외 (압착, 손상 아님, 판독 불가 등)
                else:
                    severity_score = 30
                    evidence_quality = "low"
                    
                # 최종 리포트용 신뢰도는 AI가 산출한 값을 우선 사용
                report_confidence = ai_confidence if ai_confidence > 0 else severity_score
    
                
                # [Added] 상세 판정 결과 추출
                worker_verdict = f"[{evidence_result.step6_verdict.conclusion}] {evidence_result.step6_verdict.final_reasoning}"
                
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
                
        else:
            observations = f"Wire가 아님: {connection_type}"
            worker_verdict = observations
            logger.info(f"Worker {hotspot_id}: Skipped (Not Wire)")
        
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
                "global_arrangement": evidence_result.step1_context_analysis.get("global_arrangement"),
                "fire_pattern": evidence_result.step1_context_analysis.get("fire_pattern"),
                "identified_location": evidence_result.step2_location_mapping.get("identified_location"),
                "crop_description": evidence_result.step3_crop_identification.get("crop_description"),
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
                "verdict": evidence_result.step6_verdict.conclusion,
                "confidence": evidence_result.step6_verdict.confidence_score,
                "reasoning": evidence_result.step6_verdict.final_reasoning,
                "supporting_logic": evidence_result.step5_logic_contrast.logic_supporting,
                "refuting_logic": evidence_result.step5_logic_contrast.logic_refuting
            }
        else:
            # 분석 실패 또는 Wire 아님 등의 경우 빈 값 처리
            worker_report["facts"] = {"error": "No evidence collected"}
            worker_report["opinion"] = {"verdict": "Indeterminate", "confidence": 0, "reasoning": "Extraction failed"}
    
        # [Added] Notebook 호환성을 위한 analysis_results 포맷 (Reordered)
        sr_conclusion = evidence_result.step6_verdict.conclusion if evidence_result else "판독 불가"
        
        # reasoning 추출
        reasoning_text = ""
        if evidence_result and hasattr(evidence_result, 'step6_verdict'):
            reasoning_text = evidence_result.step6_verdict.final_reasoning if hasattr(evidence_result.step6_verdict, 'final_reasoning') else ""
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



# ===== Supervisor Node =====

async def supervisor_verdict(state: DeformExpertState) -> Dict[str, Any]:

    """
    Hybrid Fast/Slow Path Supervisor (Map-Reduce Reduce Stage)
    
    Fast Path (90% of cases):
    - Rule-based weighted scoring
    - Clear cases: ≥2 high-risk OR all low-risk
    - Decision time: < 1 second
    
    Slow Path (10% of cases):
    - Analyst-Critic debate
    - Ambiguous cases: 1 high-risk OR mixed signals
    - Decision time: ~ 10-20 seconds
    """
    try:
        assessments = state.get("preliminary_assessments", [])
        
        logger.info(f"Supervisor: Reviewing evidence from {len(assessments)} Workers...")
        
        # Early Return: No assessments
        if not assessments:
            return {
                "final_verdict": {
                    "conclusion": "분석 불가",
                    "confidence": 0.0,
                    "reasoning": "분석된 증거 없음"
                }
            }
        
        # ===== AI Supervisor Logic (Reasoning-based Map-Reduce) =====
        # [Refactored] Rule-based 로직을 제거하고 LLM이 직접 Worker들의 보고서를 종합 판단
        
        # 1. Prepare Aggregation Context
        reports_text = format_report_summary(assessments)
        logger.debug(f"Supervisor: Aggregation Context:\n{reports_text[:500]}...") # 로그 줄임
        
        # 2. Call LLM (Map-Reduce Reduction)
        prompt = get_deform_supervisor_prompt(reports_text=reports_text)
        
        # API 호출 함수 분리
        async def _call_supervisor_api(client, model_name, prompt, config):
            """Supervisor API 호출"""
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model_name,
                contents=prompt,
                config=config
            )
            
            # Response handling
            response_text = getattr(response, 'text', None)
            if not response_text:
                finish_reason = "Unknown"
                if hasattr(response, 'candidates') and response.candidates:
                    finish_reason = getattr(response.candidates[0], 'finish_reason', "Unknown")
                raise ValueError(f"Supervisor response is empty. (Finish Reason: {finish_reason})")
            
            return response
        
        # [Gemini Native] Use genai.Client instead of LangChain
        # Consistent with worker nodes and avoid undefined globals/imports
        
        client = get_genai_client()
        model_name = os.environ.get("GEMINI_MODEL_NAME", config.GEMINI_MODEL_NAME)
        
        # Safety settings (String based for compatibility)
        safety_settings_block_none = [
             {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
             {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
             {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
             {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        print("🤔 [Supervisor] 종합 판정 중...")
        
        api_config = {
            "temperature": 0.0,
            "response_mime_type": "application/json",
            "response_json_schema": SupervisorVerdict.model_json_schema(),
            "safety_settings": safety_settings_block_none,
        }
        
        # 🔥 Centralized Retry Logic
        response = await async_retry_with_backoff(
            _call_supervisor_api,
            client=client,
            model_name=model_name,
            prompt=prompt,
            config=api_config,
            max_retries=5,
            context_name="Supervisor"
        )
        
        # Pydantic validation
        supervisor_result = SupervisorVerdict.model_validate_json(response.text)
        
        # 3. Finalize
        logger.info(f"Supervisor: Final Verdict: {supervisor_result.final_conclusion} (Conf: {supervisor_result.final_confidence})")
        logger.debug(f"Supervisor Reasoning: {supervisor_result.reasoning_process}")
        
        return {
            "final_verdict": {
                "conclusion": supervisor_result.final_conclusion,
                "confidence": supervisor_result.final_confidence / 100.0, # Normalize to 0.0-1.0 if needed, or keep integer
                "reasoning": f"[{supervisor_result.key_evidence_summary}] {supervisor_result.reasoning_process}"
            }
        }

        
    except Exception as e:
        logger.error(f"Deform Supervisor Error: {str(e)}", exc_info=True)
        return {
            "final_verdict": {
                "conclusion": "판독 불가",
                "confidence": 0,
                "reasoning": "시스템 오류로 인해 분석을 완료할 수 없습니다. (판독 보류)"
            }
        }


# ===== Helper Functions =====
def format_report_summary(assessments: list) -> str:
    """
    구조화된 요약 보고서 생성 (Map-Reduce용)
    Workers의 preliminary_assessments를 바탕으로 Debate용 요약 생성
    """
    if not assessments:
        return "분석된 증거 없음"
    
    summary = "=== Worker Reports Summary ===\n"
    for assessment in assessments:
        hotspot_id = assessment.get('id', 'unknown')
        
        # New WorkerReport Structure Handling
        if "facts" in assessment and "opinion" in assessment:
            facts = assessment['facts']
            opinion = assessment['opinion']
            
            # Extract basic info safely
            verdict = opinion.get('verdict', 'N/A')
            confidence = opinion.get('confidence', 0)
            conn_type = assessment.get('_connection_type', 'Unknown')
            
            summary += f"\n[Worker Report #{hotspot_id}] (Type: {conn_type})\n"
            
            # [Logic] Wire가 아닌 경우 Skip 메시지를 명확히 전달
            if "Wire" not in conn_type and conn_type != "Unknown":
                summary += f"⚠️ NOTE: Analysis Skipped (Target is not a Wire)\n"
                summary += "-"*40 + "\n"
                continue
            
            # [Added] 에러 상태인 경우 요약에 표시
            if "error" in facts:
                 summary += f"⚠️ NOTE: Analysis Failed (Error: {facts['error']})\n"
                 summary += "-"*40 + "\n"
                 continue

            summary += f"1. FACTS (Evidence):\n"
            summary += f"  - Global Arrangement: {facts.get('global_arrangement', 'N/A')}\n"
            summary += f"  - Fire Pattern: {facts.get('fire_pattern', 'N/A')}\n"
            summary += f"  - Location: {facts.get('identified_location', 'N/A')}\n"
            summary += f"  - Crop: {facts.get('crop_description', 'N/A')}\n"
            summary += f"  - Reference Shaft Shape: {facts.get('reference_shaft_shape_observation', 'N/A')}\n"
            summary += f"  - Surface: {facts.get('surface_visual_check', 'N/A')}\n"
            summary += f"  - Width Change: {facts.get('width_change_observation', 'N/A')}\n"
            summary += f"  - Boundary: {facts.get('boundary_visual_check', 'N/A')}\n"
            summary += f"  - Terminal Shape: {facts.get('terminal_shape_observation', 'N/A')}\n"
            summary += f"  - Terminal Width: {facts.get('terminal_width_comparison', 'N/A')}\n"
            summary += f"  - Strand State: {facts.get('strand_state_observation', 'N/A')}\n"
            summary += f"  - Bead Scan (Zone4): {facts.get('bead_scan', 'N/A')}\n"

            summary += f"2. OPINION (Verdict):\n"
            summary += f"  - Verdict: {verdict}\n"
            summary += f"  - Confidence: {confidence}\n"
            summary += f"  - Reasoning: {opinion.get('reasoning', 'N/A')}\n"
            summary += f"  - Supporting Logic: {opinion.get('supporting_logic', 'N/A')}\n"
            summary += f"  - Refuting Logic: {opinion.get('refuting_logic', 'N/A')}\n"
            summary += "-"*40 + "\n"
            
        else:
            # Fallback for old structure or error
            observations = assessment.get('observations', 'N/A')
            severity_score = assessment.get('severity_score', 0)
            evidence_quality = assessment.get('evidence_quality', 'unknown')
            is_critical = assessment.get('is_critical', False)
            connection_type = assessment.get('_connection_type', 'Unknown')
            
            risk_level = "🔴 HIGH" if is_critical else ("🟡 MEDIUM" if evidence_quality == "medium" else "🟢 LOW")
            
            summary += f"- [{hotspot_id}] Type: {connection_type} | Risk: {risk_level} | Score: {severity_score}\n"
            summary += f"  Obs: {observations}\n"
    return summary


def extract_critiqued_hotspots(critique: str, all_results: list) -> list:
    """
    Critic의 지적에서 언급된 특정 Hotspot ID 추출
    
    Args:
        critique: Critic의 비평 텍스트
        all_results: 전체 분석 결과 리스트
    
    Returns:
        Critic이 언급한 Hotspot들의 분석 결과 리스트
    """
    if not critique or not all_results:
        return []
    
    # "Spot #3", "Hotspot #7", "#2" 등 패턴 추출
    mentioned_ids = set()
    patterns = [
        r'[Ss]pot\s*#?(\d+)',
        r'[Hh]otspot\s*#?(\d+)',
        r'#(\d+)',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, critique)
        mentioned_ids.update(int(m) for m in matches)
    
    if not mentioned_ids:
        # Critic이 특정 Hotspot을 언급하지 않으면 전체 반환
        return all_results
    
    # 언급된 ID만 필터링
    filtered = [
        res for res in all_results 
        if res.get('hotspot_info', {}).get('id') in mentioned_ids
    ]
    
    logger.info(f"Focus: Critic highlighted hotspots: {sorted(mentioned_ids)}")
    
    return filtered if filtered else all_results

# ===== Analyst-Critic Debate Nodes =====

async def verdict_analyst_node(state: DeformExpertState) -> Dict[str, Any]:

    """
    Final Verdict Analyst (분석관) - Map-Reduce용
    - 최초: preliminary_assessments 기반 초기 가설 수립
    - 재분석: Critic의 지적 수용 후 가설 수정/방어
    """
    # Map-Reduce: preliminary_assessments 사용
    results = state.get("preliminary_assessments", [])
    debate_messages = state.get("debate_messages", [])
    critique = state.get("critique_points", "")
    debate_iter = state.get("debate_iteration", 0)
    
    # Early Return: 결과 없음
    if not results:
        return {
            "current_hypothesis": "분석된 특이점이 없습니다.",
            "debate_messages": ["[Analyst] No hotspots detected."],
            "debate_iteration": debate_iter + 1
        }
    
    # Report Summary 생성 (Map-Reduce용 format_report_summary 사용)
    report_summary = format_report_summary(results)
    
    if not debate_messages:
        # [상황 1] 최초 종합 분석
        logger.info(f"Analyst: Establishing initial hypothesis...")
        
        # 프롬프트 함수 호출 (중앙화)
        system_prompt = get_analyst_initial_prompt(report_summary)
        
    else:
        # [상황 2] 비평 수용 후 재분석 - 특정 부위 집중 모드
        logger.info(f"Analyst: Re-analyzing based on critique (Round {debate_iter + 1})...")
        
        prev_hypothesis = state.get("current_hypothesis", "")
        
        #  Phase 2: CritiqueResult.hotspots_mentioned 직접 사용
        critique_result = state.get("critique_result")
        
        if critique_result is not None and critique_result.hotspots_mentioned:
            # Pydantic 객체에서 명시적 Hotspot ID 추출 (정규표현식 불필요!)
            mentioned_ids = critique_result.hotspots_mentioned
            # Map-Reduce: 'id' 필드 사용
            focused_hotspots = [r for r in results if r.get("id") in mentioned_ids]
            logger.info(f"Analyst: Critic specified hotspots: {mentioned_ids}")
        else:
            # Fallback: Legacy 정규표현식 추출
            focused_hotspots = extract_critiqued_hotspots(critique, results)
            logger.warning(f"Analyst: Fallback to regex for hotspot extraction")
        
        focused_summary = format_report_summary(focused_hotspots)

        
        # 전체 컨텍스트 요약 (참고용)
        total_hotspot_count = len(results)
        focused_count = len(focused_hotspots)
        
        # 프롬프트 함수 호출 (중앙화)
        system_prompt = get_analyst_reanalysis_prompt(
            prev_hypothesis=prev_hypothesis,
            critique=critique,
            focused_summary=focused_summary,
            total_hotspot_count=total_hotspot_count,
            focused_count=focused_count,
            full_context=report_summary
        )
    
    
    # 🔥 API 호출 함수 분리
    async def _call_analyst_api(client, model_name, system_prompt, safety_settings):
        """Analyst API 호출"""
        # thinking level 지원 모델에만 추가
        thinking_supported_models = ["gemini-2.0-flash-exp", "gemini-2.5-flash", "gemini-2.5-pro"]
        config_dict = {
            "temperature": 1.0,
            "response_mime_type": "application/json",
            "response_json_schema": AnalystHypothesis.model_json_schema(),
            "safety_settings": safety_settings
        }
        if any(m in model_name for m in thinking_supported_models):
            config_dict["thinking_config"] = types.ThinkingConfig(thinking_level="high")
        
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=model_name,
            contents=system_prompt,
            config=types.GenerateContentConfig(**config_dict)
        )
        return response
    
    try:
        # [Gemini Official Best Practice] Safety settings BLOCK_NONE
        safety_settings_block_none = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        
        # Gemini Native Structured Output 사용
        client = get_genai_client()
        model_name = os.environ.get("GEMINI_MODEL_NAME", config.GEMINI_MODEL_NAME)
        
        # 🔥 Centralized Retry Logic
        response = await async_retry_with_backoff(
            _call_analyst_api,
            client=client,
            model_name=model_name,
            system_prompt=system_prompt,
            safety_settings=safety_settings_block_none,
            max_retries=5,
            context_name="Analyst"
        )

        # [Debug/Safety] 응답 텍스트 확인 및 안전 파싱
        response_text = getattr(response, 'text', None)
        finish_reason = "Unknown"
        if hasattr(response, 'candidates') and response.candidates:
            finish_reason = getattr(response.candidates[0], 'finish_reason', "Unknown")
            
        logger.debug(f"Analyst: Finish reason: {finish_reason}")
        
        if not response_text:
            raise ValueError(f"Gemini API 응답 텍스트가 비어있습니다. (Finish Reason: {finish_reason})")

        # Pydantic 안전 파싱 (공식 권장 방식: model_validate_json)
        analyst_result = AnalystHypothesis.model_validate_json(response_text)

        
        # 가설 추출 (Pydantic 메서드 사용)
        hypothesis = analyst_result.get_hypothesis()
        
        logger.info(f"Analyst: Hypothesis: {hypothesis}")
        
        return {
            # [Phase 2] Pydantic 객체 저장
            "analyst_hypothesis": analyst_result,
            
            # [Legacy] 하위 호환성
            "current_hypothesis": hypothesis,
            
            "debate_messages": [f"[Analyst Round {debate_iter + 1}] {response.text}"],
            "debate_iteration": debate_iter + 1
        }
        
    except Exception as e:
        logger.error(f"Analyst Parsing Error: {e}", exc_info=True)
        return {
            "current_hypothesis": "분석 오류 발생",
            "debate_messages": [f"[Analyst Error] {str(e)}"],
            "debate_iteration": debate_iter + 1
        }


async def verdict_critic_node(state: DeformExpertState) -> Dict[str, Any]:

    """
    Final Verdict Critic (비평가)
    - Analyst 가설의 맹점 공격
    - 합의 시 "NO_OBJECTION" 반환
    """
    hypothesis = state.get("current_hypothesis", "")
    results = state.get("analysis_results", [])
    debate_iter = state.get("debate_iteration", 0)
    
    # Early Return: 가설 없음
    if not hypothesis or "오류" in hypothesis or "없습니다" in hypothesis:
        logger.info(f"Critic: Skipping - No hypothesis to critique")
        return {
            "critique_points": "NO_OBJECTION",
            "debate_messages": ["[Critic] No hypothesis to critique."]
        }
    
    logger.info(f"Critic: Verifying hypothesis (Round {debate_iter})...")
    
    # 🔥 Phase 1 Critical Fix: Image Access for Critic
    # Critic이 원본 이미지와 ROI 이미지를 직접 보고 검증
    
    # 1. 원본 이미지 로드
    image_path = state.get("image_path")
    image_data_list = []
    
    try:
        if image_path:
            original_image = _load_image_data(image_path)
            image_data_list.append(original_image)
            logger.debug(f"Critic: Loaded original image: {image_path}")
    except Exception as img_err:
        logger.warning(f"Critic: Failed to load original image: {img_err}")
    
    # 2. 모든 ROI 이미지 로드 (Analyst가 분석한 영역들)
    roi_loaded_count = 0
    for res in results:
        roi_path = res.get("roi_image_path")
        if roi_path:
            try:
                roi_image = _load_image_data(roi_path)
                image_data_list.append(roi_image)
                roi_loaded_count += 1
            except Exception as roi_err:
                logger.warning(f"Critic: Failed to load ROI image: {roi_err}")
    
    if roi_loaded_count > 0:
        logger.debug(f"Critic: Loaded {roi_loaded_count} ROI images")
    
    # 3. 텍스트 보고서 요약
    report_summary = format_report_summary(results)
    
    # 4. 프롬프트 구성 (이미지 컨텍스트 추가)
    image_context = ""
    if image_data_list:
        image_context = f"""
<image_access>
⚠️ **중요**: 당신은 분석가의 주장을 **실제 이미지로 직접 검증**할 수 있습니다.
- Image 1: 원본 전체 이미지 (Context)
- Image 2~{len(image_data_list)}: 각 Hotspot의 ROI 이미지 (Detail)

분석가가 "세장화를 보았다", "미세 망울이 있다"고 주장하면:
1. 해당 Hotspot의 ROI 이미지에서 **직접 확인**하십시오.
2. Pixel 레벨로 검증: 진짜 뾰족한가? 뭉툭한가? 망울이 미세한가? 거대한가?
3. 분석가의 주장과 실제 이미지가 일치하지 않으면 **즉시 지적**하십시오.
</image_access>
"""
    
    # 프롬프트 함수 호출 (중앙화)
    system_prompt = get_critic_prompt(
        hypothesis=hypothesis,
        report_summary=report_summary,
        image_context=image_context
    )
    
    
    # 🔥 API 호출 함수 분리 (Vision 및 Text 버전)
    async def _call_critic_vision_api(client, model_name, parts):
        """Critic Vision API 호출"""
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=model_name,
            contents=parts,
            config=types.GenerateContentConfig(
                temperature=1.0,
                response_mime_type="application/json",
                response_schema=CritiqueResult,
                thinking_config=types.ThinkingConfig(
                    thinking_level="medium"
                )
            )
        )
        return response
    
    async def _call_critic_text_api(client, model_name, prompt, safety_settings):
        """Critic Text API 호출"""
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=1.0,
                response_mime_type="application/json",
                response_json_schema=CritiqueResult.model_json_schema(),
                safety_settings=safety_settings,
                thinking_config=types.ThinkingConfig(
                    thinking_level="high"
                )
            )
        )
        return response
    
    try:
        # 🔥 핵심 변경: Gemini Native Structured Output
        client = get_genai_client()
        model_name = os.environ.get("GEMINI_MODEL_NAME", config.GEMINI_MODEL_NAME)

        
        if image_data_list:
            # 이미지가 있으면 Vision API 사용 (Multimodal + Structured)
            logger.info(f"Critic: Calling Vision API with {len(image_data_list)} images...")
            
            parts = [system_prompt]
            for idx, img_data in enumerate(image_data_list, 1):
                parts.append(types.Part.from_bytes(
                    data=img_data,
                    mime_type="image/jpeg"
                ))
                
            # 🔥 Centralized Retry Logic
            response = await async_retry_with_backoff(
                _call_critic_vision_api,
                client=client,
                model_name=model_name,
                parts=parts,
                max_retries=5,
                context_name="Critic Vision"
            )

        else:
            # 이미지 로드 실패 시 텍스트만 사용 (Fall back)
            logger.warning(f"Critic: Text-only verification (Image load failed)")
            logger.info(f"Critic: Calling Text API (Model: {model_name})...")
            
            # [Gemini Official Best Practice] Safety settings BLOCK_NONE
            safety_settings_block_none = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
            
            # 🔥 Centralized Retry Logic
            response = await async_retry_with_backoff(
                _call_critic_text_api,
                client=client,
                model_name=model_name,
                prompt=system_prompt,
                safety_settings=safety_settings_block_none,
                max_retries=5,
                context_name="Critic Text"
            )

            logger.info(f"Critic: API response received")
        
    except Exception as e:
        # 재시도 실패 시 NO_OBJECTION 반환
        logger.error(f"Critic: Final failure: {e}", exc_info=True)
        
        no_objection = create_no_objection()
        return {
            "critique_result": no_objection,
            "critique_points": "NO_OBJECTION",
            "debate_messages": [f"[Critic Error] {str(e)}"]
        }
    
    # 파싱 및 결과 처리
    try:
        # [Debug/Safety] 응답 텍스트 확인 및 안전 파싱
        response_text = getattr(response, 'text', None)
        finish_reason = "Unknown"
        if hasattr(response, 'candidates') and response.candidates:
            finish_reason = getattr(response.candidates[0], 'finish_reason', "Unknown")
            
        logger.debug(f"Critic: Finish reason: {finish_reason}")
        
        if not response_text:
            raise ValueError(f"Gemini API 응답 텍스트가 비어있습니다. (Finish Reason: {finish_reason})")

        # Pydantic 안전 파싱 (공식 권장 방식: model_validate_json)
        critique_result = CritiqueResult.model_validate_json(response_text)

        
        # is_approved bool 체크 (문자열 검색 불필요!)
        if critique_result.is_approved:
            logger.info("Critic: Consensus reached: NO_OBJECTION")
        else:
            logger.info(f"Critic: Objection raised: {critique_result.objection_type}")
            if critique_result.hotspots_mentioned:
                logger.info(f"Critic: Highlighted hotspots: {critique_result.hotspots_mentioned}")
        
        return {
            # [Phase 2] Pydantic 객체 저장
            "critique_result": critique_result,
            
            # [Legacy] 하위 호환성 (문자열)
            "critique_points": response.text,
            
            "debate_messages": [f"[Critic Round {debate_iter}] {response.text}"]
        }
        
    except Exception as e:
        logger.error(f"Critic Parsing Error: {e}", exc_info=True)
        
        # 에러 시 NO_OBJECTION 반환
        no_objection = create_no_objection()
        return {
            "critique_result": no_objection,
            "critique_points": "NO_OBJECTION",
            "debate_messages": [f"[Critic Error] {str(e)}"]
        }


async def verdict_finalize_node(state: DeformExpertState) -> Dict[str, Any]:

    """
    Final Verdict Finalize (최종 정리)
    - Supervisor 또는 Analyst의 결론을 바탕으로 최종 보고서 생성
    - Timeout 시 Analyst의 마지막 결론 채택
    """
    hypothesis = state.get("current_hypothesis", "")
    debate_messages = state.get("debate_messages", [])
    debate_iter = state.get("debate_iteration", 0)
    critique = state.get("critique_points", "")
    results = state.get("analysis_results", [])
    
    MAX_ITERATIONS = 3
    
    logger.info(f"Finalize: Consolidating verdict (Debate Rounds: {debate_iter})...")
    logger.debug(f"Finalize: Accumulated results count: {len(results)}")

    
    # =========================================================
    # [Integrated Finalize Logic] 통합 결론 도출 로직
    # =========================================================
    
    # 1. 초기값 설정
    conclusion = "판독 불가"
    confidence = 0
    
    # 2. best_result 계산 (조기 초기화 - Legacy 버그 수정)
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
    
    # 3. Supervisor Fast Path 결론 확인 (우선 순위 1)
    final_verdict = state.get("final_verdict")
    
    if final_verdict:
        conclusion = final_verdict.get("conclusion", conclusion)
        conf_val = final_verdict.get("confidence", 0)
        # 0.90 -> 90% 변환
        confidence = conf_val * 100 if conf_val <= 1.0 else conf_val
        hypothesis = final_verdict.get("reasoning", hypothesis)
        logger.info(f"Finalize: Adopted Supervisor Fast Path verdict: {conclusion} ({confidence}%)")
    
    # 4. Analyst Debate 결론 확인 (우선 순위 2)
    else:
        analyst_result = state.get("analyst_hypothesis")
        
        if analyst_result:
            try:
                # Pydantic 객체에서 데이터 추출
                if hasattr(analyst_result, "get_hypothesis_data"):
                    data = analyst_result.get_hypothesis_data()
                    conclusion = data.conclusion
                    confidence = data.probability
                elif isinstance(analyst_result, dict):
                    # 딕셔너리 처리
                    if analyst_result.get("revised_hypothesis"):
                        nested = analyst_result["revised_hypothesis"]
                        conclusion = nested.get("conclusion", "판독 불가")
                        confidence = nested.get("probability", 0)
                    else:
                        conclusion = analyst_result.get("conclusion", "판독 불가")
                        confidence = analyst_result.get("probability", 0)
                else:
                    # 객체 속성 접근
                    if getattr(analyst_result, "revised_hypothesis", None):
                        nested = analyst_result.revised_hypothesis
                        conclusion = getattr(nested, "conclusion", "판독 불가")
                        confidence = getattr(nested, "probability", 0)
                    else:
                        conclusion = getattr(analyst_result, "conclusion", "판독 불가")
                        confidence = getattr(analyst_result, "probability", 0)
                
                logger.info(f"Finalize: Adopted Analyst verdict: {conclusion} ({confidence}%)")
                
            except Exception as e:
                # 🔥 Pydantic 파싱이 완전히 실패한 극히 드문 경우
                logger.critical(f"Finalize: Pydantic extraction failed: {e}", exc_info=True)
                logger.error(f"Finalize: No results from Supervisor/Analyst. Defaulting to Indeterminate.")
                conclusion = "판독 불가"
                confidence = 0
        else:
            # 🔥 이론적으로 도달 불가능 (워크플로우상 Supervisor 또는 Analyst 중 하나는 반드시 실행)
            logger.critical(f"Finalize: Missing both final_verdict and analyst_result!")
            logger.critical(f"Finalize: Invalid workflow state.")
            conclusion = "판독 불가"
            confidence = 0

    # 5. Timeout 메시지 출력
    is_consensus = critique is not None and "NO_OBJECTION" in critique
    
    if debate_iter >= MAX_ITERATIONS and not is_consensus:
        logger.warning(f"Finalize: Debate timeout (Round {debate_iter}). Adopting Analyst's last verdict.")
    
    # 6. 최종 보고서 생성
    debate_log = "\n\n".join(debate_messages)
    
    final_report = f"""
[Deform 전문가 최종 판정 - Analyst-Critic 토론]

## 결론: {conclusion} ({confidence}%)

## 최종 합의 가설
{hypothesis}

## 종합 소견
Analyst-Critic {debate_iter}턴 토론 후 합의 도출.
{'합의된 판정' if is_consensus else '제한적 합의'}

## 토론 기록
{debate_log}
"""
    
    logger.info(f"Finalize: Final Conclusion: {conclusion} ({confidence}%)")
    
    return {
        "verdict_report": final_report,
        "verdict_confidence": confidence,
        "verdict_result": best_result
    }
