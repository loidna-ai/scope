"""
Necking (반단선) 전문가 노드
Map-Reduce 아키텍처 with Send API (Wire Focused)
"""
import json
import os
import asyncio
import re
import random
from typing import Dict, Any, List, Optional, TypedDict, Annotated
import operator
from google import genai
from google.genai import types
import datetime
import cv2


from config import TOP_N_HOTSPOTS

# [Mitigation] API 부하 방지를 위한 동시 실행 제한 세마포어
# 미리보기 모델(gemini-3-flash-preview)의 동시 요청 제한(Concurrency Limit)에 대응
gemini_semaphore = asyncio.Semaphore(2)

# Define Project Root for centralized output
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))





from src.utils import crop_roi_from_box
from src.tools.experts.expert_utils import _load_image_data
from src.prompts.common_prompts import (
    get_component_classifier_prompt,
)
from src.prompts.necking_expert_prompts import (
    get_necking_wire_prompt,
    get_analyst_initial_prompt,
    get_analyst_reanalysis_prompt,
    get_critic_prompt,
    get_necking_supervisor_prompt
)

from src.models.necking_models import NeckingEvidenceResult, SupervisorVerdict
from src.models.debate_models import AnalystHypothesis, CritiqueResult, HypothesisData, create_no_objection
from src.models.component_models import ComponentClassification
from src.nodes.enhancement import ImageEnhancer






# --- State Definition ---
from src.states.necking_state import WorkerState, NeckingExpertState

# --- Nodes ---

# hotspot_detector_node는 이제 src/nodes/common_nodes.py에서 공통으로 사용됩니다.

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
    hotspot = state["current_hotspot"]
    image_path = state["image_path"]
    hotspot_id = hotspot.get("id", "unknown")
    
    print(f"\n🔄 [Worker #{hotspot_id}] 증거 수집 시작...", flush=True)
    
    # ===== Step 1: ROI Crop + Enhancement =====
    detector_result = {
        "box_2d": hotspot.get("box_2d"),
        "feature_name": hotspot.get("damage_type"),
        "confidence": hotspot.get("severity_score")
    }
    
    box_2d = detector_result.get("box_2d")
    roi_image_path = image_path  # Default fallback
    
    if box_2d:
        print(f"✂️ [Worker #{hotspot_id}] ROI 크롭... {box_2d}")
        try:
            # 임시 파일로 크롭 (output/crops 미사용)
            cropped_path = await asyncio.to_thread(crop_roi_from_box, image_path, box_2d)
            
            # Enhancement (Async to prevent blocking)
            print(f"✨ [Worker #{hotspot_id}] ROI 이미지 2배 향상 적용 중...", flush=True)
            # 대형 ROI 안내 (Enhancement 1~2분 소요 가능)
            try:
                xmin, xmax = box_2d.get("xmin", 0), box_2d.get("xmax", 0)
                ymin, ymax = box_2d.get("ymin", 0), box_2d.get("ymax", 0)
                area = (xmax - xmin) * (ymax - ymin) if all([xmin, xmax, ymin, ymax]) else 0
                if area > 80_000:
                    print(f"   ⏱️ [Worker #{hotspot_id}] 대형 ROI (약 {xmax-xmin}×{ymax-ymin}px) — Enhancement 1~2분 소요 가능", flush=True)
            except Exception:
                pass
            try:
                # 1. 크롭된 이미지 로드 (Async I/O)
                cropped_img = await asyncio.to_thread(cv2.imread, cropped_path)
                if cropped_img is None:
                    raise ValueError("크롭된 이미지를 읽을 수 없습니다.")
                
                # 2. Enhancement (Blocking 작업을 thread로 offload)
                def enhance_image(img, path):
                    enhancer = ImageEnhancer()
                    enhanced_img = enhancer.upscale(img)
                    cv2.imwrite(path, enhanced_img)
                    return path
                
                enhanced_path = await asyncio.to_thread(enhance_image, cropped_img, cropped_path)
                print(f"✨ [Worker #{hotspot_id}] 향상 완료: {enhanced_path}", flush=True)
                
            except Exception as enh_err:
                print(f"⚠️ [Worker #{hotspot_id}] Enhancement Failed: {enh_err}")
                # 향상 실패해도 원본 크롭 이미지는 유지됨

            
            roi_image_path = cropped_path
        except Exception as e:
            print(f"⚠️ [Worker #{hotspot_id}] Crop Failed: {e}")
    
    # ===== Step 2: Component Classification (Async) =====
    connection_type = "None"
    MAX_RETRIES = 5  # 503 대응을 위해 3 -> 5회로 증설
    
    for retry_attempt in range(MAX_RETRIES):

        try:
            print(f"🔍 [Worker #{hotspot_id}] 부품 유형 식별... (시도 {retry_attempt + 1}/{MAX_RETRIES})", flush=True)
            # Blocking I/O offloading to thread
            roi_image_data = await asyncio.to_thread(_load_image_data, roi_image_path)
            original_image_data = await asyncio.to_thread(_load_image_data, image_path)
            
            prompt = get_component_classifier_prompt(roi_image_path)
            
            # 🔥 Pydantic Structured Output (Gemini Official Best Practice)
            
            client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

            model_name = os.environ.get("GEMINI_MODEL_NAME", "gemini-3-flash-preview")
            
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
            
            # Async API 호출 (Semaphore 적용하여 동시성 제어)
            async with gemini_semaphore:
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model_name,
                    contents=parts,
                    config={
                        "response_mime_type": "application/json",
                        "response_json_schema": ComponentClassification.model_json_schema(),
                        "safety_settings": safety_settings_block_none,
                    }
                )

            
            # [Debug/Safety] 응답 텍스트 확인 및 안전 파싱
            response_text = getattr(response, 'text', None)
            if not response_text:
                finish_reason = "Unknown"
                if hasattr(response, 'candidates') and response.candidates:
                    finish_reason = getattr(response.candidates[0], 'finish_reason', "Unknown")
                raise ValueError(f"Classifier 응답이 비어있습니다. (Finish Reason: {finish_reason})")

            # Pydantic 안전 파싱 (공식 권장 방식)
            classification = ComponentClassification.model_validate_json(response_text)
            
            connection_type = classification.deduced_type
            print(f"✅ [Worker #{hotspot_id}] 부품: {connection_type} (신뢰도: {classification.confidence}%)")
            
            # 성공 시 루프 탈출
            break
            
        except Exception as e:
            error_msg = str(e)
            is_retriable = any(code in error_msg for code in [
                "503", "429", "UNAVAILABLE", "overloaded", "Value", "empty",
                "SSL", "UNEXPECTED_EOF", "10054", "ECONNRESET", "끊겼습니다"
            ])

            if is_retriable and retry_attempt < MAX_RETRIES - 1:
                wait_time = 2 ** retry_attempt
                # 503 Overload일 경우 추가 대기 시간 부여
                if "503" in error_msg or "overloaded" in error_msg.lower():
                    wait_time += 5  # 기본 대기 + 5초 추가 리커버리 시간
                # SSL/연결 끊김(원격 호스트 강제 종료 등) 시 추가 대기
                if "SSL" in error_msg or "10054" in error_msg or "ECONNRESET" in error_msg or "끊겼습니다" in error_msg:
                    wait_time += 8

                jitter = random.uniform(0, wait_time * 0.1)
                total_wait = wait_time + jitter
                print(f"⚠️ [Worker #{hotspot_id}] Classifier Retry {retry_attempt + 1}/{MAX_RETRIES}: {e}. ({total_wait:.2f}s 대기)")
                await asyncio.sleep(total_wait)

            elif not is_retriable:
                print(f"❌ [Worker #{hotspot_id}] Classifier 최종 실패 (Non-retriable): {e}")
                print(f"⏭️ [Worker #{hotspot_id}] Wire로 가정하고 계속 진행")
                connection_type = "Wire"  # Fallback
                break
            else:
                # Max retries reached
                print(f"❌ [Worker #{hotspot_id}] Classifier 최종 실패 (Retries exhausted): {e}")
                print(f"⏭️ [Worker #{hotspot_id}] Wire로 가정하고 계속 진행")
                connection_type = "Wire"
                break

    
    # ===== Step 3: Evidence Collection (Wire Only - Async) =====

    observations = ""
    severity_score = 0
    report_confidence = 0
    evidence_quality = "low"
    is_critical = False
    evidence_result = None # [Fix] Initialize to prevent UnboundLocalError
    
    if "Wire" in connection_type:
        MAX_RETRIES = 5  # 503 대응 증설
        for retry_attempt in range(MAX_RETRIES):

            try:
                print(f"⚡ [Worker #{hotspot_id}] Wire 증거 수집 중... (시도 {retry_attempt + 1}/{MAX_RETRIES})", flush=True)
                print(f"⏳ [Worker #{hotspot_id}] Evidence Gemini API 호출 대기 중 (동시 2회 제한)...", flush=True)
                # Blocking I/O offloading to thread
                roi_data = await asyncio.to_thread(_load_image_data, roi_image_path)
                original_data = await asyncio.to_thread(_load_image_data, image_path)
                
                prompt = get_necking_wire_prompt(roi_image_path)
                
                # [Gemini Official Best Practice] Pydantic Structured Output
                
                # [Gemini Official Best Practice] Safety settings BLOCK_NONE
                safety_settings_block_none = [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                ]
                
                client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
                model_name = os.environ.get("GEMINI_MODEL_NAME", "gemini-3-flash-preview")

                
                # 이미지 파트 구성
                parts = [prompt]
                for img_data in [original_data, roi_data]:
                    parts.append(types.Part.from_bytes(
                        data=img_data,
                        mime_type="image/jpeg"
                    ))
                
                # Async API 호출 (Semaphore 적용)
                async with gemini_semaphore:
                    response = await asyncio.to_thread(
                        client.models.generate_content,
                        model=model_name,
                        contents=parts,
                        config={
                            "temperature": 1.0,
                            "response_mime_type": "application/json",
                            "response_json_schema": NeckingEvidenceResult.model_json_schema(),
                            "safety_settings": safety_settings_block_none,
                            "thinking_config": types.ThinkingConfig(
                                thinking_level="high"
                            )
                        }
                    )

                
                # [Debug/Safety] 응답 텍스트 확인 및 안전 파싱
                response_text = getattr(response, 'text', None)
                if not response_text:
                    finish_reason = "Unknown"
                    if hasattr(response, 'candidates') and response.candidates:
                        finish_reason = getattr(response.candidates[0], 'finish_reason', "Unknown")
                    raise ValueError(f"Evidence Collection 응답이 비어있습니다. (Finish Reason: {finish_reason})")

                # Pydantic 안전 파싱
                evidence_result = NeckingEvidenceResult.model_validate_json(response_text)
                
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
                
                # 1. High-risk: 확정적 "반단선" 판정
                if conclusion == "반단선":
                    severity_score = 80
                    is_critical = True
                    evidence_quality = "high"
                
                # 2. Medium-risk: "반단선 의심" 판정
                elif conclusion == "반단선 의심":
                    severity_score = 50
                    evidence_quality = "medium"
                    
                # 3. Low-risk: 그 외 (반단선 아님, 판독 불가 등)
                else:
                    severity_score = 30
                    evidence_quality = "low"
                    
                # 최종 리포트용 신뢰도는 AI가 산출한 값을 우선 사용
                report_confidence = ai_confidence if ai_confidence > 0 else severity_score



                
                # [Added] 상세 판정 결과 추출
                worker_verdict = f"[{evidence_result.step6_verdict.conclusion}] {evidence_result.step6_verdict.final_reasoning}"
                
                # [Phase 9] 개별 분석 결과 파일 저장 (Persistence)
                try:
                    output_dir = os.path.join(PROJECT_ROOT, "output", "necking_analysis")
                    os.makedirs(output_dir, exist_ok=True)
                    
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"hotspot_{hotspot_id}_{timestamp}.json"
                    file_path = os.path.join(output_dir, filename)
                    
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(evidence_result.model_dump(), f, ensure_ascii=False, indent=2)
                    print(f"💾 [Worker #{hotspot_id}] 분석 결과 저장됨: {file_path}")
                except Exception as save_err:
                    print(f"⚠️ [Worker #{hotspot_id}] 결과 저장 실패: {save_err}")

                print(f"📊 [Worker #{hotspot_id}] Evidence: {observations} (Score: {severity_score})", flush=True)
                
                # 성공 시 루프 탈출
                break

                
            except Exception as e:
                error_msg = str(e)
                # 재시도 가능한 오류: API(503,429), 빈 응답, SSL/연결 끊김(UNEXPECTED_EOF, 10054, ECONNRESET 등)
                is_retriable = any(code in error_msg for code in [
                    "503", "429", "UNAVAILABLE", "overloaded",
                    "비어있습니다", "empty", "FinishReason", "ValueError",
                    "응답이", "비어",
                    "SSL", "UNEXPECTED_EOF", "10054", "ECONNRESET", "끊겼습니다"
                ])

                if is_retriable and retry_attempt < MAX_RETRIES - 1:
                    wait_time = 2 ** retry_attempt
                    # 503/Overload 시 추가 대기
                    if "503" in error_msg or "overloaded" in error_msg.lower():
                        wait_time += 5
                    # SSL/연결 끊김(원격 호스트 강제 종료 등) 시 추가 대기
                    if "SSL" in error_msg or "10054" in error_msg or "ECONNRESET" in error_msg or "끊겼습니다" in error_msg:
                        wait_time += 8

                    jitter = random.uniform(0, wait_time * 0.1)
                    total_wait = wait_time + jitter
                    print(f"⚠️ [Worker #{hotspot_id}] Evidence Retry {retry_attempt + 1}/{MAX_RETRIES}: {e}. ({total_wait:.2f}s 대기)")
                    await asyncio.sleep(total_wait)

                elif not is_retriable:
                    print(f"❌ [Worker #{hotspot_id}] Evidence 최종 실패 (Non-retriable): {e}")
                    observations = f"분석 최종 실패 (Error): {str(e)}"
                    worker_verdict = observations
                    break
                else:
                    print(f"❌ [Worker #{hotspot_id}] Evidence 최종 실패 (Retries exhausted): {e}")
                    observations = f"분석 최종 실패 (Timeout): {str(e)}"
                    worker_verdict = observations
                    break

    else:
        observations = f"Wire가 아님: {connection_type}"
        worker_verdict = observations
        print(f"⏭️ [Worker #{hotspot_id}] Wire 아님, 스킵")
    
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
    analysis_entry = {
        "hotspot_id": hotspot_id,
        "hotspot_info": hotspot,
        "roi_image_path": roi_image_path,
        "specialist_result": {
            "verdict": worker_verdict,        # 판정 결론 (Conclusion + Reasoning)
            "confidence": report_confidence,  # AI 산출 신뢰도 우선 적용
            "visual_description": observations # 시각적 특징 (Taper, Apex 등)
        },
        "connection_type": connection_type,
        "damage_type": hotspot.get("damage_type", "Unknown")
    }

    print(f"✅ [Worker #{hotspot_id}] 증거 수집 완료\n", flush=True)

    # LangGraph Map-Reduce를 위한 리스트 포장
    return {
        "preliminary_assessments": [worker_report],
        "analysis_results": [analysis_entry] # 노트북/리포트용 로그
    }



# ===== Supervisor Node =====

async def supervisor_verdict(state: NeckingExpertState) -> Dict[str, Any]:

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
    assessments = state.get("preliminary_assessments", [])
    
    print(f"\n⚖️ [Supervisor] {len(assessments)}개 Worker 증거 검토 중...")
    
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
    print(f"📄 [Supervisor] Aggregation Context:\n{reports_text[:500]}...") # 로그 줄임
    
    # 2. Call LLM (Map-Reduce Reduction)
    prompt = get_necking_supervisor_prompt(reports_text=reports_text)
    
    try:
        # [Gemini Native] Use genai.Client instead of LangChain
        # Consistent with worker nodes and avoid undefined globals/imports
        
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        model_name = os.environ.get("GEMINI_MODEL_NAME", "gemini-3-flash-preview")
        
        # Safety settings (String based for compatibility)
        safety_settings_block_none = [
             {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
             {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
             {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
             {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]

        print("🤔 [Supervisor] 종합 판정 중...")
        
        
        # 🔥 Retry Logic with Exponential Backoff
        MAX_RETRIES = 5
        supervisor_result = None
        
        for retry_attempt in range(MAX_RETRIES):
            try:
                # Async call with semaphore
                async with gemini_semaphore:
                     response = await asyncio.to_thread(
                         client.models.generate_content,
                         model=model_name,
                         contents=prompt,
                         config={
                             "temperature": 0.0,
                             "response_mime_type": "application/json",
                             "response_json_schema": SupervisorVerdict.model_json_schema(),
                             "safety_settings": safety_settings_block_none,
                         }
                     )

                # Response handling
                response_text = getattr(response, 'text', None)
                if not response_text:
                     finish_reason = "Unknown"
                     if hasattr(response, 'candidates') and response.candidates:
                        finish_reason = getattr(response.candidates[0], 'finish_reason', "Unknown")
                     raise ValueError(f"Supervisor response is empty. (Finish Reason: {finish_reason})")

                # Pydantic validation
                supervisor_result = SupervisorVerdict.model_validate_json(response_text)
                
                # 성공 시 루프 탈출
                break
                
            except Exception as e:
                error_msg = str(e)
                is_retriable = any(code in error_msg for code in ["503", "429", "UNAVAILABLE", "overloaded", "Value", "empty"])

                if is_retriable and retry_attempt < MAX_RETRIES - 1:
                    wait_time = 2 ** retry_attempt
                    # 503 Overload일 경우 추가 대기 시간 부여
                    if "503" in error_msg or "overloaded" in error_msg.lower():
                        wait_time += 5
                    
                    
                    jitter = random.uniform(0, wait_time * 0.1)
                    total_wait = wait_time + jitter
                    # [Improvement] ValueError도 재시도 로그에 포함 (빈 응답 등)
                    print(f"⚠️ [Supervisor] Retry {retry_attempt+1}/{MAX_RETRIES}: {e}. ({total_wait:.2f}s 대기)")
                    await asyncio.sleep(total_wait)
                else:
                    print(f"❌ [Supervisor] Max retries reached or non-retriable error: {e}")
                    raise e  # 최종 실패 시 예외 전파

        if supervisor_result is None:
            raise ValueError("Supervisor failed to produce a result after retries.")

        # 3. Finalize
        print(f"⚖️ [Supervisor] Final Verdict: {supervisor_result.final_conclusion} (Conf: {supervisor_result.final_confidence})")
        print(f"📝 [Reasoning]: {supervisor_result.reasoning_process}")
        
        return {
            "final_verdict": {
                "conclusion": supervisor_result.final_conclusion,
                "confidence": supervisor_result.final_confidence / 100.0, # Normalize to 0.0-1.0 if needed, or keep integer
                "reasoning": f"[{supervisor_result.key_evidence_summary}] {supervisor_result.reasoning_process}"
            }
        }
        
    except Exception as e:
        print(f"❌ [Supervisor] Aggregation Error: {e}")
        # Fallback to Safe Default
        return {
            "final_verdict": {
                "conclusion": "판독 불가",
                "confidence": 0,
                "reasoning": f"Supervisor Error: {str(e)}"
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
    
    print(f"🔍 [Focus] Critic이 지적한 Hotspot: {sorted(mentioned_ids)}")
    
    return filtered if filtered else all_results

# ===== Analyst-Critic Debate Nodes =====

async def verdict_analyst_node(state: NeckingExpertState) -> Dict[str, Any]:

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
        print("\n🔍 [Verdict Analyst] 초기 가설 수립 중...")
        
        # 프롬프트 함수 호출 (중앙화)
        system_prompt = get_analyst_initial_prompt(report_summary)
        
    else:
        # [상황 2] 비평 수용 후 재분석 - 특정 부위 집중 모드
        print(f"\n🔄 [Verdict Analyst] 비평 수용 및 재분석 중... (Round {debate_iter + 1})")
        
        prev_hypothesis = state.get("current_hypothesis", "")
        
        # �� Phase 2: CritiqueResult.hotspots_mentioned 직접 사용
        critique_result = state.get("critique_result")
        
        if critique_result is not None and critique_result.hotspots_mentioned:
            # Pydantic 객체에서 명시적 Hotspot ID 추출 (정규표현식 불필요!)
            mentioned_ids = critique_result.hotspots_mentioned
            # Map-Reduce: 'id' 필드 사용
            focused_hotspots = [r for r in results if r.get("id") in mentioned_ids]
            print(f"🎯 [Analyst] Critic이 명시한 Hotspot: {mentioned_ids}")
        else:
            # Fallback: Legacy 정규표현식 추출
            focused_hotspots = extract_critiqued_hotspots(critique, results)
            print(f"⚠️ [Analyst] Fallback: 정규표현식으로 Hotspot 추출")
        
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
    
    
    # 🔥 Retry Logic with Exponential Backoff
    MAX_RETRIES = 5  # 503 대응 증설

    response = None
    
    for retry_attempt in range(MAX_RETRIES):
        try:
            # 🔥 Phase 2: Pydantic Structured Output
            # [Gemini Official Best Practice] Safety settings BLOCK_NONE
            safety_settings_block_none = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
            
            # Gemini Native Structured Output 사용
            client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
            model_name = os.environ.get("GEMINI_MODEL_NAME", "gemini-3-flash-preview")
            
            # [Gemini Official Best Practice] Structured Output: model_json_schema 사용
            async with gemini_semaphore:
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model_name,
                    contents=system_prompt,
                    config=types.GenerateContentConfig(
                        temperature=1.0,
                        response_mime_type="application/json",
                        response_json_schema=AnalystHypothesis.model_json_schema(), # response_schema 대신 json_schema 사용
                        safety_settings=safety_settings_block_none,
                        thinking_config=types.ThinkingConfig(
                            thinking_level="high"
                        )
                    )
                )


            
            # 성공 시 루프 탈출
            break
            
        except Exception as e:
            error_msg = str(e)
            # 재시도 가능한 오류 판별
            is_retriable = any(code in error_msg for code in ["503", "429", "UNAVAILABLE", "overloaded", "Value", "empty"])
            
            if is_retriable and retry_attempt < MAX_RETRIES - 1:
                wait_time = 2 ** retry_attempt
                # 503/Overload 대응
                if "503" in error_msg or "overloaded" in error_msg.lower():
                    wait_time += 5
                    
                jitter = random.uniform(0, wait_time * 0.1)
                total_wait = wait_time + jitter
                print(f"⚠️ [Analyst Retry {retry_attempt + 1}/{MAX_RETRIES}] {error_msg}")
                print(f"⏰ Waiting {total_wait:.2f}s before retry...")
                # Async 함수 내에서 sleep 시 await 사용 (중요!)
                await asyncio.sleep(total_wait)

            else:
                # 재시도 불가능하거나 최종 실패
                print(f"❌ [Analyst Error] {e}")
                return {
                    "current_hypothesis": "분석 오류 발생",
                    "debate_messages": [f"[Analyst Error] {str(e)}"],
                    "debate_iteration": debate_iter + 1
                }
    
    # Retry 성공 후 처리
    if response is None:
        print(f"❌ [Analyst] All retries failed")
        return {
            "current_hypothesis": "분석 오류 발생",
            "debate_messages": [f"[Analyst Error] All retries exhausted"],
            "debate_iteration": debate_iter + 1
        }
    
    try:
        # [Debug/Safety] 응답 텍스트 확인 및 안전 파싱
        response_text = getattr(response, 'text', None)
        finish_reason = "Unknown"
        if hasattr(response, 'candidates') and response.candidates:
            finish_reason = getattr(response.candidates[0], 'finish_reason', "Unknown")
            
        print(f"📋 [Verdict Analyst] Finish reason: {finish_reason}")
        
        if not response_text:
            raise ValueError(f"Gemini API 응답 텍스트가 비어있습니다. (Finish Reason: {finish_reason})")

        # Pydantic 안전 파싱 (공식 권장 방식: model_validate_json)
        analyst_result = AnalystHypothesis.model_validate_json(response_text)

        
        # 가설 추출 (Pydantic 메서드 사용)
        hypothesis = analyst_result.get_hypothesis()
        
        print(f"💡 [Analyst] 가설: {hypothesis}")
        
        return {
            # [Phase 2] Pydantic 객체 저장
            "analyst_hypothesis": analyst_result,
            
            # [Legacy] 하위 호환성
            "current_hypothesis": hypothesis,
            
            "debate_messages": [f"[Analyst Round {debate_iter + 1}] {response.text}"],
            "debate_iteration": debate_iter + 1
        }
        
    except Exception as e:
        print(f"⚠️ [Analyst Parsing Error] {e}")
        return {
            "current_hypothesis": "분석 오류 발생",
            "debate_messages": [f"[Analyst Error] {str(e)}"],
            "debate_iteration": debate_iter + 1
        }


async def verdict_critic_node(state: NeckingExpertState) -> Dict[str, Any]:

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
        print("\n⏭️ [Verdict Critic] 가설 부재로 검토 생략")
        return {
            "critique_points": "NO_OBJECTION",
            "debate_messages": ["[Critic] No hypothesis to critique."]
        }
    
    print(f"\n🔎 [Verdict Critic] 가설 검증 중... (Round {debate_iter})")
    
    # 🔥 Phase 1 Critical Fix: Image Access for Critic
    # Critic이 원본 이미지와 ROI 이미지를 직접 보고 검증
    
    # 1. 원본 이미지 로드
    image_path = state.get("image_path")
    image_data_list = []
    
    try:
        if image_path:
            original_image = _load_image_data(image_path)
            image_data_list.append(original_image)
            print(f"📷 [Critic Image Access] 원본 이미지 로드: {image_path}")
    except Exception as img_err:
        print(f"⚠️ [Critic] 원본 이미지 로드 실패: {img_err}")
    
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
                print(f"⚠️ [Critic] ROI 이미지 로드 실패: {roi_err}")
    
    if roi_loaded_count > 0:
        print(f"📷 [Critic Image Access] ROI 이미지 {roi_loaded_count}개 로드 완료")
    
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
    
    
    # 🔥 Retry Logic with Exponential Backoff
    MAX_RETRIES = 5  # 503 대응 증설
    response = None
    
    for retry_attempt in range(MAX_RETRIES):
        try:
            # 🔥 핵심 변경: Gemini Native Structured Output
            client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
            model_name = os.environ.get("GEMINI_MODEL_NAME", "gemini-3-flash-preview")

            
            if image_data_list:
                # 이미지가 있으면 Vision API 사용 (Multimodal + Structured)
                print(f"🔄 [Critic API Call] Gemini Vision API 호출 중... (이미지 {len(image_data_list)}개)")
                
                parts = [system_prompt]
                for idx, img_data in enumerate(image_data_list, 1):
                    parts.append(types.Part.from_bytes(
                        data=img_data,
                        mime_type="image/jpeg"
                    ))
                
                # Async API 호출 (Semaphore 적용)
                async with gemini_semaphore:
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

            else:
                # 이미지 로드 실패 시 텍스트만 사용 (Fallback)
                print("⚠️ [Critic] 이미지 없이 텍스트 기반 검증 (정확도 낮음)")
                print(f"🔄 [Critic API Call] Gemini Text API 호출 중... (모델: {model_name})")
                # [Gemini Official Best Practice] Safety settings BLOCK_NONE
                safety_settings_block_none = [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                ]
                
                #Structured Output: Pydantic 모델 직접 전달 (model_json_schema 사용)
                async with gemini_semaphore:
                    response = await asyncio.to_thread(
                        client.models.generate_content,
                        model=model_name,
                        contents=system_prompt,
                        config=types.GenerateContentConfig(
                            temperature=1.0,
                            response_mime_type="application/json",
                            response_json_schema=CritiqueResult.model_json_schema(), # response_schema 대신 json_schema 사용
                            safety_settings=safety_settings_block_none,
                            thinking_config=types.ThinkingConfig(
                                thinking_level="high"
                            )
                        )
                    )

                print(f"✅ [Critic API Call] API 응답 수신 완료")
            
            # 성공 시 루프 탈출
            break
            
        except Exception as e:
            error_msg = str(e)
            # 재시도 가능한 오류 판별
            is_retriable = any(code in error_msg for code in ["503", "429", "UNAVAILABLE", "overloaded", "Value", "empty"])
            
            if is_retriable and retry_attempt < MAX_RETRIES - 1:
                wait_time = 2 ** retry_attempt
                if "503" in error_msg or "overloaded" in error_msg.lower():
                    wait_time += 5
                    
                jitter = random.uniform(0, wait_time * 0.1)
                total_wait = wait_time + jitter
                print(f"⚠️ [Critic Retry {retry_attempt + 1}/{MAX_RETRIES}] {error_msg}")
                print(f"⏰ Waiting {total_wait:.2f}s before retry...")
                await asyncio.sleep(total_wait)

            else:
                # 재시도 불가능하거나 최종 실패
                print(f"❌ [Critic Error] {e}")
                import traceback
                traceback.print_exc()
                
                # 에러 시 NO_OBJECTION 반환
                no_objection = create_no_objection()
                return {
                    "critique_result": no_objection,
                    "critique_points": "NO_OBJECTION",
                    "debate_messages": [f"[Critic Error] {str(e)}"]
                }
    
    # Retry 성공 후 처리
    if response is None:
        print(f"❌ [Critic] All retries failed")
        no_objection = create_no_objection()
        return {
            "critique_result": no_objection,
            "critique_points": "NO_OBJECTION",
            "debate_messages": [f"[Critic Error] All retries exhausted"]
        }
    
    try:
        # [Debug/Safety] 응답 텍스트 확인 및 안전 파싱
        response_text = getattr(response, 'text', None)
        finish_reason = "Unknown"
        if hasattr(response, 'candidates') and response.candidates:
            finish_reason = getattr(response.candidates[0], 'finish_reason', "Unknown")
            
        print(f"📋 [Verdict Critic] Finish reason: {finish_reason}")
        
        if not response_text:
            raise ValueError(f"Gemini API 응답 텍스트가 비어있습니다. (Finish Reason: {finish_reason})")

        # Pydantic 안전 파싱 (공식 권장 방식: model_validate_json)
        critique_result = CritiqueResult.model_validate_json(response_text)

        
        # is_approved bool 체크 (문자열 검색 불필요!)
        if critique_result.is_approved:
            print("✅ [Critic] 합의 도출: NO_OBJECTION")
        else:
            print(f"⚠️ [Critic] 이의 제기: {critique_result.objection_type}")
            if critique_result.hotspots_mentioned:
                print(f"🎯 [Critic] 지적 Hotspot: {critique_result.hotspots_mentioned}")
        
        return {
            # [Phase 2] Pydantic 객체 저장
            "critique_result": critique_result,
            
            # [Legacy] 하위 호환성 (문자열)
            "critique_points": response.text,
            
            "debate_messages": [f"[Critic Round {debate_iter}] {response.text}"]
        }
        
    except Exception as e:
        print(f"⚠️ [Critic Parsing Error] {e}")
        
        # 에러 시 NO_OBJECTION 반환
        no_objection = create_no_objection()
        return {
            "critique_result": no_objection,
            "critique_points": "NO_OBJECTION",
            "debate_messages": [f"[Critic Error] {str(e)}"]
        }


async def verdict_finalize_node(state: NeckingExpertState) -> Dict[str, Any]:

    """
    Final Verdict Finalize (최종 정리)
    - 합의된 가설을 바탕으로 최종 보고서 생성
    - Timeout 시 "판독 불가" 처리
    """
    hypothesis = state.get("current_hypothesis", "")
    debate_messages = state.get("debate_messages", [])
    debate_iter = state.get("debate_iteration", 0)
    critique = state.get("critique_points", "")
    results = state.get("analysis_results", [])
    
    MAX_ITERATIONS = 3
    
    print(f"\n📋 [Verdict Finalize] 최종 판정 정리 중... (Debate Rounds: {debate_iter})")
    print(f"   - Accumulated results count: {len(results)}")

    
    # Timeout 처리
    # =========================================================
    # [Integrated Finalize Logic] 통합 결론 도출 로직
    # =========================================================
    
    import re
    
    # 1. 초기값 설정
    conclusion = "판독 불가"
    confidence = 0
    
    # 2. Supervisor Fast Path 결론 확인 (우선 순위 1)
    final_verdict = state.get("final_verdict")
    analyst_result = state.get("analyst_hypothesis")
    
    if final_verdict:
        conclusion = final_verdict.get("conclusion", conclusion)
        conf_val = final_verdict.get("confidence", 0)
        # 0.90 -> 90% 변환
        confidence = conf_val * 100 if conf_val <= 1.0 else conf_val
        hypothesis = final_verdict.get("reasoning", hypothesis)
        print(f"✅ [Finalize] Supervisor Fast Path 결론 채택: {conclusion} ({confidence}%)")
        
    elif analyst_result:

        # [Option A] Pydantic 객체 활용
        try:
            # 1. Pydantic 모델 메서드 활용 (Initial/Revised 자동 처리)
            if hasattr(analyst_result, "get_hypothesis_data"):
                data = analyst_result.get_hypothesis_data()
                conclusion = data.conclusion
                confidence = data.probability
            # 2. 딕셔너리인 경우 (수동 파싱)
            elif isinstance(analyst_result, dict):
                if analyst_result.get("revised_hypothesis"):
                    nested = analyst_result["revised_hypothesis"]
                    conclusion = nested.get("conclusion", "판독 불가")
                    confidence = nested.get("probability", 0)
                else:
                    conclusion = analyst_result.get("conclusion", "판독 불가")
                    confidence = analyst_result.get("probability", 0)
            # 3. 그 외 객체 (단순 속성 접근)
            else:
                # Revised 우선 확인
                if getattr(analyst_result, "revised_hypothesis", None):
                    nested = analyst_result.revised_hypothesis
                    conclusion = getattr(nested, "conclusion", "판독 불가")
                    confidence = getattr(nested, "probability", 0)
                else:
                    conclusion = getattr(analyst_result, "conclusion", "판독 불가")
                    confidence = getattr(analyst_result, "probability", 0)
                    
            print(f"✅ [Finalize] Analyst Pydantic 결론: {conclusion} ({confidence}%)")
            
        except Exception as e:
            print(f"⚠️ [Finalize] Pydantic 추출 실패: {e}")
            # Fallback will trigger below
        
    else:
        # [Option B] Legacy 문자열 파싱 Fallback (Deprecated but kept for safety)
        # Pydantic 파싱이 완전히 실패했을 때 최후의 수단으로 텍스트에서 정보 추출
        match = re.search(r"(반단선|외부 화재|판독 불가).*?(\d+)%", hypothesis)
        if match:
            conclusion = match.group(1)
            confidence = float(match.group(2))
        else:
            if "반단선" in hypothesis:
                conclusion = "반단선"
                confidence = max_confidence if max_confidence > 0 else 50
            elif "외부" in hypothesis or "화재" in hypothesis:
                conclusion = "외부 화재"
                confidence = 30
        print(f"⚠️ [Finalize] Legacy 문자열 파싱(Fallback): {conclusion} ({confidence}%)")

    # 3. Timeout 메시지 출력 (패널티 제거)
    is_consensus = "NO_OBJECTION" in critique
    
    if debate_iter >= MAX_ITERATIONS and not is_consensus:
        print(f"⚠️ [Timeout] 합의 실패 (Round {debate_iter}). Analyst의 마지막 결론을 그대로 채택합니다.")
    
    # [Missing Logic Restored] best_result 계산
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

    # Debate Log 추가
    debate_log = "\n\n".join(debate_messages)
    
    final_report = f"""
[Necking 전문가 최종 판정 - Analyst-Critic 토론]

## 결론: {conclusion} ({confidence}%)

## 최종 합의 가설
{hypothesis}

## 종합 소견
Analyst-Critic {debate_iter}턴 토론 후 합의 도출.
{'합의된 판정' if 'NO_OBJECTION' in critique else '제한적 합의'}

## 토론 기록
{debate_log}
"""
    
    print(f"✅ [Finalize] 결론: {conclusion} ({confidence}%)")
    
    return {
        "verdict_report": final_report,
        "verdict_confidence": confidence,
        "verdict_result": best_result
    }

