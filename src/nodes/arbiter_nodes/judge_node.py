"""
Judge 노드
최종 판정 도출
"""
from typing import Dict, Any
from src.states.arbiter_debate_state import ArbiterDebateState
from src.prompts.arbiter_debate_prompts import build_judge_prompt
from src.tools.experts.expert_utils import call_gemini_text
from src.utils.logging_config import setup_logger

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
        
        if speaker in ["contact", "deform", "necking"]:
            validation_status = "✓" if validated else "✗"
            summary_parts.append(
                f"[Round {round_num}, {stage}] {speaker.upper()} 전문가 {validation_status}:\n{content[:200]}...\n"
            )
    
    return "\n".join(summary_parts) if summary_parts else "논쟁 기록이 없습니다."

def judge_node(state: ArbiterDebateState) -> Dict[str, Any]:
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
    
    if disqualified:
        logger.warning(f"Judge: {len(disqualified)} experts disqualified: {disqualified}")
        # 실격된 전문가 제외하고 판정
        remaining_experts = {k: v for k, v in expert_opinions.items() if k not in disqualified}
        verdict = generate_disqualification_verdict(disqualified, remaining_experts, messages)
        logger.info("Judge: Generated disqualification verdict")
    else:
        # 정상적인 논쟁 종료 - LLM으로 최종 판정 생성
        logger.info(f"Judge: Generating normal verdict (consensus: {consensus_reached})")
        try:
            prompt = build_judge_prompt(
                expert_opinions,
                messages,
                expert_reports,
                consensus_reached
            )
            
            logger.debug("Judge: Calling LLM for final verdict")
            response_text, _ = call_gemini_text(
                prompt,
                step_name="arbiter_judge",
                verbose=False,
                temperature=0.3
            )
            verdict = response_text
            logger.info(f"Judge: Final verdict generated ({len(verdict)} chars)")
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
    
    # Judge 메시지 생성
    judge_message = {
        "speaker": "judge",
        "content": verdict,
        "validated": True,
        "stage": "judgment",
        "round_num": state.get("current_round", 1)
    }
    
    logger.info("Judge node: Final verdict completed")
    
    return {
        "final_verdict": verdict,
        "debate_messages": [judge_message]
    }
