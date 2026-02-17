"""
Arbiter Agent 모듈 (Legacy - 논쟁 시스템으로 교체됨)
증거 통합 및 상충 해결을 통한 최종 결론 도출

[주의] 이 파일은 논쟁 시스템(arbiter_expert_graph.py)으로 교체되었습니다.
기존 로직 체인 방식의 참고용으로 보관됩니다.

[중요] 이 파일은 더 이상 사용되지 않으며, 참고용으로만 보관됩니다.
실제 실행 코드에서는 arbiter_expert_graph.py의 arbiter_expert_wrapper_node가 사용됩니다.
"""
from typing import Dict, Any, List
# from src.prompts.arbiter_report_prompts import build_arbiter_report_prompt  # [Deleted] Legacy 파일 삭제됨
from src.state import InvestigationState
from src.tools.experts.arbiter_utils import (
    extract_visual_features,
    calculate_primary_secondary_score,
    apply_conflict_resolution,
    apply_evidence_hierarchy,
    determine_dominant_expert
)
import config
from src.tools.experts.expert_utils import client, MODEL_NAME, generation_config
import re

# 판단 불가 상태 상수
UNDETERMINED_VERDICT = "UNDETERMINED"

# 1차/2차 판정 점수 차이 임계값 (점수 차이가 이 값 미만이면 판단 불가)
PRIMARY_SECONDARY_SCORE_DIFF_THRESHOLD = 10

def _mask_python_errors(text: str) -> str:
    """
    텍스트 내의 파이썬 에러 메시지를 사용자 친화적인 메시지로 마스킹합니다.
    """
    if "Traceback (most recent call last)" in text or "Error:" in text:
        # 에러 패턴 감지 시 대체
        return "분석 불가 (시스템 데이터 부족 또는 처리 오류)"
    return text

def _generate_undetermined_report(
    confidence_scores: Dict[str, float],
    evidence: Dict[str, List[Dict]],
    reports: List[str],
    weighted_scores: Dict[str, float] = None,
    primary_secondary_summary: str = None,
    conflict_summary: str = None,
    reason_code: str = "LOW_CONFIDENCE"
) -> str:
    """
    판단 불가(Undetermined) 리포트 생성 헬퍼 함수
    """
    avg_conf = sum(confidence_scores.values()) / len(confidence_scores) if confidence_scores else 0
    threshold = config.ARBITER_CONFIDENCE_THRESHOLD
    
    # 낮은 신뢰도 전문가 식별
    low_conf_experts = [
        name for name, score in confidence_scores.items() 
        if score < threshold * 100
    ]
    
    # 신뢰도 요약 생성
    confidence_summary = "\n".join([
        f"- {expert_name}: {score:.1f}%"
        for expert_name, score in confidence_scores.items()
    ])
    
    # 증거 요약 생성
    evidence_summary_parts = []
    for expert_name, evidence_list in evidence.items():
        if evidence_list:
            evidence_summary_parts.append(f"\n[{expert_name} 전문가 증거]")
            for ev in evidence_list:
                evidence_summary_parts.append(
                    f"  - Step {ev.get('step', 'N/A')}: {ev.get('evidence', 'N/A')}"
                )
    
    evidence_summary = "\n".join(evidence_summary_parts) if evidence_summary_parts else "증거 없음"
    
    # 판단 불가 사유 메시지
    reasons = {
        "LOW_CONFIDENCE": f"전문가 신뢰도 평균({avg_conf:.1f}%)이 임계값({threshold*100:.0f}%) 미만입니다.",
        "INSUFFICIENT_EVIDENCE": "핵심 증거가 부족하여 결론을 내릴 수 없습니다.",
        "AMBIGUOUS_VERDICT": "1차/2차 단락흔 판정 점수 차이가 미미하여 구분이 불가능합니다."
    }
    
    reason_text = reasons.get(reason_code, reason_code)
    
    # 리포트 텍스트 결합 (에러 마스킹 적용)
    clean_reports = [_mask_python_errors(r) for r in reports]
    reports_text = "\n\n".join(clean_reports) if clean_reports else "전문가 리포트 없음"
    
    # 리포트 생성 (새로운 포맷 적용)
    report = f"""# 🔥 AI 화재증거물 정밀 분석 보고서 (판단 보류)

| 분석 결과 | **판단 보류 (UNDETERMINED)** |
| --- | --- |
| **사유** | {reason_text} |
| **평균 신뢰도** | {avg_conf:.1f}% (기준: {threshold*100:.0f}%) |

## 1. 판단 보류 상세 사유
- {reason_text}
- 참여 전문가 수: {len(confidence_scores)}명
{f"- 신뢰도 저조 전문가: {', '.join(low_conf_experts)}" if low_conf_experts else ""}

## 2. 전문가별 분석 요약
{reports_text}

## 3. 상세 증거 분석
{evidence_summary}

## 4. 추가 조사 권고 사항
1. **이미지 품질 보완**: 더 높은 해상도 및 다양한 각도의 이미지 확보 필요.
2. **물리적 증거 보강**: 현장에서 물리적 시료 수집 및 실험실 정밀 분석 권장.
3. **전문가 재분석**: 신뢰도가 낮은 분야에 대한 심층 재검토 필요.

---
*(시스템 로그: {reason_code})*
"""
    return report

def node_arbiter(state: InvestigationState) -> Dict[str, Any]:
    """
    Arbiter Agent 노드
    1차/2차 단락흔 판정 및 상충 해결 논리를 적용한 최종 결론 도출
    
    Returns:
        Partial State: {'final_verdict': str}
    """
    import json
    import time
    try:
        
        expert_reports = state.get("expert_reports", [])
        expert_confidence_scores = state.get("expert_confidence_scores", {})
        expert_evidence = state.get("expert_evidence", {})
        expert_analysis_results = state.get("expert_analysis_results", {})
        
        if not expert_reports:
            return {
                "errors": ["Arbiter 노드 실행 실패: 전문가 리포트가 없습니다."],
                "final_verdict": None
            }
        
        # 에러 마스킹 처리 (Raw Report 보호)
        clean_reports = [_mask_python_errors(r) for r in expert_reports]
        reports_text = "\n\n".join(clean_reports)
        
        # 1-3단계 로직 수행 (시각 특징, 판정, 상충 해결)
        # 1단계: 시각적 특징 추출
        visual_features = extract_visual_features(expert_analysis_results, expert_evidence)
        
        # 2단계: 1차/2차 단락흔 판정
        primary_secondary_result = calculate_primary_secondary_score(
            visual_features,
            uncertainty_threshold=PRIMARY_SECONDARY_SCORE_DIFF_THRESHOLD
        )
        determination = primary_secondary_result["determination"]
        primary_score = primary_secondary_result["primary_score"]
        secondary_score = primary_secondary_result["secondary_score"]
        score_difference = primary_secondary_result.get("score_difference", abs(primary_score - secondary_score))
        
        # 3단계: 상충 해결 적용
        conflict_resolution = apply_conflict_resolution(expert_analysis_results, expert_confidence_scores, expert_evidence)
        adjusted_scores = conflict_resolution["adjusted_scores"]
        conflicts = conflict_resolution["conflicts"]
        resolutions = conflict_resolution["resolutions"]
        
        # 4단계: 증거 위계 적용
        hierarchy_result = apply_evidence_hierarchy(adjusted_scores, expert_evidence)
        weighted_scores = hierarchy_result["weighted_scores"]
        evidence_types = hierarchy_result["evidence_types"]
        
        # 압도적 전문가 판정
        dominance_result = determine_dominant_expert(
            weighted_scores, 
            absolute_threshold=70.0, 
            margin_threshold=15.0
        )
        dominant_expert = dominance_result["dominant_expert"]
        max_score = dominance_result["max_score"]
        
        # 통계 요약 준비
        avg_confidence = sum(expert_confidence_scores.values()) / len(expert_confidence_scores) if expert_confidence_scores else 0
        
        confidence_summary = "\n".join([
            f"- {expert_name}: {score:.1f}%"
            for expert_name, score in expert_confidence_scores.items()
        ])
        
        weighted_confidence_summary = "\n".join([
            f"- {expert_name}: {score:.1f}% ({evidence_types.get(expert_name, 'N/A')})"
            for expert_name, score in weighted_scores.items()
        ])
        
        # 증거 요약
        evidence_summary_parts = []
        for expert_name, evidence_list in expert_evidence.items():
            if evidence_list:
                evidence_summary_parts.append(f"[{expert_name}]")
                for ev in evidence_list:
                    evidence_summary_parts.append(f"- {ev.get('evidence', 'N/A')}")
        evidence_summary = "\n".join(evidence_summary_parts) if evidence_summary_parts else "증거 없음"
        
        # 상세 요약 텍스트
        primary_secondary_summary = (
            f"1차 단락흔: {primary_score}점 / 2차 단락흔: {secondary_score}점 "
            f"-> 판정: {'1차 단락흔' if determination == 'primary' else '2차 단락흔' if determination == 'secondary' else '불확실'}"
        )
        
        conflict_summary = "상충 없음"
        if conflicts:
            conflict_summary = f"{len(conflicts)}건의 상충 해결됨"
            for res in resolutions:
                 conflict_summary += f"\n- {res.get('reason', '')}"

        # ---------------------------------------------------------
        # 판단 보류 체크 (Logic Check)
        # ---------------------------------------------------------
        # 조건: 압도적 1위가 없고(None) + (평균 점수 낮음 OR 점수 차이 미미)
        threshold = config.ARBITER_CONFIDENCE_THRESHOLD
        is_ambiguous = score_difference < PRIMARY_SECONDARY_SCORE_DIFF_THRESHOLD
        is_low_confidence = (avg_confidence / 100.0 < threshold)

        if not dominant_expert and (is_low_confidence or is_ambiguous):
            reason_code = "LOW_CONFIDENCE" if is_low_confidence else "AMBIGUOUS_VERDICT"
            return {
                "final_verdict": _generate_undetermined_report(
                    expert_confidence_scores,
                    expert_evidence,
                    clean_reports,
                    weighted_scores=weighted_scores,
                    reason_code=reason_code
                ),
                "errors": [f"판단 보류: {reason_code} (최고: {max_score:.1f}%, 차이: {score_difference}점)"]
            }

        # ---------------------------------------------------------
        # LLM 리포트 생성 (Synthesis)
        # [Disabled] arbiter_report_prompts.py가 삭제되어 비활성화됨
        # 실제 사용되는 것은 arbiter_expert_graph.py의 judge_node입니다.
        # ---------------------------------------------------------
        # arbiter_prompt = build_arbiter_report_prompt(
        #     reports_text,
        #     confidence_summary,
        #     weighted_confidence_summary,
        #     evidence_summary,
        #     primary_secondary_summary,
        #     conflict_summary,
        #     dominance_result,
        #     avg_confidence
        # )
        
        # Legacy 코드: 더 이상 실행되지 않음
        final_verdict = "[Legacy] 이 노드는 더 이상 사용되지 않습니다. arbiter_expert_graph.py를 사용하세요."
        # if client is None:
        #     final_verdict = "Error: GenAI Client Not Initialized"
        # else:
        #     response = client.models.generate_content(
        #         model=MODEL_NAME,
        #         contents=arbiter_prompt,
        #         config=generation_config
        #     )
        #     final_verdict = response.text if hasattr(response, 'text') else str(response)
        
        return {
            "final_verdict": final_verdict
        }
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "errors": [f"Arbiter 노드 실행 중 오류: {str(e)}"],
            "final_verdict": None
        }

