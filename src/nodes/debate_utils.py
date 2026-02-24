"""
공통 Debate 노드 베이스
Analyst, Critic, Finalize 노드의 공통 로직을 제공합니다.
"""
from typing import Dict, Any, Optional, Callable, List
from src.utils.logging_config import setup_logger
from src.utils.expert_config import MAX_DEBATE_ITERATIONS
from src.utils.expert_report_utils import format_report_summary, extract_critiqued_hotspots
from src.models.debate_models import AnalystHypothesis, CritiqueResult, create_no_objection

logger = setup_logger(__name__)


def extract_analyst_result_data(analyst_result: Any) -> tuple[str, int]:
    """
    Analyst 결과에서 conclusion과 probability 추출 (공통 로직)
    
    Args:
        analyst_result: AnalystHypothesis Pydantic 객체 또는 dict
    
    Returns:
        (conclusion, confidence) 튜플
    """
    try:
        # Pydantic 객체에서 데이터 추출
        if hasattr(analyst_result, "get_hypothesis_data"):
            data = analyst_result.get_hypothesis_data()
            return data.conclusion, data.probability
        elif isinstance(analyst_result, dict):
            # 딕셔너리 처리
            if analyst_result.get("revised_hypothesis"):
                nested = analyst_result["revised_hypothesis"]
                return nested.get("conclusion", "판독 불가"), nested.get("probability", 0)
            else:
                return analyst_result.get("conclusion", "판독 불가"), analyst_result.get("probability", 0)
        else:
            # 객체 속성 접근
            if getattr(analyst_result, "revised_hypothesis", None):
                nested = analyst_result.revised_hypothesis
                return getattr(nested, "conclusion", "판독 불가"), getattr(nested, "probability", 0)
            else:
                return getattr(analyst_result, "conclusion", "판독 불가"), getattr(analyst_result, "probability", 0)
    except Exception as e:
        logger.critical(f"Analyst result extraction failed: {e}", exc_info=True)
        return "판독 불가", 0


def prepare_focused_hotspots(
    results: List[Dict[str, Any]],
    critique_result: Optional[Any],
    critique: str
) -> List[Dict[str, Any]]:
    """
    Critic의 지적에 따라 집중할 Hotspot들을 준비 (공통 로직)
    
    Args:
        results: 전체 분석 결과 리스트
        critique_result: CritiqueResult Pydantic 객체 (None 가능)
        critique: Critic 비평 텍스트 (fallback용)
    
    Returns:
        집중할 Hotspot 리스트
    """
    if critique_result is not None and hasattr(critique_result, 'hotspots_mentioned') and critique_result.hotspots_mentioned:
        # Pydantic 객체에서 명시적 Hotspot ID 추출
        mentioned_ids = critique_result.hotspots_mentioned
        focused_hotspots = [r for r in results if r.get("id") in mentioned_ids]
        logger.info(f"Analyst: Critic specified hotspots: {mentioned_ids}")
        return focused_hotspots
    else:
        # Fallback: Legacy 정규표현식 추출
        focused_hotspots = extract_critiqued_hotspots(critique, results)
        logger.warning(f"Analyst: Fallback to regex for hotspot extraction")
        return focused_hotspots


def create_final_report(
    expert_type: str,
    conclusion: str,
    confidence: int,
    hypothesis: str,
    debate_iter: int,
    debate_messages: List[str],
    is_consensus: bool
) -> str:
    """
    최종 보고서 생성 (공통 로직)
    
    Args:
        expert_type: 전문가 타입 ("necking", "deform", "contact")
        conclusion: 최종 결론
        confidence: 신뢰도
        hypothesis: 최종 가설
        debate_iter: Debate 반복 횟수
        debate_messages: Debate 메시지 리스트
        is_consensus: 합의 여부
    
    Returns:
        최종 보고서 텍스트
    """
    expert_names = {
        "necking": "Necking",
        "deform": "Deform",
        "contact": "Contact",
        "aging": "Aging",
    }
    expert_name = expert_names.get(expert_type, "Expert")
    
    debate_log = "\n\n".join(debate_messages)
    
    final_report = f"""
[{expert_name} 전문가 최종 판정 - Analyst-Critic 토론]

## 결론: {conclusion} ({confidence}%)

## 최종 합의 가설
{hypothesis}

## 종합 소견
Analyst-Critic {debate_iter}턴 토론 후 합의 도출.
{'합의된 판정' if is_consensus else '제한적 합의'}

## 토론 기록
{debate_log}
"""
    return final_report


def extract_finalize_conclusion(
    state: Dict[str, Any],
    expert_type: str
) -> tuple[str, int, str]:
    """
    Finalize 노드에서 최종 결론 추출 (공통 로직)
    
    Args:
        state: Expert State 딕셔너리
        expert_type: 전문가 타입
    
    Returns:
        (conclusion, confidence, hypothesis) 튜플
    """
    conclusion = "판독 불가"
    confidence = 0
    hypothesis = state.get("current_hypothesis", "")
    
    # 1. Supervisor Fast Path 결론 확인 (우선 순위 1)
    final_verdict = state.get("final_verdict")
    
    if final_verdict:
        conclusion = final_verdict.get("conclusion", conclusion)
        conf_val = final_verdict.get("confidence", 0)
        # 0.90 -> 90% 변환
        confidence = int(conf_val * 100 if conf_val <= 1.0 else conf_val)
        hypothesis = final_verdict.get("reasoning", hypothesis)
        logger.info(f"Finalize: Adopted Supervisor Fast Path verdict: {conclusion} ({confidence}%)")
    
    # 2. Analyst Debate 결론 확인 (우선 순위 2)
    else:
        analyst_result = state.get("analyst_hypothesis")
        
        if analyst_result:
            try:
                conclusion, confidence = extract_analyst_result_data(analyst_result)
                logger.info(f"Finalize: Adopted Analyst verdict: {conclusion} ({confidence}%)")
            except Exception as e:
                logger.critical(f"Finalize: Pydantic extraction failed: {e}", exc_info=True)
                logger.error(f"Finalize: No results from Supervisor/Analyst. Defaulting to Indeterminate.")
                conclusion = "판독 불가"
                confidence = 0
        else:
            logger.critical(f"Finalize: Missing both final_verdict and analyst_result!")
            logger.critical(f"Finalize: Invalid workflow state.")
            conclusion = "판독 불가"
            confidence = 0
    
    return conclusion, confidence, hypothesis
