"""
Arbiter Agent 모듈 (Legacy - 논쟁 시스템으로 교체됨)
증거 통합 및 상충 해결을 통한 최종 결론 도출

[주의] 이 파일은 논쟁 시스템(arbiter_expert_graph.py)으로 교체되었습니다.
기존 로직 체인 방식의 참고용으로 보관됩니다.
"""
from typing import Dict, Any, List
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

# 판단 불가 상태 상수
UNDETERMINED_VERDICT = "UNDETERMINED"

# 1차/2차 판정 점수 차이 임계값 (점수 차이가 이 값 미만이면 판단 불가)
PRIMARY_SECONDARY_SCORE_DIFF_THRESHOLD = 10

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
    
    Args:
        confidence_scores: 전문가별 신뢰도 점수 (0-100)
        evidence: 전문가별 증거 리스트
        reports: 전문가 리포트 텍스트 리스트
        weighted_scores: 증거 위계 적용 후 가중치 점수 (선택사항)
        primary_secondary_summary: 1차/2차 판정 요약 (선택사항)
        conflict_summary: 상충 해결 요약 (선택사항)
        reason_code: 판단 불가 사유 코드 ("LOW_CONFIDENCE", "INSUFFICIENT_EVIDENCE", "AMBIGUOUS_VERDICT")
    
    Returns:
        판단 불가 리포트 텍스트
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
        f"- {expert_name}: {score}%"
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
    
    # 부족한 증거 항목 분석
    missing_evidence_parts = []
    if not evidence or all(not ev_list for ev_list in evidence.values()):
        missing_evidence_parts.append("- 모든 전문가가 충분한 증거를 제시하지 못했습니다.")
    
    if low_conf_experts:
        missing_evidence_parts.append(f"- 신뢰도가 낮은 전문가: {', '.join(low_conf_experts)}")
    
    # 판단 불가 사유 메시지
    reasons = {
        "LOW_CONFIDENCE": f"전문가 신뢰도 평균({avg_conf:.1f}%)이 임계값({threshold*100:.0f}%) 미만입니다.",
        "INSUFFICIENT_EVIDENCE": "핵심 증거가 부족하여 결론을 내릴 수 없습니다.",
        "AMBIGUOUS_VERDICT": "1차/2차 단락흔 판정 점수 차이가 미미하여 구분이 불가능합니다."
    }
    
    reason_text = reasons.get(reason_code, reason_code)
    
    # 리포트 텍스트 결합
    reports_text = "\n\n".join(reports) if reports else "전문가 리포트 없음"
    
    # 리포트 생성
    report = f"""## 화재조사 최종 결론 (Arbiter Agent)

[판단 불가(UNDETERMINED) 선언]

**판단 불가 사유:**
{reason_text}
- 평균 신뢰도: {avg_conf:.1f}%
- 임계값: {threshold*100:.0f}%
- 전문가 수: {len(confidence_scores)}명

[전문가 리포트 요약]
{reports_text}

[전문가별 신뢰도 점수]
{confidence_summary}"""
    
    # 증거 위계 적용 후 점수가 있으면 추가
    if weighted_scores:
        weighted_summary = "\n".join([
            f"- {expert_name}: {score:.1f}%"
            for expert_name, score in weighted_scores.items()
        ])
        report += f"\n\n[전문가별 신뢰도 점수 (증거 위계 적용 후)]\n{weighted_summary}"
    
    # 1차/2차 판정 요약이 있으면 추가
    if primary_secondary_summary:
        report += f"\n\n{primary_secondary_summary}"
    
    # 상충 해결 요약이 있으면 추가
    if conflict_summary:
        report += f"\n\n{conflict_summary}"
    
    report += f"""

[전문가별 증거]
{evidence_summary}

[부족한 증거 항목]
{chr(10).join(missing_evidence_parts) if missing_evidence_parts else "- 증거 수집 상태를 확인할 수 없습니다."}

[추가 조사가 필요한 사항]
1. 이미지 품질 및 각도 개선
   - 더 높은 해상도의 이미지 확보
   - 다양한 각도에서 촬영된 이미지 추가
   - **원본 이미지(Raw Image) 기반 분석 재확인**: 질감(기공, 거칠기) 분석이 원본 이미지에 기반했는지 검토

2. 전문가별 추가 분석 필요
   - 신뢰도가 낮은 전문가({', '.join(low_conf_experts) if low_conf_experts else '해당 없음'})의 재분석 고려
   - 각 전문가의 분석 단계별 상세 결과 검토
   - AI로 확대된(Enhanced) 이미지의 텍스처를 과신하지 않았는지 확인

3. 물리적 증거 추가 수집
   - 현장에서 추가 증거 수집
   - 실험실 분석 결과 보완

4. 전문가 간 상충 해결
   - 전문가 의견이 상충하는 경우, 추가 검증 실험 수행
   - 제3의 전문가 의견 수렴

**결론:**
현재 수집된 증거와 전문가 분석 결과만으로는 신뢰할 수 있는 결론을 도출할 수 없습니다. 
위의 추가 조사 항목을 수행한 후 재분석을 권장합니다."""
    
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
        
        # ---------------------------------------------------------
        # [로직 순서 변경] 계산을 먼저 다 수행하고, 나중에 판단 보류 체크
        # ---------------------------------------------------------
        
        # 2. 분석 데이터 가공 (Logic Chain)
        reports_text = "\n\n".join(expert_reports)
        
        # 신뢰도 점수 요약 생성
        confidence_summary = "\n".join([
            f"- {expert_name}: {score}%"
            for expert_name, score in expert_confidence_scores.items()
        ])
        
        # 증거 요약 생성
        evidence_summary_parts = []
        for expert_name, evidence_list in expert_evidence.items():
            if evidence_list:
                evidence_summary_parts.append(f"\n[{expert_name} 전문가 증거]")
                for ev in evidence_list:
                    evidence_summary_parts.append(f"  - Step {ev.get('step', 'N/A')}: {ev.get('evidence', 'N/A')}")
        
        evidence_summary = "\n".join(evidence_summary_parts) if evidence_summary_parts else "증거 없음"
        
        # ---------------------------------------------------------
        # [로직 순서 변경] 계산을 먼저 다 수행하고, 나중에 판단 보류 체크
        # ---------------------------------------------------------
        
        # 1단계: 시각적 특징 추출
        visual_features = extract_visual_features(expert_analysis_results, expert_evidence)
        print("\n" + "="*20 + " Arbiter Logic: Visual Features " + "="*20)
        print(json.dumps(visual_features, indent=2, ensure_ascii=False))
        
        # 2단계: 1차/2차 단락흔 판정 (임계값 전달!)
        primary_secondary_result = calculate_primary_secondary_score(
            visual_features,
            uncertainty_threshold=PRIMARY_SECONDARY_SCORE_DIFF_THRESHOLD
        )
        print("\n" + "="*20 + " Arbiter Logic: Primary vs Secondary " + "="*20)
        print(f"Primary Score: {primary_secondary_result['primary_score']}")
        print(f"Secondary Score: {primary_secondary_result['secondary_score']}")
        print(f"Difference: {primary_secondary_result.get('score_difference', 0)}")
        print(f"Determination: {primary_secondary_result['determination']}")
        
        determination = primary_secondary_result["determination"]
        primary_score = primary_secondary_result["primary_score"]
        secondary_score = primary_secondary_result["secondary_score"]
        score_difference = primary_secondary_result.get("score_difference", abs(primary_score - secondary_score))
        observed_count = primary_secondary_result.get("observed_count", 0)
        
        # 3단계: 상충 해결 적용 (미리 수행)
        conflict_resolution = apply_conflict_resolution(expert_analysis_results, expert_confidence_scores, expert_evidence)
        adjusted_scores = conflict_resolution["adjusted_scores"]
        conflicts = conflict_resolution["conflicts"]
        resolutions = conflict_resolution["resolutions"]
        
        # 4단계: 증거 위계 적용 (미리 수행)
        hierarchy_result = apply_evidence_hierarchy(adjusted_scores, expert_evidence)
        weighted_scores = hierarchy_result["weighted_scores"]
        evidence_types = hierarchy_result["evidence_types"]
        print("\n" + "="*20 + " Arbiter Logic: Weighted Scores " + "="*20)
        print(json.dumps(weighted_scores, indent=2, ensure_ascii=False))
        
        # ---------------------------------------------------------
        # [신규] 압도적 전문가 판정 수행
        # ---------------------------------------------------------
        dominance_result = determine_dominant_expert(
            weighted_scores, 
            absolute_threshold=70.0,  # 70점 이상이면 유력 후보
            margin_threshold=15.0     # 2등과 15점 차이면 독보적
        )
        print("\n" + "="*20 + " Arbiter Logic: Dominant Expert " + "="*20)
        print(json.dumps(dominance_result, indent=2, ensure_ascii=False))
        
        dominant_expert = dominance_result["dominant_expert"]
        max_score = dominance_result["max_score"]
        
        # ---------------------------------------------------------
        # [수정됨] 판단 보류(Undetermined) 체크 로직
        # ---------------------------------------------------------
        # 조건: 압도적 1위가 없고(None), 전체적으로 점수가 낮을 때만 판단 보류
        
        avg_confidence = sum(expert_confidence_scores.values()) / len(expert_confidence_scores) if expert_confidence_scores else 0
        threshold = config.ARBITER_CONFIDENCE_THRESHOLD
        
        # [변경] 평균이 낮더라도, 압도적 1위(dominant_expert)가 있으면 통과시킴!
        if not dominant_expert and (avg_confidence / 100.0 < threshold):
            return {
                "final_verdict": _generate_undetermined_report(
                    expert_confidence_scores,
                    expert_evidence,
                    expert_reports,
                    weighted_scores=weighted_scores,
                    reason_code="LOW_CONFIDENCE"
                ),
                "errors": [
                    f"압도적인 전문가가 없고 평균 신뢰도가 낮습니다. (최고점: {max_score:.1f}%, 평균: {avg_confidence:.1f}%)"
                ]
            }
        
        # 최종 신뢰도 점수 요약 (증거 위계 적용 후)
        weighted_confidence_summary = "\n".join([
            f"- {expert_name}: {score:.1f}% (증거 유형: {evidence_types.get(expert_name, 'N/A')})"
            for expert_name, score in weighted_scores.items()
        ])
        
        # 상충 해결 요약 생성
        conflict_summary_parts = []
        if conflicts:
            conflict_summary_parts.append("\n[상충 해결 결과]")
            for i, resolution in enumerate(resolutions, 1):
                conflict_summary_parts.append(f"{i}. {resolution.get('reason', 'N/A')}")
                conflict_summary_parts.append(f"   우선순위: {resolution.get('priority', 'N/A')}")
        else:
            conflict_summary_parts.append("\n[상충 해결 결과]\n상충하는 전문가 의견이 없습니다.")
        
        conflict_summary = "\n".join(conflict_summary_parts)
        
        # 1차/2차 판정 요약 생성
        primary_secondary_summary = f"""
[1차/2차 단락흔 판정]
- 1차 단락흔 점수: {primary_score}점
- 2차 단락흔 점수: {secondary_score}점
- 판정: {'1차 단락흔 (화재 원인)' if determination == 'primary' else '2차 단락흔 (화재 결과)' if determination == 'secondary' else '불확실'}
- 점수 차이: {score_difference}점

[시각적 특징 분석]
- 광택: {visual_features.get('luster', 'N/A')}
- 기공: {visual_features.get('porosity', 'N/A')}
- 형상: {visual_features.get('shape', 'N/A')}
- 경계: {visual_features.get('demarcation', 'N/A')}
- 탄화 위치: {visual_features.get('carbonization_location', 'N/A')}
- 표면 질감: {visual_features.get('surface_texture', 'N/A')}
"""
        
        # ---------------------------------------------------------
        # 3. [Logic Level] 판정 점수 차이 검증 (Ambiguity Check)
        # 계산이 다 끝난 상태에서 체크하므로 코드가 간결해짐
        # ---------------------------------------------------------
        if determination in ["uncertain", "undetermined"] or score_difference < PRIMARY_SECONDARY_SCORE_DIFF_THRESHOLD:
            return {
                "final_verdict": _generate_undetermined_report(
                    expert_confidence_scores,
                    expert_evidence,
                    expert_reports,
                    weighted_scores=weighted_scores,  # 이미 계산됨
                    primary_secondary_summary=primary_secondary_summary,  # 이미 생성됨
                    conflict_summary=conflict_summary,  # 이미 생성됨
                    reason_code="AMBIGUOUS_VERDICT"
                ),
                "errors": [
                    f"1차/2차 단락흔 판정 점수 차이({score_difference}점)가 임계값({PRIMARY_SECONDARY_SCORE_DIFF_THRESHOLD}점) 미만이거나 판정이 불확실합니다."
                ]
            }
        
        # ---------------------------------------------------------
        # 4. LLM 프롬프트 구성 (Synthesis) - 통과 시 실행
        # ---------------------------------------------------------
        # 신뢰도 평균 계산 (프롬프트에 포함하기 위해)
        avg_confidence_value = avg_confidence  # 이미 계산됨
        
        arbiter_prompt = f"""당신은 화재조사 Arbiter Agent입니다. 5명의 전문가가 구조화된 다단계 분석을 통해 작성한 리포트를 종합하여 최종 결론을 도출하세요.

[데이터 무결성 검증 지침]
- 전문가들이 **'미세 질감(기공, 거칠기)'**을 근거로 들 때는, 그 분석이 **원본 이미지(Raw Image)**에 기반했는지 비판적으로 검토하십시오.
- AI로 확대된(Enhanced) 이미지의 텍스처를 과신한 것으로 보이면 신뢰도를 낮추십시오.
- 전문가 리포트에서 질감, 기공, 표면 거칠기 등을 언급할 때, 원본 이미지에서도 확인 가능한지 검증하십시오.

[전문가 리포트]
{reports_text}

[전문가별 신뢰도 점수 (원본)]
{confidence_summary}

[전문가별 신뢰도 점수 (증거 위계 적용 후)]
{weighted_confidence_summary}

[압도적 전문가 판정 결과]
- 압도적 전문가: {dominant_expert if dominant_expert else '없음'}
- 최고 점수: {max_score:.1f}점
- 2위 점수: {dominance_result.get('second_score', 0):.1f}점
- 점수 격차: {dominance_result.get('margin', 0):.1f}점
- 판정: {'압도적 1위 확정' if dominance_result.get('is_determined', False) else '압도적 1위 미확정'}

[전문가 신뢰도 평균]
평균 신뢰도: {avg_confidence_value:.1f}% (임계값: {config.ARBITER_CONFIDENCE_THRESHOLD*100:.0f}%)

[전문가별 증거]
{evidence_summary}

{primary_secondary_summary}

{conflict_summary}

[중요: 판단 보류 조건]
다음 조건 중 하나라도 해당되면 "판단 불가(UNDETERMINED)" 상태를 선언하세요:

1. 압도적인 전문가가 식별되지 않는 경우
   - 최고 점수 전문가와 2위 전문가의 점수 차이가 15점 미만이고, 최고 점수가 70점 미만인 경우
   - 현재 1위: {dominance_result.get('dominant_expert', '없음')} ({max_score:.1f}점)
   - 현재 2위 격차: {dominance_result.get('margin', 0):.1f}점
   - 압도적 전문가가 없으면 신뢰할 수 있는 결론을 내릴 수 없음을 명시하세요

2. 모든 전문가의 신뢰도 점수 평균이 {config.ARBITER_CONFIDENCE_THRESHOLD*100:.0f}% 미만이고 압도적 전문가가 없는 경우
   - 현재 평균: {avg_confidence_value:.1f}%
   - 증거가 불충분하여 신뢰할 수 있는 결론을 내릴 수 없음을 명시하세요

3. 증거가 불충분하여 명확한 결론을 내릴 수 없는 경우
   - 전문가들이 충분한 증거를 제시하지 못한 경우
   - 이미지 품질이나 각도로 인해 분석이 제한된 경우
   - 원본 이미지 기반 검증이 불가능한 경우

4. 전문가 간 의견이 심각하게 상충하고 해결이 불가능한 경우
   - 상충 해결 규칙을 적용해도 명확한 우선순위를 정할 수 없는 경우

5. 1차/2차 단락흔 판정 점수 차이가 미미한 경우
   - 현재 점수 차이: {score_difference}점 (임계값: {PRIMARY_SECONDARY_SCORE_DIFF_THRESHOLD}점)
   - 점수 차이가 임계값 미만이면 구분이 불가능함을 명시하세요

판단 불가 상태일 경우, 다음을 포함하세요:
- 판단 불가를 선언한 이유 (위 조건 중 해당하는 것)
- 부족한 증거 항목 (어떤 증거가 더 필요했는지)
- 추가 조사가 필요한 사항 (추가로 확인해야 할 항목)

[판정 지시사항]
판단 보류 조건에 해당하지 않는 경우에만 다음 항목을 포함하여 최종 결론을 작성하세요:

1. 화재 원인 종합 분석
   - 각 전문가의 신뢰도 점수(증거 위계 적용 후)와 증거를 고려한 평가
   - 가장 가능성 높은 화재 원인 결정
   - 원본 이미지 기반 검증 결과

2. 1차 vs 2차 단락흔 판정
   - 위의 판정 매트릭스 결과를 반영하여, 단락흔이 화재의 원인인지 결과인지 명확히 구분하세요
   - 1차 단락흔: 화재의 직접적 원인
   - 2차 단락흔: 화재로 인한 결과

3. 상충 해결 결과 반영
   - 상충이 해결된 경우, 해결 과정과 결과를 명시하세요
   - 각 전문가 의견의 일치/불일치 사항

4. 증거 위계 적용 결과
   - 형상학적 변형 > 화학적 성분 > 일반적 탄화 순으로 가중치가 적용되었음을 반영하세요

5. 추가 조사가 필요한 사항

명확하고 객관적인 최종 결론을 작성해주세요. 증거가 충분하지 않다면 억지로 결론을 내리지 말고 판단 불가 상태를 선언하세요."""
        
        # 5. LLM 호출
        if client is None:
            # Fallback for offline/test: 구조화된 텍스트 기반 종합 수행
            dominant_info = ""
            if dominant_expert:
                dominant_info = f"\n[압도적 전문가]\n- {dominant_expert} (점수: {max_score:.1f}%, 2위와 격차: {dominance_result.get('margin', 0):.1f}점)"
            
            final_verdict = f"""## 화재조사 최종 결론 (Arbiter Agent)

[전문가 리포트 요약]
{reports_text}

[전문가별 신뢰도 점수 (증거 위계 적용 후)]
{weighted_confidence_summary}
{dominant_info}

{primary_secondary_summary}

{conflict_summary}

[종합 분석]
제공된 전문가 리포트, 신뢰도 점수, 1차/2차 단락흔 판정 결과를 종합하여 분석한 결과:

1. 가장 가능성 높은 화재 원인: {max(weighted_scores.items(), key=lambda x: x[1])[0] if weighted_scores else '결정 불가'} (신뢰도: {max(weighted_scores.values()) if weighted_scores else 0:.1f}%)

2. 1차/2차 단락흔 판정: {'1차 단락흔 (화재 원인)' if determination == 'primary' else '2차 단락흔 (화재 결과)' if determination == 'secondary' else '불확실'}

3. 상충 해결: {len(conflicts)}개의 상충이 해결되었습니다.

각 전문가의 상세 리포트를 참고하여 추가 조사가 필요할 수 있습니다."""
        else:
            # 최신 SDK 방식: Client를 사용하여 콘텐츠 생성
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=arbiter_prompt,
                config=generation_config
            )
            final_verdict = response.text if hasattr(response, 'text') else str(response)
        
        
        
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

