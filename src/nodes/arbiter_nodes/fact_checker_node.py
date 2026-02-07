"""
Fact Checker 노드
전문가의 증거 일관성을 LLM 기반으로 검증 (Factcheck-GPT + AXCEL 방식)
"""
from typing import Dict, Any, List
from src.states.arbiter_debate_state import ArbiterDebateState, ExpertName
from src.prompts.arbiter_debate_prompts import build_fact_check_prompt
from src.tools.experts.expert_utils import call_gemini_text
from src.utils.logging_config import setup_logger

logger = setup_logger(__name__)

def validate_evidence_consistency_llm(
    message: str,
    opinion: Dict,
    evidence: List[Dict]
) -> tuple[bool, Dict[str, Any]]:
    """
    LLM 기반 증거 일관성 검증 (Factcheck-GPT + AXCEL 방식)
    
    Args:
        message: 전문가가 제시한 메시지
        opinion: 전문가의 의견 딕셔너리
        evidence: 전문가의 증거 리스트
        
    Returns:
        tuple: (is_consistent: bool, verification_result: Dict)
        
    Raises:
        Exception: LLM 호출 실패 시 예외 발생 (fallback 없음)
    """
    # 프롬프트 구성
    prompt = build_fact_check_prompt(message, opinion, evidence)
    
    # LLM 호출 (낮은 temperature로 일관성 확보)
    response_text, _ = call_gemini_text(
        prompt,
        step_name="fact_checker_llm",
        verbose=False,
        temperature=0.3  # 낮은 temperature로 일관된 검증
    )
    
    # JSON 파싱
    import json
    import re
    
    # JSON 추출 (마크다운 코드 블록 제거)
    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
    if json_match:
        verification_result = json.loads(json_match.group())
    else:
        # Fallback: 전체 텍스트를 JSON으로 파싱 시도
        verification_result = json.loads(response_text)
    
    is_consistent = verification_result.get("is_consistent", False)
    verification_result["verification_method"] = "llm"
    
    return is_consistent, verification_result

def fact_checker_node(state: ArbiterDebateState) -> Dict[str, Any]:
    """
    Fact Checker: 전문가의 증거 일관성 검증 (LLM 기반만 사용)
    
    Args:
        state: ArbiterDebateState
        
    Returns:
        업데이트된 상태
    """
    messages = state.get("debate_messages", [])
    if not messages:
        logger.warning("No messages found in state")
        return {}
    
    last_message = messages[-1]
    speaker = last_message.get("speaker", "")
    
    # Fact Checker, Moderator, Judge 메시지는 검증 불필요
    if speaker not in ["contact", "deform", "necking"]:
        logger.debug(f"Fact check skipped for system message from {speaker}")
        fact_check_message = {
            "speaker": "fact_checker",
            "content": "검증 불필요 (시스템 메시지)",
            "validated": True,
            "stage": state.get("current_stage", "opening"),
            "round_num": state.get("current_round", 1)
        }
        return {"debate_messages": [fact_check_message]}
    
    logger.info(f"Fact checking {speaker} expert's statement")
    
    # 전문가의 의견과 증거 일관성 검증
    expert_opinions = state.get("expert_opinions", {})
    expert_evidence = state.get("expert_evidence", {})
    
    expert_opinion = expert_opinions.get(speaker, {})
    expert_evidence_list = expert_evidence.get(speaker, [])
    message_content = last_message.get("content", "")
    
    logger.debug(f"Validating {speaker} expert: {len(expert_evidence_list)} evidence items")
    
    # LLM 기반 검증 실행
    try:
        is_consistent, verification_result = validate_evidence_consistency_llm(
            message_content,
            expert_opinion,
            expert_evidence_list
        )
        logger.info(f"{speaker} expert fact check completed: {'PASSED' if is_consistent else 'FAILED'}")
    except Exception as e:
        # LLM 호출 실패 시 에러 처리
        logger.error(f"Fact check LLM call failed for {speaker}: {e}", exc_info=True)
        fact_check_message = {
            "speaker": "fact_checker",
            "content": f"증거 일관성 검증: 오류 발생\n- LLM 호출 실패: {str(e)}",
            "validated": False,
            "stage": state.get("current_stage", "opening"),
            "round_num": state.get("current_round", 1)
        }
        failures = state.get("fact_check_failures", {}).copy()
        failures[speaker] = failures.get(speaker, 0) + 1
        logger.warning(f"{speaker} expert fact check failure count: {failures[speaker]}")
        
        return {
            "debate_messages": [fact_check_message],
            "fact_check_failures": failures
        }
    
    # 검증 결과를 상세하게 기록
    consistency_score = verification_result.get("consistency_score", 0)
    verification_method = verification_result.get("verification_method", "llm")
    overall_reasoning = verification_result.get("overall_reasoning", "")
    issues_found = verification_result.get("issues_found", [])
    
    logger.debug(f"{speaker} expert consistency score: {consistency_score}/100")
    if issues_found:
        logger.debug(f"{speaker} expert issues found: {len(issues_found)}")
    
    # Fact Check 메시지 생성 (상세 정보 포함)
    if is_consistent:
        fact_check_content = f"""증거 일관성 검증: 통과
- 검증 방법: {verification_method}
- 일관성 점수: {consistency_score}/100
- 검증 결과: {overall_reasoning}"""
    else:
        issues_text = "\n".join([f"  - {issue}" for issue in issues_found]) if issues_found else "  - 일관성 문제 발견"
        fact_check_content = f"""증거 일관성 검증: 실패
- 검증 방법: {verification_method}
- 일관성 점수: {consistency_score}/100
- 발견된 문제:
{issues_text}
- 검증 결과: {overall_reasoning}"""
    
    fact_check_message = {
        "speaker": "fact_checker",
        "content": fact_check_content,
        "validated": is_consistent,
        "stage": state.get("current_stage", "opening"),
        "round_num": state.get("current_round", 1)
    }
    
    # 실패 횟수 업데이트
    failures = state.get("fact_check_failures", {}).copy()
    if not is_consistent:
        failures[speaker] = failures.get(speaker, 0) + 1
        logger.warning(f"{speaker} expert fact check failed (failure count: {failures[speaker]}/3)")
    
    return {
        "debate_messages": [fact_check_message],
        "fact_check_failures": failures
    }
