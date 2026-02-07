"""
Fact Check Router 노드
Fact Check 결과에 따라 다음 노드로 라우팅
"""
from typing import Literal
from src.states.arbiter_debate_state import ArbiterDebateState, ExpertName
from src.utils.logging_config import setup_logger

logger = setup_logger(__name__)

def fact_check_router_node(state: ArbiterDebateState) -> Literal["contact_debater", "deform_debater", "necking_debater", "moderator", "judge"]:
    """
    Fact Check 결과에 따라 라우팅
    
    Returns:
        다음 노드 이름
    """
    messages = state.get("debate_messages", [])
    if not messages:
        logger.debug("No messages found, routing to moderator")
        return "moderator"
    
    last_message = messages[-1]
    
    # Fact Checker 메시지 확인
    if last_message.get("speaker") != "fact_checker":
        logger.debug("Last message is not from fact_checker, routing to moderator")
        return "moderator"
    
    validated = last_message.get("validated", False)
    
    # 실격 체크 (3회 실패 시)
    failures = state.get("fact_check_failures", {})
    
    # 마지막 발언한 전문가 찾기
    speaker: ExpertName = None
    for msg in reversed(messages):
        if msg.get("speaker") in ["contact", "deform", "necking"]:
            speaker = msg.get("speaker")
            break
    
    if speaker:
        failure_count = failures.get(speaker, 0)
        if failure_count >= 3:
            # 3회 실패 시 조기 종료
            logger.warning(f"{speaker} expert disqualified: 3 fact check failures, routing to judge")
            return "judge"
    
    if validated:
        logger.info(f"{speaker} expert fact check passed, routing to moderator")
        return "moderator"  # 통과
    else:
        # Retry: 해당 전문가에게 다시 발언 기회 제공
        if speaker:
            logger.info(f"{speaker} expert fact check failed (failure count: {failures.get(speaker, 0)}), retrying")
            return f"{speaker}_debater"
        logger.warning("No speaker found for retry, routing to moderator")
        return "moderator"  # Fallback
