"""
전문가 Debater 노드들
각 전문가가 자신의 의견을 제시하거나 다른 전문가의 의견에 반박
"""
from typing import Dict, Any
from src.states.arbiter_debate_state import ArbiterDebateState, ExpertName
from src.prompts.arbiter_debate_prompts import (
    build_opening_prompt,
    build_rebuttal_prompt,
    build_final_prompt
)
from src.tools.experts.expert_utils import call_gemini_text
from src.utils.logging_config import setup_logger

logger = setup_logger(__name__)

async def contact_debater_node(state: ArbiterDebateState) -> Dict[str, Any]:
    """Contact 전문가 Debater 노드"""
    return await _debater_node(state, "contact")

async def deform_debater_node(state: ArbiterDebateState) -> Dict[str, Any]:
    """Deform 전문가 Debater 노드"""
    return await _debater_node(state, "deform")

async def necking_debater_node(state: ArbiterDebateState) -> Dict[str, Any]:
    """Necking 전문가 Debater 노드"""
    return await _debater_node(state, "necking")

async def _debater_node(state: ArbiterDebateState, expert_name: ExpertName) -> Dict[str, Any]:
    """
    공통 Debater 노드 로직
    
    Args:
        state: ArbiterDebateState
        expert_name: 전문가 이름
        
    Returns:
        업데이트된 상태
    """
    stage = state.get("current_stage", "opening")
    round_num = state.get("current_round", 1)
    debate_messages = state.get("debate_messages", [])
    expert_opinions = state.get("expert_opinions", {})
    
    logger.info(f"{expert_name} debater: Round {round_num}, Stage {stage}")
    
    expert_opinion = expert_opinions.get(expert_name, {})
    if not expert_opinion:
        logger.error(f"{expert_name} expert opinion data not found")
        return {
            "errors": [f"{expert_name} 전문가의 의견 데이터가 없습니다."],
            "debate_messages": [{
                "speaker": expert_name,
                "content": f"{expert_name} 전문가: 데이터 없음",
                "validated": True,
                "stage": stage,
                "round_num": round_num
            }]
        }
    
    # 프롬프트 구성 (라운드별로 다름)
    if stage == "opening":
        prompt = build_opening_prompt(expert_opinion, expert_name)
        logger.debug(f"{expert_name} debater: Building opening prompt")
    elif stage == "rebuttal":
        prompt = build_rebuttal_prompt(expert_opinion, expert_name, debate_messages)
        logger.debug(f"{expert_name} debater: Building rebuttal prompt")
    else:  # final_argument
        prompt = build_final_prompt(expert_opinion, expert_name, debate_messages)
        logger.debug(f"{expert_name} debater: Building final argument prompt")
    
    # LLM 호출
    try:
        logger.debug(f"{expert_name} debater: Calling LLM")
        response_text, _ = call_gemini_text(
            prompt,
            step_name=f"{expert_name}_debater_{stage}",
            verbose=False,
            temperature=0.7
        )
        logger.info(f"{expert_name} debater: LLM response received ({len(response_text)} chars)")
    except Exception as e:
        logger.error(f"{expert_name} debater: LLM call failed - {e}", exc_info=True)
        response_text = f"{expert_name} 전문가: LLM 호출 실패 - {str(e)}"
    
    # 메시지 생성
    new_message = {
        "speaker": expert_name,
        "content": response_text,
        "validated": False,  # Fact Checker가 검증할 예정
        "stage": stage,
        "round_num": round_num
    }
    
    return {
        "debate_messages": [new_message],
        "current_speaker": expert_name
    }

# 동기 함수로 래핑 (LangGraph 호환성)
def contact_debater_node_sync(state: ArbiterDebateState) -> Dict[str, Any]:
    """Contact 전문가 Debater 노드 (동기 버전)"""
    logger.debug("Contact debater node sync entry")
    
    # #region agent log
    import json
    import time
    from pathlib import Path
    log_path = Path(__file__).parent.parent.parent.parent / ".cursor" / "debug.log"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"expert_debater_nodes.py:89","message":"contact_debater_node_sync entry","data":{},"timestamp":int(time.time()*1000)})+"\n")
    except: pass
    # #endregion
    
    import asyncio
    try:
        # 이미 실행 중인 이벤트 루프 확인
        loop = asyncio.get_running_loop()
        logger.debug("Event loop already running, using ThreadPoolExecutor")
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"expert_debater_nodes.py:97","message":"event loop already running","data":{},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        # 이벤트 루프가 실행 중이면 create_task 사용
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, contact_debater_node(state))
            result = future.result()
    except RuntimeError:
        logger.debug("No event loop, using asyncio.run")
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"expert_debater_nodes.py:105","message":"no event loop, using asyncio.run","data":{},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        # 이벤트 루프가 없으면 일반적으로 실행
        result = asyncio.run(contact_debater_node(state))
    
    logger.debug("Contact debater node sync exit")
    
    # #region agent log
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"expert_debater_nodes.py:111","message":"contact_debater_node_sync exit","data":{},"timestamp":int(time.time()*1000)})+"\n")
    except: pass
    # #endregion
    
    return result

def deform_debater_node_sync(state: ArbiterDebateState) -> Dict[str, Any]:
    """Deform 전문가 Debater 노드 (동기 버전)"""
    logger.debug("Deform debater node sync entry")
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, deform_debater_node(state))
            result = future.result()
            logger.debug("Deform debater node sync exit")
            return result
    except RuntimeError:
        result = asyncio.run(deform_debater_node(state))
        logger.debug("Deform debater node sync exit")
        return result

def necking_debater_node_sync(state: ArbiterDebateState) -> Dict[str, Any]:
    """Necking 전문가 Debater 노드 (동기 버전)"""
    logger.debug("Necking debater node sync entry")
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, necking_debater_node(state))
            result = future.result()
            logger.debug("Necking debater node sync exit")
            return result
    except RuntimeError:
        result = asyncio.run(necking_debater_node(state))
        logger.debug("Necking debater node sync exit")
        return result
