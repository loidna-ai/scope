"""
Debate Moderator 노드
턴 관리 및 라운드 진행
"""
from typing import Dict, Any, Literal, List
from src.states.arbiter_debate_state import ArbiterDebateState, ExpertName, DebateStage
from src.utils.logging_config import setup_logger

logger = setup_logger(__name__)

def check_consensus(messages: List[Dict]) -> bool:
    """
    논쟁 메시지에서 합의 여부 확인
    
    Args:
        messages: 논쟁 메시지 리스트
        
    Returns:
        합의 여부
    """
    if not messages:
        return False
    
    # 최근 메시지들에서 합의 키워드 확인
    consensus_keywords = ["합의", "동의", "일치", "consensus", "agree", "동의합니다"]
    
    recent_messages = messages[-6:]  # 최근 6개 메시지 확인
    for msg in recent_messages:
        content = msg.get("content", "").lower()
        if any(keyword in content for keyword in consensus_keywords):
            return True
    
    return False

def determine_next_speaker(state: ArbiterDebateState) -> ExpertName:
    """
    다음 발언자 결정 (라운드 로빈)
    
    Args:
        state: ArbiterDebateState
        
    Returns:
        다음 발언자 이름
    """
    stage = state.get("current_stage", "opening")
    messages = state.get("debate_messages", [])
    current_round = state.get("current_round", 1)
    
    # 실제로 사용 가능한 전문가 확인
    expert_opinions = state.get("expert_opinions", {})
    available_experts = list(expert_opinions.keys())
    
    if not available_experts:
        return "contact"  # Fallback
    
    # 현재 라운드에서 발언한 전문가 확인
    speakers_this_round = [
        msg.get("speaker") for msg in messages 
        if msg.get("round_num") == current_round 
        and msg.get("speaker") in available_experts
    ]
    
    # 사용 가능한 전문가만으로 라운드 로빈 순서 결정
    order = available_experts
    
    if not speakers_this_round:
        return order[0]
    
    # 마지막 발언자 확인
    last_speaker = speakers_this_round[-1]
    try:
        idx = order.index(last_speaker)
        return order[(idx + 1) % len(order)]
    except ValueError:
        return order[0]

def debate_moderator_node(state: ArbiterDebateState) -> Dict[str, Any]:
    """
    Debate Moderator: 턴 관리 및 라운드 진행
    
    Args:
        state: ArbiterDebateState
        
    Returns:
        업데이트된 상태
    """
    current_stage = state.get("current_stage", "opening")
    current_round = state.get("current_round", 1)
    messages = state.get("debate_messages", [])
    expert_opinions = state.get("expert_opinions", {})
    
    logger.info(f"Moderator: Round {current_round}, Stage {current_stage}, {len(messages)} messages")
    logger.debug(f"Moderator: Available experts: {list(expert_opinions.keys())}")
    
    # 합의 확인 (Round 2 이상에서만)
    if current_round >= 2:
        consensus = check_consensus(messages)
        if consensus:
            logger.info("Moderator: Consensus reached, moving to judgment stage")
            moderator_message = {
                "speaker": "moderator",
                "content": f"합의가 도달되었습니다. 최종 판정으로 진행합니다.",
                "validated": True,
                "stage": "judgment",
                "round_num": current_round
            }
            return {
                "debate_messages": [moderator_message],
                "consensus_reached": True,
                "current_stage": "judgment",
                "current_speaker": None
            }
    
    # 다음 단계 결정
    next_stage: DebateStage = current_stage
    next_round = current_round
    next_speaker: ExpertName = None
    
    if current_stage == "opening":
        # 모든 전문가가 의견 제시했는지 확인
        speakers = [
            msg.get("speaker") for msg in messages 
            if msg.get("speaker") in ["contact", "deform", "necking", "aging"]
            and msg.get("stage") == "opening"
        ]
        unique_speakers = set(speakers)
        
        # 실제로 사용 가능한 전문가 수 확인 (expert_opinions에서)
        expert_opinions = state.get("expert_opinions", {})
        available_experts = set(expert_opinions.keys())
        
        # 사용 가능한 모든 전문가가 발언했는지 확인
        if len(unique_speakers) >= len(available_experts) and len(available_experts) > 0:
            next_stage = "rebuttal"
            next_round = current_round + 1
            # 첫 번째 발언자는 사용 가능한 전문가 중 첫 번째
            next_speaker = list(available_experts)[0] if available_experts else "contact"
        else:
            # 아직 발언하지 않은 전문가 결정
            next_speaker = determine_next_speaker(state)
    
    elif current_stage == "rebuttal":
        # 반박 라운드 완료 확인
        speakers_this_round = [
            msg.get("speaker") for msg in messages 
            if msg.get("round_num") == current_round
            and msg.get("speaker") in ["contact", "deform", "necking", "aging"]
        ]
        unique_speakers_round = set(speakers_this_round)
        
        # 실제로 사용 가능한 전문가 수 확인
        expert_opinions = state.get("expert_opinions", {})
        available_experts = set(expert_opinions.keys())
        
        # 사용 가능한 모든 전문가가 반박 완료했는지 확인
        if len(unique_speakers_round) >= len(available_experts) and len(available_experts) > 0:
            next_stage = "final_argument"
            next_round = current_round + 1
            next_speaker = list(available_experts)[0] if available_experts else "contact"
        else:
            # 아직 발언하지 않은 전문가 결정
            next_speaker = determine_next_speaker(state)
    
    elif current_stage == "final_argument":
        # 최종 라운드 완료 확인
        speakers_this_round = [
            msg.get("speaker") for msg in messages 
            if msg.get("round_num") == current_round
            and msg.get("speaker") in ["contact", "deform", "necking", "aging"]
        ]
        unique_speakers_round = set(speakers_this_round)
        
        # 실제로 사용 가능한 전문가 수 확인
        expert_opinions = state.get("expert_opinions", {})
        available_experts = set(expert_opinions.keys())
        
        # 사용 가능한 모든 전문가가 최종 의견 제시 완료했는지 확인
        if len(unique_speakers_round) >= len(available_experts) and len(available_experts) > 0:
            next_stage = "judgment"
            next_speaker = None
        else:
            # 아직 발언하지 않은 전문가 결정
            next_speaker = determine_next_speaker(state)
    
    # Moderator 메시지 생성
    if next_stage == "judgment":
        moderator_content = f"모든 라운드가 완료되었습니다. 최종 판정으로 진행합니다."
        logger.info("Moderator: All rounds completed, moving to judgment")
    else:
        moderator_content = f"Round {next_round}, Stage: {next_stage}, Next Speaker: {next_speaker}"
        logger.info(f"Moderator: Next speaker: {next_speaker}, Stage: {next_stage}, Round: {next_round}")
    
    moderator_message = {
        "speaker": "moderator",
        "content": moderator_content,
        "validated": True,
        "stage": current_stage,
        "round_num": current_round
    }
    
    result = {
        "debate_messages": [moderator_message],
        "current_stage": next_stage,
        "current_round": next_round,
        "current_speaker": next_speaker
    }
    
    return result