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
        
        # #region agent log
        import json
        import time
        from pathlib import Path
        log_path = Path(__file__).parent.parent.parent.parent / ".cursor" / "debug.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"id":"log_debater_before_call","timestamp":int(time.time()*1000),"location":"expert_debater_nodes.py:75","message":"before call_gemini_text","data":{"expert_name":expert_name,"stage":stage},"runId":"run1","hypothesisId":"D"})+"\n")
        except: pass
        # #endregion
        
        response_text, _ = call_gemini_text(
            prompt,
            step_name=f"{expert_name}_debater_{stage}",
            verbose=False,
            temperature=0.7
        )
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"id":"log_debater_after_call","timestamp":int(time.time()*1000),"location":"expert_debater_nodes.py:87","message":"after call_gemini_text","data":{"expert_name":expert_name,"response_length":len(response_text)},"runId":"run1","hypothesisId":"D"})+"\n")
        except: pass
        # #endregion
        
        logger.info(f"{expert_name} debater: LLM response received ({len(response_text)} chars)")
    except Exception as e:
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"id":"log_debater_call_error","timestamp":int(time.time()*1000),"location":"expert_debater_nodes.py:95","message":"call_gemini_text error","data":{"expert_name":expert_name,"error":str(e)},"runId":"run1","hypothesisId":"D"})+"\n")
        except: pass
        # #endregion
        
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
    log_path.parent.mkdir(parents=True, exist_ok=True)
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
        
        async def _run_with_cleanup():
            """asyncio.run() 내부에서 실행되며, 완료 전에 클라이언트 정리"""
            try:
                return await contact_debater_node(state)
            finally:
                # asyncio.run() 완료 전에 클라이언트의 비동기 리소스 정리하여 이벤트 루프 종료 후 에러 방지
                from src.tools.experts.expert_utils import client
                if client is not None and hasattr(client, 'aclose'):
                    try:
                        await client.aclose()
                    except Exception as e:
                        logger.debug(f"Client cleanup warning (ignored): {e}")
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, _run_with_cleanup())
            result = future.result()
    except RuntimeError:
        logger.debug("No event loop, using asyncio.run")
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"expert_debater_nodes.py:105","message":"no event loop, using asyncio.run","data":{},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        async def _run_with_cleanup():
            """asyncio.run() 내부에서 실행되며, 완료 전에 클라이언트 정리"""
            try:
                return await contact_debater_node(state)
            finally:
                # asyncio.run() 완료 전에 클라이언트의 비동기 리소스 정리하여 이벤트 루프 종료 후 에러 방지
                from src.tools.experts.expert_utils import client
                if client is not None and hasattr(client, 'aclose'):
                    try:
                        await client.aclose()
                    except Exception as e:
                        logger.debug(f"Client cleanup warning (ignored): {e}")
        
        # 이벤트 루프가 없으면 일반적으로 실행
        result = asyncio.run(_run_with_cleanup())
    
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
        
        async def _run_with_cleanup():
            """asyncio.run() 내부에서 실행되며, 완료 전에 클라이언트 정리"""
            try:
                return await deform_debater_node(state)
            finally:
                # asyncio.run() 완료 전에 클라이언트의 비동기 리소스 정리하여 이벤트 루프 종료 후 에러 방지
                from src.tools.experts.expert_utils import client
                if client is not None and hasattr(client, 'aclose'):
                    try:
                        await client.aclose()
                    except Exception as e:
                        logger.debug(f"Client cleanup warning (ignored): {e}")
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, _run_with_cleanup())
            result = future.result()
            logger.debug("Deform debater node sync exit")
            return result
    except RuntimeError:
        async def _run_with_cleanup():
            """asyncio.run() 내부에서 실행되며, 완료 전에 클라이언트 정리"""
            try:
                return await deform_debater_node(state)
            finally:
                # asyncio.run() 완료 전에 클라이언트의 비동기 리소스 정리하여 이벤트 루프 종료 후 에러 방지
                from src.tools.experts.expert_utils import client
                if client is not None and hasattr(client, 'aclose'):
                    try:
                        await client.aclose()
                    except Exception as e:
                        logger.debug(f"Client cleanup warning (ignored): {e}")
        
        result = asyncio.run(_run_with_cleanup())
        logger.debug("Deform debater node sync exit")
        return result

def necking_debater_node_sync(state: ArbiterDebateState) -> Dict[str, Any]:
    """Necking 전문가 Debater 노드 (동기 버전)"""
    logger.debug("Necking debater node sync entry")
    
    # #region agent log
    import json
    import time
    from pathlib import Path
    log_path = Path(__file__).parent.parent.parent.parent / ".cursor" / "debug.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"id":"log_necking_sync_entry","timestamp":int(time.time()*1000),"location":"expert_debater_nodes.py:174","message":"necking_debater_node_sync entry","data":{},"runId":"run1","hypothesisId":"A"})+"\n")
    except: pass
    # #endregion
    
    import asyncio
    try:
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"id":"log_necking_check_loop","timestamp":int(time.time()*1000),"location":"expert_debater_nodes.py:183","message":"checking for running event loop","data":{},"runId":"run1","hypothesisId":"B"})+"\n")
        except: pass
        # #endregion
        
        loop = asyncio.get_running_loop()
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"id":"log_necking_loop_found","timestamp":int(time.time()*1000),"location":"expert_debater_nodes.py:190","message":"event loop found, using ThreadPoolExecutor","data":{"loop_closed":loop.is_closed()},"runId":"run1","hypothesisId":"B"})+"\n")
        except: pass
        # #endregion
        
        logger.debug("Event loop already running, using ThreadPoolExecutor")
        import concurrent.futures
        
        async def _run_with_cleanup():
            """asyncio.run() 내부에서 실행되며, 완료 전에 클라이언트 정리"""
            try:
                return await necking_debater_node(state)
            finally:
                # asyncio.run() 완료 전에 클라이언트의 비동기 리소스 정리하여 이벤트 루프 종료 후 에러 방지
                # #region agent log
                try:
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"id":"log_necking_cleanup_start","timestamp":int(time.time()*1000),"location":"expert_debater_nodes.py:347","message":"starting client cleanup","data":{},"runId":"run1","hypothesisId":"C"})+"\n")
                except: pass
                # #endregion
                
                from src.tools.experts.expert_utils import client
                if client is not None and hasattr(client, 'aclose'):
                    try:
                        await client.aclose()
                        # #region agent log
                        try:
                            with open(log_path, "a", encoding="utf-8") as f:
                                f.write(json.dumps({"id":"log_necking_cleanup_success","timestamp":int(time.time()*1000),"location":"expert_debater_nodes.py:355","message":"client cleanup successful","data":{},"runId":"run1","hypothesisId":"C"})+"\n")
                        except: pass
                        # #endregion
                    except Exception as e:
                        # #region agent log
                        try:
                            with open(log_path, "a", encoding="utf-8") as f:
                                f.write(json.dumps({"id":"log_necking_cleanup_error","timestamp":int(time.time()*1000),"location":"expert_debater_nodes.py:361","message":"client cleanup error","data":{"error":str(e)},"runId":"run1","hypothesisId":"C"})+"\n")
                        except: pass
                        # #endregion
                        logger.debug(f"Client cleanup warning (ignored): {e}")
                else:
                    # #region agent log
                    try:
                        with open(log_path, "a", encoding="utf-8") as f:
                            f.write(json.dumps({"id":"log_necking_cleanup_skip","timestamp":int(time.time()*1000),"location":"expert_debater_nodes.py:368","message":"client cleanup skipped","data":{"client_is_none":client is None,"has_aclose":hasattr(client, 'aclose') if client is not None else False},"runId":"run1","hypothesisId":"C"})+"\n")
                    except: pass
                    # #endregion
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"id":"log_necking_before_run","timestamp":int(time.time()*1000),"location":"expert_debater_nodes.py:197","message":"before asyncio.run in ThreadPoolExecutor","data":{},"runId":"run1","hypothesisId":"B"})+"\n")
        except: pass
        # #endregion
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, _run_with_cleanup())
            result = future.result()
            
            # #region agent log
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"id":"log_necking_after_run","timestamp":int(time.time()*1000),"location":"expert_debater_nodes.py:204","message":"after asyncio.run completed","data":{},"runId":"run1","hypothesisId":"B"})+"\n")
            except: pass
            # #endregion
            
            logger.debug("Necking debater node sync exit")
            return result
    except RuntimeError as e:
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"id":"log_necking_no_loop","timestamp":int(time.time()*1000),"location":"expert_debater_nodes.py:212","message":"no running event loop, using asyncio.run directly","data":{"error":str(e)},"runId":"run1","hypothesisId":"C"})+"\n")
        except: pass
        # #endregion
        
        logger.debug("No event loop, using asyncio.run")
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"id":"log_necking_before_direct_run","timestamp":int(time.time()*1000),"location":"expert_debater_nodes.py:220","message":"before direct asyncio.run","data":{},"runId":"run1","hypothesisId":"C"})+"\n")
        except: pass
        # #endregion
        
        async def _run_with_cleanup():
            """asyncio.run() 내부에서 실행되며, 완료 전에 클라이언트 정리"""
            try:
                return await necking_debater_node(state)
            finally:
                # asyncio.run() 완료 전에 클라이언트의 비동기 리소스 정리하여 이벤트 루프 종료 후 에러 방지
                from src.tools.experts.expert_utils import client
                if client is not None and hasattr(client, 'aclose'):
                    try:
                        # 이벤트 루프가 아직 열려있는 동안 정리
                        await client.aclose()
                    except Exception as e:
                        # 정리 실패는 무시 (이미 닫혔거나 다른 문제일 수 있음)
                        logger.debug(f"Client cleanup warning (ignored): {e}")
        
        result = asyncio.run(_run_with_cleanup())
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"id":"log_necking_after_direct_run","timestamp":int(time.time()*1000),"location":"expert_debater_nodes.py:240","message":"after direct asyncio.run completed","data":{},"runId":"run1","hypothesisId":"C"})+"\n")
        except: pass
        # #endregion
        
        logger.debug("Necking debater node sync exit")
        return result
