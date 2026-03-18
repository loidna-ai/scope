"""
Judge 노드
최종 판정 도출 (구조화된 출력 사용)
전문가 노드와 동일한 패턴 적용
"""
from typing import Dict, Any, Optional
import os
import asyncio
from google.genai import types

from src.states.arbiter_debate_state import ArbiterDebateState
from src.prompts.arbiter_debate_prompts import build_judge_prompt
from src.models.verdict_models import FinalVerdictResult
from src.utils.expert_config import get_thinking_config
from src.utils.genai_client import get_genai_client
from src.utils import async_retry_with_backoff
from src.utils.logging_config import setup_logger
import config

logger = setup_logger(__name__)

def generate_disqualification_verdict(
    disqualified: list,
    remaining_experts: Dict,
    messages: list
) -> str:
    """실격된 전문가가 있을 때의 판정"""
    disqualified_str = ", ".join([d.upper() for d in disqualified])
    remaining_str = ", ".join([k.upper() for k in remaining_experts.keys()])
    
    return f"""## 화재조사 최종 결론 (Arbiter Agent)

[조기 종료]
다음 전문가들이 Fact Check 실패로 인해 실격되었습니다: {disqualified_str}

[남은 전문가]
{remaining_str}

[판정]
실격된 전문가를 제외하고 남은 전문가들의 의견을 종합하여 판정합니다.
하지만 Fact Check 실패가 발생한 것은 증거의 신뢰성에 문제가 있음을 시사합니다.

[권고사항]
1. 실격된 전문가의 분석 결과를 재검토하세요
2. 추가 증거 수집을 권장합니다
3. 이미지 품질 및 분석 방법을 재확인하세요"""

def format_debate_summary(messages: list) -> str:
    """논쟁 메시지 요약"""
    summary_parts = []
    for msg in messages:
        speaker = msg.get("speaker", "")
        content = msg.get("content", "")
        stage = msg.get("stage", "")
        round_num = msg.get("round_num", 0)
        validated = msg.get("validated", True)
        
        if speaker in ["contact", "deform", "necking", "aging"]:
            validation_status = "✓" if validated else "✗"
            summary_parts.append(
                f"[Round {round_num}, {stage}] {speaker.upper()} 전문가 {validation_status}:\n{content[:200]}...\n"
            )
    
    return "\n".join(summary_parts) if summary_parts else "논쟁 기록이 없습니다."

async def judge_node(state: ArbiterDebateState) -> Dict[str, Any]:
    """
    Judge: 최종 판정
    
    Args:
        state: ArbiterDebateState
        
    Returns:
        최종 판정이 포함된 상태 업데이트
    """
    logger.info("Judge node: Starting final verdict generation")
    
    messages = state.get("debate_messages", [])
    expert_opinions = state.get("expert_opinions", {})
    expert_reports = state.get("expert_reports", [])
    consensus_reached = state.get("consensus_reached", False)
    
    logger.debug(f"Judge: {len(messages)} debate messages, {len(expert_opinions)} expert opinions")
    
    # 실격 확인
    failures = state.get("fact_check_failures", {})
    disqualified = [expert for expert, count in failures.items() if count >= 3]
    
    # ARBITER_CONFIDENCE_THRESHOLD: 전문가 평균 신뢰도가 임계값 미만이면 UNDETERMINED
    expert_confidence_scores = state.get("expert_confidence_scores", {})
    if expert_confidence_scores and not disqualified:
        avg_confidence = sum(expert_confidence_scores.values()) / len(expert_confidence_scores)
        threshold_pct = config.ARBITER_CONFIDENCE_THRESHOLD * 100
        if avg_confidence < threshold_pct:
            logger.info(
                f"Judge: Avg confidence {avg_confidence:.1f}% < threshold {threshold_pct}% → UNDETERMINED (skip LLM)"
            )
            verdict = f"""**최종 판정**: UNDETERMINED
**신뢰도**: {avg_confidence:.1f}% (Low)

**판정 근거:**
전문가 평균 신뢰도가 임계값({threshold_pct:.0f}%) 미만으로, 판단 불가 상태로 선언합니다."""
            return {
                "final_verdict": verdict,
                "final_verdict_structured": None,
                "debate_messages": [{
                    "speaker": "judge",
                    "content": verdict,
                    "validated": True,
                    "stage": "judgment",
                    "round_num": state.get("current_round", 1)
                }]
            }
    
    if disqualified:
        logger.warning(f"Judge: {len(disqualified)} experts disqualified: {disqualified}")
        # 실격된 전문가 제외하고 판정
        remaining_experts = {k: v for k, v in expert_opinions.items() if k not in disqualified}
        verdict = generate_disqualification_verdict(disqualified, remaining_experts, messages)
        logger.info("Judge: Generated disqualification verdict")
    else:
        # 정상적인 논쟁 종료 - 구조화된 출력으로 최종 판정 생성
        logger.info(f"Judge: Generating structured final verdict (consensus: {consensus_reached})")
        
        prompt = build_judge_prompt(
            expert_opinions,
            messages,
            expert_reports,
            consensus_reached
        )
        
        # 🔥 API 호출 함수 분리 (전문가 노드와 동일한 패턴)
        async def _call_judge_api(client, model_name, prompt, safety_settings):
            """Judge API 호출 (구조화된 출력)"""
            config_dict = {
                "temperature": 1.0,  # 공식 문서 권장사항: 1.0으로 통일
                "response_mime_type": "application/json",
                "response_json_schema": FinalVerdictResult.model_json_schema(),
                "safety_settings": safety_settings
            }
            # 모델 시리즈별 Thinking 설정 (Gemini 2.5: thinking_budget, Gemini 3: thinking_level)
            thinking_cfg = get_thinking_config(model_name, "high")
            if thinking_cfg:
                config_dict["thinking_config"] = thinking_cfg
            
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model_name,
                contents=prompt,
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
            model_name = os.environ.get("GEMINI_PRO_MODEL_NAME", config.GEMINI_PRO_MODEL_NAME)
            
            # 🔥 Centralized Retry Logic (전문가 노드와 동일)
            response = await async_retry_with_backoff(
                _call_judge_api,
                client=client,
                model_name=model_name,
                prompt=prompt,
                safety_settings=safety_settings_block_none,
                max_retries=5,
                context_name="Judge"
            )
            
            # [Debug/Safety] 응답 텍스트 확인 및 안전 파싱
            response_text = getattr(response, 'text', None)
            finish_reason = "Unknown"
            if hasattr(response, 'candidates') and response.candidates:
                finish_reason = getattr(response.candidates[0], 'finish_reason', "Unknown")
            
            logger.debug(f"Judge: Finish reason: {finish_reason}")
            
            if not response_text:
                raise ValueError(f"Gemini API 응답 텍스트가 비어있습니다. (Finish Reason: {finish_reason})")
            
            # 🔥 구조화된 데이터 파싱 (전문가 노드와 동일: model_validate_json 사용)
            verdict_structured = FinalVerdictResult.model_validate_json(response_text)
            
            # 하위 호환성을 위한 텍스트 생성
            verdict = verdict_structured.to_text_summary()
            
            logger.info(f"Judge: Structured final verdict generated (confidence: {verdict_structured.confidence_score}%)")
            
            return {
                # [구조화 데이터] - 전문가 노드의 "analyst_hypothesis"와 동일한 패턴
                "final_verdict_structured": verdict_structured,
                
                # [하위 호환성] - 전문가 노드의 "current_hypothesis"와 동일한 패턴
                "final_verdict": verdict,
                
                "debate_messages": [{
                    "speaker": "judge",
                    "content": verdict,
                    "validated": True,
                    "stage": "judgment",
                    "round_num": state.get("current_round", 1)
                }]
            }
            
        except Exception as e:
            # Fallback: 간단한 판정 생성
            logger.error(f"Judge: LLM call failed - {e}", exc_info=True)
            verdict = f"""## 화재조사 최종 결론 (Arbiter Agent)

[오류]
LLM 호출 실패: {str(e)}

[전문가 의견 요약]
{format_debate_summary(messages)}

[임시 판정]
각 전문가의 의견을 종합하여 판정하세요."""
            logger.warning("Judge: Using fallback verdict")
            
            return {
                "final_verdict": verdict,
                "final_verdict_structured": None,  # 구조화 데이터 없음
                "debate_messages": [{
                    "speaker": "judge",
                    "content": verdict,
                    "validated": False,
                    "stage": "judgment",
                    "round_num": state.get("current_round", 1)
                }]
            }
    
    # 실격 케이스는 이미 반환됨 (위의 if disqualified 블록에서)
    # 이 코드는 실행되지 않지만 하위 호환성을 위해 유지
    logger.info("Judge node: Final verdict completed")
    
    return {
        "final_verdict": verdict,
        "final_verdict_structured": None,  # 실격 케이스는 구조화 데이터 없음
        "debate_messages": [{
            "speaker": "judge",
            "content": verdict,
            "validated": True,
            "stage": "judgment",
            "round_num": state.get("current_round", 1)
        }]
    }



