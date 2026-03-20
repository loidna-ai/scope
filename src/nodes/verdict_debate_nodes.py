"""
공통 판정 및 논쟁 노드 (Generic Verdict and Debate Nodes)

각 전문가 모듈(Contact, Deform, Necking)에서 중복 사용되는
Supervisor, Analyst, Critic, Finalize 노드를 제네릭화한 팩토리 함수들을 제공합니다.
"""
import os
import json
from typing import Dict, Any, Callable, Type
from google.genai import types

import config
from src.utils.expert_config import MAX_DEBATE_ITERATIONS

from src.utils.logging_config import setup_logger
from src.utils import async_retry_with_backoff, get_genai_client
from src.utils.expert_image_utils import ExpertImageLoader
from src.utils.expert_report_utils import format_report_summary, extract_critiqued_hotspots
from src.utils.expert_api_utils import validate_gemini_response, extract_finish_reason, call_analyst_api, call_critic_vision_api, call_critic_text_api, call_supervisor_api
from src.models.debate_models import AnalystHypothesis, CritiqueResult, create_no_objection

logger = setup_logger(__name__)


def create_supervisor_verdict_node(
    expert_type: str,
    get_supervisor_prompt_fn: Callable[[str], str],
    SupervisorVerdict: Type  # Pydantic 모델 클래스
):
    """
    Supervisor 노드를 생성하는 팩토리 함수
    """
    async def supervisor_verdict(state: Dict[str, Any]) -> Dict[str, Any]:
        assessments = state.get("preliminary_assessments", [])
        logger.info(f"{expert_type.capitalize()} Supervisor: Reviewing evidence from {len(assessments)} Workers...")
        
        if not assessments:
            return {
                "final_verdict": {
                    "conclusion": "분석 불가",
                    "confidence": 0.0,
                    "reasoning": "분석된 증거 없음"
                },
                "debate_context": None
            }
        
        # 1. Prepare Aggregation Context
        reports_text = format_report_summary(assessments, expert_type=expert_type)
        logger.debug(f"{expert_type.capitalize()} Supervisor: Aggregation Context:\n{reports_text[:500]}...")
        
        # 2. Call LLM
        prompt = get_supervisor_prompt_fn(reports_text=reports_text)
        
        try:
            client = get_genai_client()
            model_name = os.environ.get("GEMINI_PRO_MODEL_NAME", config.GEMINI_PRO_MODEL_NAME)
            print(f"🤔 [{expert_type.capitalize()} Supervisor] 종합 판정 중...")
            
            async def _call_supervisor_wrapper(**kwargs):
                return await call_supervisor_api(
                    client=kwargs["client"],
                    model_name=kwargs["model_name"],
                    prompt=kwargs["prompt"],
                    response_schema=SupervisorVerdict,
                    temperature=0.0,
                    context_name=kwargs.get("context_name", f"{expert_type.capitalize()} Supervisor")
                )
            
            response = await async_retry_with_backoff(
                _call_supervisor_wrapper,
                client=client,
                model_name=model_name,
                prompt=prompt,
                context_name=f"{expert_type.capitalize()} Supervisor",
                max_retries=5
            )
            
            supervisor_result = SupervisorVerdict.model_validate_json(response.text)
            
            conclusion = supervisor_result.final_conclusion
            confidence = supervisor_result.final_confidence
            
            logger.info(f"{expert_type.capitalize()} Supervisor: Final Verdict: {conclusion} (Conf: {confidence})")
            
            # Debate 필요 여부 판단:
            # - 신뢰도 60% 미만이거나
            # - 결론에 "의심" 또는 "판독 불가" 키워드 포함 시 Debate 경로 활성화
            DOUBT_KEYWORDS = ["의심", "판독 불가"]
            needs_debate = confidence < 60 or any(kw in conclusion for kw in DOUBT_KEYWORDS)
            
            debate_context = None
            if needs_debate:
                debate_context = {
                    "requires_debate": True,
                    "reason": f"confidence={confidence}, conclusion={conclusion}"
                }
                logger.info(f"{expert_type.capitalize()} Supervisor: Debate requested ({debate_context['reason']})")
            else:
                logger.info(f"{expert_type.capitalize()} Supervisor: Fast path (no debate needed)")
            
            return {
                "final_verdict": {
                    "conclusion": conclusion,
                    "confidence": confidence / 100.0,
                    "reasoning": f"[{supervisor_result.key_evidence_summary}] {supervisor_result.reasoning_process}"
                },
                "debate_context": debate_context
            }
            
        except Exception as e:
            logger.error(f"{expert_type.capitalize()} Supervisor Error: {str(e)}", exc_info=True)
            return {
                "final_verdict": {
                    "conclusion": "판독 불가",
                    "confidence": 0,
                    "reasoning": "시스템 오류로 인해 분석을 완료할 수 없습니다. (판독 보류)"
                },
                "debate_context": None  # 시스템 오류는 debate 불필요
            }
            
    return supervisor_verdict


def create_verdict_analyst_node(
    expert_type: str,
    get_initial_prompt_fn: Callable[[str], str],
    get_reanalysis_prompt_fn: Callable[..., str]
):
    """
    Analyst 노드를 생성하는 팩토리 함수
    """
    async def verdict_analyst_node(state: Dict[str, Any]) -> Dict[str, Any]:
        results = state.get("preliminary_assessments", [])
        debate_messages = state.get("debate_messages", [])
        critique = state.get("critique_points", "")
        debate_iter = state.get("debate_iteration", 0)
        
        if not results:
            return {
                "current_hypothesis": "분석된 특이점이 없습니다.",
                "debate_messages": ["[Analyst] No hotspots detected."],
                "debate_iteration": debate_iter + 1
            }
        
        report_summary = format_report_summary(results, expert_type=expert_type)
        
        if not debate_messages:
            logger.info(f"{expert_type.capitalize()} Analyst: Establishing initial hypothesis...")
            system_prompt = get_initial_prompt_fn(report_summary)
        else:
            logger.info(f"{expert_type.capitalize()} Analyst: Re-analyzing based on critique (Round {debate_iter + 1})...")
            prev_hypothesis = state.get("current_hypothesis", "")
            critique_result = state.get("critique_result")
            
            if critique_result is not None and critique_result.hotspots_mentioned:
                mentioned_ids = critique_result.hotspots_mentioned
                focused_hotspots = [r for r in results if r.get("id") in mentioned_ids]
                logger.info(f"{expert_type.capitalize()} Analyst: Critic specified hotspots: {mentioned_ids}")
            else:
                focused_hotspots = extract_critiqued_hotspots(critique, results)
                logger.warning(f"{expert_type.capitalize()} Analyst: Fallback to regex for hotspot extraction")
            
            focused_summary = format_report_summary(focused_hotspots, expert_type=expert_type)
            debate_transcript = "\n\n".join(debate_messages)
            system_prompt = get_reanalysis_prompt_fn(
                prev_hypothesis=prev_hypothesis,
                critique=critique,
                focused_summary=focused_summary,
                total_hotspot_count=len(results),
                focused_count=len(focused_hotspots),
                full_context=report_summary,
                critique_result=critique_result,
                debate_transcript=debate_transcript
            )
        
        try:
            client = get_genai_client()
            model_name = os.environ.get("GEMINI_PRO_MODEL_NAME", config.GEMINI_PRO_MODEL_NAME)
            
            async def _call_analyst_wrapper(**kwargs):
                return await call_analyst_api(
                    client=kwargs["client"],
                    model_name=kwargs["model_name"],
                    system_prompt=kwargs["system_prompt"],
                    response_schema=AnalystHypothesis,
                    thinking_level="high",
                    temperature=1.0,
                    context_name=kwargs.get("context_name", f"{expert_type.capitalize()} Analyst")
                )
            
            response = await async_retry_with_backoff(
                _call_analyst_wrapper,
                client=client,
                model_name=model_name,
                system_prompt=system_prompt,
                context_name=f"{expert_type.capitalize()} Analyst",
                max_retries=5
            )

            response_text = validate_gemini_response(response, context_name=f"{expert_type.capitalize()} Analyst")
            analyst_result = AnalystHypothesis.model_validate_json(response_text)
            hypothesis = analyst_result.get_hypothesis()
            
            logger.info(f"{expert_type.capitalize()} Analyst: Hypothesis: {hypothesis}")
            
            return {
                "analyst_hypothesis": analyst_result,
                "current_hypothesis": hypothesis,
                "debate_messages": [f"[Analyst Round {debate_iter + 1}] {response.text}"],
                "debate_iteration": debate_iter + 1
            }
            
        except Exception as e:
            logger.error(f"{expert_type.capitalize()} Analyst Parsing Error: {e}", exc_info=True)
            return {
                "current_hypothesis": "분석 오류 발생",
                "debate_messages": [f"[{expert_type.capitalize()} Analyst Error] {str(e)}"],
                "debate_iteration": debate_iter + 1
            }
            
    return verdict_analyst_node


def create_verdict_critic_node(
    expert_type: str,
    get_critic_prompt_fn: Callable[[str, str, str], str]
):
    """
    Critic 노드를 생성하는 팩토리 함수
    """
    async def verdict_critic_node(state: Dict[str, Any]) -> Dict[str, Any]:
        hypothesis = state.get("current_hypothesis", "")
        results = state.get("analysis_results", [])
        # [Phase 1.1] analysis_results 비어 있으면 preliminary_assessments/preprocessed_hotspots에서 ROI Fallback
        if not results:
            assessments = state.get("preliminary_assessments", [])
            preprocessed = state.get("preprocessed_hotspots") or []
            for a in assessments:
                roi_path = a.get("_roi_image_path")
                if not roi_path and preprocessed:
                    for p in preprocessed:
                        if p.get("id") == a.get("id"):
                            roi_path = p.get("roi_image_path")
                            break
                if roi_path:
                    results.append({"roi_image_path": roi_path})
            if results:
                logger.info(f"{expert_type.capitalize()} Critic: Using ROI fallback from preliminary_assessments/preprocessed_hotspots")
        debate_iter = state.get("debate_iteration", 0)
        
        if not hypothesis or "오류" in hypothesis or "없습니다" in hypothesis:
            logger.info(f"{expert_type.capitalize()} Critic: Skipping - No hypothesis to critique")
            return {
                "critique_points": "NO_OBJECTION",
                "debate_messages": ["[Critic] No hypothesis to critique."]
            }
        
        logger.info(f"{expert_type.capitalize()} Critic: Verifying hypothesis (Round {debate_iter})...")
        
        image_path = state.get("image_path")
        image_data_list = []
        image_loader = ExpertImageLoader(use_cache=True)
        
        try:
            if image_path:
                original_image = await image_loader.load_image(image_path)
                image_data_list.append(original_image)
        except Exception as img_err:
            logger.warning(f"{expert_type.capitalize()} Critic: Failed to load original image: {img_err}")
        
        for res in results:
            roi_path = res.get("roi_image_path")
            if roi_path:
                try:
                    roi_image = await image_loader.load_image(roi_path)
                    image_data_list.append(roi_image)
                except Exception as roi_err:
                    logger.warning(f"{expert_type.capitalize()} Critic: Failed to load ROI image: {roi_err}")
        
        # format_report_summary는 preliminary_assessments 구조(facts/opinion) 필요
        assessments = state.get("preliminary_assessments", [])
        report_summary = format_report_summary(assessments, expert_type=expert_type)
        
        image_context = ""
        if image_data_list:
            image_context = f"""
<image_access>
⚠️ **중요**: 당신은 분석가의 주장을 **실제 이미지로 직접 검증**할 수 있습니다.
- Image 1: 원본 전체 이미지 (Context)
- Image 2~{len(image_data_list)}: 각 Hotspot의 ROI 이미지 (Detail)

분석가가 주장하는 내용이 실제 이미지에 나타나는지 다음을 확인하십시오:
1. 해당 Hotspot의 ROI 이미지에서 **직접 확인**하십시오.
2. 분석가의 주장과 실제 이미지가 일치하지 않으면 **즉시 지적**하십시오.
</image_access>
"""
        
        system_prompt = get_critic_prompt_fn(
            hypothesis=hypothesis,
            report_summary=report_summary,
            image_context=image_context
        )
        
        try:
            client = get_genai_client()
            model_name = os.environ.get("GEMINI_PRO_MODEL_NAME", config.GEMINI_PRO_MODEL_NAME)
            
            if image_data_list:
                logger.info(f"{expert_type.capitalize()} Critic: Calling Vision API with images...")
                parts = [system_prompt]
                for img_data in image_data_list:
                    parts.append(types.Part.from_bytes(data=img_data, mime_type="image/jpeg"))
                    
                async def _call_critic_vision(**kwargs):
                    return await call_critic_vision_api(
                        client=kwargs["client"],
                        model_name=kwargs["model_name"],
                        parts=kwargs["parts"],
                        response_schema=CritiqueResult,
                        thinking_level="medium",
                        temperature=1.0,
                        context_name=kwargs.get("context_name", f"{expert_type.capitalize()} Critic Vision")
                    )
                
                response = await async_retry_with_backoff(
                    _call_critic_vision,
                    client=client,
                    model_name=model_name,
                    parts=parts,
                    context_name=f"{expert_type.capitalize()} Critic Vision",
                    max_retries=5
                )
            else:
                logger.warning(f"{expert_type.capitalize()} Critic: Text-only verification")
                async def _call_critic_text(**kwargs):
                    return await call_critic_text_api(
                        client=kwargs["client"],
                        model_name=kwargs["model_name"],
                        prompt=kwargs["prompt"],
                        response_schema=CritiqueResult,
                        thinking_level="high",
                        temperature=1.0,
                        context_name=kwargs.get("context_name", f"{expert_type.capitalize()} Critic Text")
                    )
                
                response = await async_retry_with_backoff(
                    _call_critic_text,
                    client=client,
                    model_name=model_name,
                    prompt=system_prompt,
                    context_name=f"{expert_type.capitalize()} Critic Text",
                    max_retries=5
                )
                
            response_text = validate_gemini_response(response, context_name=f"{expert_type.capitalize()} Critic")
            critique_result = CritiqueResult.model_validate_json(response_text)
            
            if critique_result.is_approved:
                logger.info(f"{expert_type.capitalize()} Critic: Consensus reached: NO_OBJECTION")
            else:
                logger.info(f"{expert_type.capitalize()} Critic: Objection raised: {critique_result.objection_type}")
            
            return {
                "critique_result": critique_result,
                "critique_points": response.text,
                "debate_messages": [f"[Critic Round {debate_iter}] {response.text}"]
            }
            
        except Exception as e:
            logger.error(f"{expert_type.capitalize()} Critic Error: {e}", exc_info=True)
            no_objection = create_no_objection()
            return {
                "critique_result": no_objection,
                "critique_points": "NO_OBJECTION",
                "debate_messages": [f"[Critic Error] {str(e)}"]
            }
            
    return verdict_critic_node


def create_verdict_finalize_node(expert_type: str):
    """
    Finalize 노드를 생성하는 팩토리 함수
    """
    async def verdict_finalize_node(state: Dict[str, Any]) -> Dict[str, Any]:
        hypothesis = state.get("current_hypothesis", "")
        debate_messages = state.get("debate_messages", [])
        debate_iter = state.get("debate_iteration", 0)
        results = state.get("analysis_results", [])
        
        logger.info(f"{expert_type.capitalize()} Finalize: Consolidating verdict (Debate Rounds: {debate_iter})...")
        
        conclusion = "판독 불가"
        confidence = 0
        
        max_confidence = 0
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
        
        final_verdict = state.get("final_verdict")
        
        if final_verdict:
            conclusion = final_verdict.get("conclusion", conclusion)
            conf_val = final_verdict.get("confidence", 0)
            confidence = conf_val * 100 if conf_val <= 1.0 else conf_val
            hypothesis = final_verdict.get("reasoning", hypothesis)
            logger.info(f"{expert_type.capitalize()} Finalize: Adopted Supervisor Fast Path verdict: {conclusion} ({confidence}%)")
        else:
            analyst_result = state.get("analyst_hypothesis")
            if analyst_result:
                try:
                    if hasattr(analyst_result, "get_hypothesis_data"):
                        data = analyst_result.get_hypothesis_data()
                        conclusion = data.conclusion
                        confidence = data.probability
                    elif isinstance(analyst_result, dict):
                        if analyst_result.get("revised_hypothesis"):
                            conclusion = analyst_result["revised_hypothesis"].get("conclusion", "판독 불가")
                            confidence = analyst_result["revised_hypothesis"].get("probability", 0)
                        else:
                            conclusion = analyst_result.get("conclusion", "판독 불가")
                            confidence = analyst_result.get("probability", 0)
                    else:
                        if getattr(analyst_result, "revised_hypothesis", None):
                            conclusion = getattr(analyst_result.revised_hypothesis, "conclusion", "판독 불가")
                            confidence = getattr(analyst_result.revised_hypothesis, "probability", 0)
                        else:
                            conclusion = getattr(analyst_result, "conclusion", "판독 불가")
                            confidence = getattr(analyst_result, "probability", 0)
                    
                    logger.info(f"{expert_type.capitalize()} Finalize: Adopted Analyst verdict: {conclusion} ({confidence}%)")
                    # [Phase 2.2] Rebuttal 페널티: debate 발생 시 rebuttal_to_critic 비어 있으면 신뢰도 0.8배
                    if debate_iter > 0 and hasattr(analyst_result, "revised_hypothesis") and analyst_result.revised_hypothesis:
                        rev = analyst_result.revised_hypothesis
                        rebuttal = getattr(rev, "rebuttal_to_critic", None) or ""
                        if not (rebuttal and rebuttal.strip()):
                            confidence = confidence * 0.8
                            logger.info(f"{expert_type.capitalize()} Finalize: Rebuttal penalty applied (confidence *= 0.8)")
                except Exception as e:
                    logger.error(f"{expert_type.capitalize()} Finalize Logic extraction error: {e}")
                    conclusion = "판독 불가"
        
        is_debate_timeout = (debate_iter >= MAX_DEBATE_ITERATIONS)
        if is_debate_timeout:
            hypothesis += "\n(참고: 분석관-비평가 간 합의 도달에 실패하여 분석관의 최종 의견을 채택함. 신뢰도 페널티 적용됨)"
            confidence = confidence * 0.7
            if confidence > 50.0:
                confidence = 50.0
            if "불가" not in conclusion and "아님" not in conclusion and "의심" not in conclusion:
                conclusion += " 의심"
        
        # [Phase 1.4] 토론 섹션: debate_iter > 0일 때 토론 턴 수, 합의 여부, 토론 기록 포함
        debate_section = ""
        if debate_iter > 0:
            critique_result = state.get("critique_result")
            consensus = "합의 도달" if (critique_result and getattr(critique_result, "is_approved", False)) else "합의 미도달"
            debate_section = f"""
### Analyst-Critic 토론
- 토론 턴 수: {debate_iter}
- 합의 여부: {consensus}
- 토론 기록:
{chr(10).join(f"  {m}" for m in debate_messages)}
"""
            
        full_report = f"""## {expert_type.capitalize()} 전문가 최종 분석 결과

### 특이점 진단 요약
- 발견된 특이점 개수: {len(results)}개
- 최종 판독: **{conclusion}** (신뢰도: {confidence:.1f}%)
{debate_section}
### 상세 분석 논리
{hypothesis}

### 개별 분석 내역
"""     
        for res in results:
            hid = res.get("hotspot_id", "Unknown")
            ctype = res.get("connection_type", "Unknown")
            sres = res.get("specialist_result", {})
            if sres:
                desc = sres.get("visual_observation", sres.get("visual_description", ""))
                reasoning = sres.get("reasoning", "")
                full_report += f"\n**[Hotspot {hid}] ({ctype})**\n- 시각적 특징: {desc}\n- 판단 근거: {reasoning}\n"
        
        return {
            "verdict_report": full_report,
            "verdict_confidence": confidence,
            "verdict_result": {
                "conclusion": conclusion,
                "verdict": f"[{conclusion}] {hypothesis}",
                "confidence": confidence / 100.0,
                "visual_description": hypothesis,
                "debate_rounds": debate_iter,
                "debate_occurred": debate_iter > 0,
                "reasoning": hypothesis
            }
        }
    
    return verdict_finalize_node
