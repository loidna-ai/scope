"""
전문가 Debater 노드들
각 전문가가 자신의 의견을 제시하거나 다른 전문가의 의견에 반박
"""
import asyncio
import concurrent.futures
from typing import Dict, Any

from src.states.arbiter_debate_state import ArbiterDebateState, ExpertName
from src.prompts.arbiter_debate_prompts import (
    build_opening_prompt,
    build_rebuttal_prompt,
    build_final_prompt
)
from src.tools.experts.expert_utils import call_gemini_text
from src.utils.logging_config import setup_logger
from src.utils.retry_utils import async_retry_with_backoff

logger = setup_logger(__name__)


# ── 비동기 Debater 노드 ────────────────────────────────────────────────────────

async def contact_debater_node(state: ArbiterDebateState) -> Dict[str, Any]:
    """Contact 전문가 Debater 노드"""
    return await _debater_node(state, "contact")


async def deform_debater_node(state: ArbiterDebateState) -> Dict[str, Any]:
    """Deform 전문가 Debater 노드"""
    return await _debater_node(state, "deform")


async def necking_debater_node(state: ArbiterDebateState) -> Dict[str, Any]:
    """Necking 전문가 Debater 노드"""
    return await _debater_node(state, "necking")

async def aging_debater_node(state: ArbiterDebateState) -> Dict[str, Any]:
    """Aging 전문가 Debater 노드"""
    return await _debater_node(state, "aging")


async def _debater_node(
    state: ArbiterDebateState, expert_name: ExpertName
) -> Dict[str, Any]:
    """공통 Debater 노드 로직."""
    stage         = state.get("current_stage", "opening")
    round_num     = state.get("current_round", 1)
    debate_msgs   = state.get("debate_messages", [])
    expert_opinion = state.get("expert_opinions", {}).get(expert_name, {})

    logger.info(f"{expert_name} debater: Round {round_num}, Stage {stage}")

    if not expert_opinion:
        logger.error(f"{expert_name} expert opinion data not found")
        return {
            "errors": [f"{expert_name} 전문가의 의견 데이터가 없습니다."],
            "debate_messages": [{
                "speaker": expert_name,
                "content": f"{expert_name} 전문가: 데이터 없음",
                "validated": True,
                "stage": stage,
                "round_num": round_num,
            }],
        }

    # 라운드별 프롬프트 선택
    if stage == "opening":
        prompt = build_opening_prompt(expert_opinion, expert_name)
    elif stage == "rebuttal":
        prompt = build_rebuttal_prompt(expert_opinion, expert_name, debate_msgs)
    else:  # final_argument
        prompt = build_final_prompt(expert_opinion, expert_name, debate_msgs)

    logger.debug(f"{expert_name} debater: Building {stage} prompt")

    # LLM 호출 (async_retry_with_backoff: 429/503 대기 + acquire_api_slot 내장)
    try:
        logger.debug(f"{expert_name} debater: Calling LLM")
        async def _call_debater():
            return await asyncio.to_thread(
                call_gemini_text,
                prompt,
                f"{expert_name}_debater_{stage}",
                False,  # verbose
                0.7,    # temperature
            )
        response_text, _ = await async_retry_with_backoff(
            _call_debater,
            context_name=f"{expert_name}_debater_{stage}",
        )
        logger.info(
            f"{expert_name} debater: LLM response received ({len(response_text)} chars)"
        )
    except Exception as e:
        logger.error(f"{expert_name} debater: LLM call failed - {e}", exc_info=True)
        response_text = f"{expert_name} 전문가: LLM 호출 실패 - {str(e)}"

    return {
        "debate_messages": [{
            "speaker": expert_name,
            "content": response_text,
            "validated": False,
            "stage": stage,
            "round_num": round_num,
        }],
        "current_speaker": expert_name,
    }


# ── 공통 비동기→동기 변환 헬퍼 (#9) ────────────────────────────────────────────

async def _with_client_cleanup(coro):
    """코루틴 실행 후 Gemini 클라이언트의 비동기 리소스를 정리합니다.

    asyncio.run() 이벤트 루프 종료 전에 aclose()를 호출하여
    'Event loop is closed' 경고를 방지합니다.
    """
    try:
        return await coro
    finally:
        from src.tools.experts.expert_utils import client
        if client is not None and hasattr(client, 'aclose'):
            try:
                await client.aclose()
            except Exception as e:
                logger.debug(f"Client cleanup warning (ignored): {e}")



