"""
Arbiter Agent 모듈
증거 통합 및 상충 해결을 통한 최종 결론 도출
"""
from typing import Dict, Any
from src.state import InvestigationState
from src.nodes.experts.arbiter_utils import (
    extract_visual_features,
    calculate_primary_secondary_score,
    determine_primary_or_secondary,
    apply_conflict_resolution,
    apply_evidence_hierarchy
)


def node_arbiter(state: InvestigationState) -> Dict:
    """
    Arbiter Agent 노드
    1차/2차 단락흔 판정 및 상충 해결 논리를 적용한 최종 결론 도출
    
    Returns:
        Partial State: {'final_verdict': str}
    """
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
        
        # 리포트들을 하나의 문자열로 결합
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
        
        # 1단계: 시각적 특징 추출
        visual_features = extract_visual_features(expert_analysis_results, expert_evidence)
        
        # 2단계: 1차/2차 단락흔 판정
        primary_secondary_result = calculate_primary_secondary_score(visual_features)
        determination = primary_secondary_result["determination"]
        primary_score = primary_secondary_result["primary_score"]
        secondary_score = primary_secondary_result["secondary_score"]
        
        # 3단계: 상충 해결 적용
        conflict_resolution = apply_conflict_resolution(expert_analysis_results, expert_confidence_scores)
        adjusted_scores = conflict_resolution["adjusted_scores"]
        conflicts = conflict_resolution["conflicts"]
        resolutions = conflict_resolution["resolutions"]
        
        # 4단계: 증거 위계 적용
        hierarchy_result = apply_evidence_hierarchy(adjusted_scores, expert_evidence)
        weighted_scores = hierarchy_result["weighted_scores"]
        evidence_types = hierarchy_result["evidence_types"]
        
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
- 점수 차이: {primary_secondary_result['score_difference']}점

[시각적 특징 분석]
- 광택: {visual_features.get('luster', 'N/A')}
- 기공: {visual_features.get('porosity', 'N/A')}
- 형상: {visual_features.get('shape', 'N/A')}
- 경계: {visual_features.get('demarcation', 'N/A')}
- 탄화 위치: {visual_features.get('carbonization_location', 'N/A')}
- 표면 질감: {visual_features.get('surface_texture', 'N/A')}
"""
        
        # 최종 결론 생성 프롬프트
        arbiter_prompt = f"""당신은 화재조사 Arbiter Agent입니다. 5명의 전문가가 구조화된 다단계 분석을 통해 작성한 리포트를 종합하여 최종 결론을 도출하세요.

[전문가 리포트]
{reports_text}

[전문가별 신뢰도 점수 (원본)]
{confidence_summary}

[전문가별 신뢰도 점수 (증거 위계 적용 후)]
{weighted_confidence_summary}

[전문가별 증거]
{evidence_summary}

{primary_secondary_summary}

{conflict_summary}

[판정 지시사항]
다음 항목을 포함하여 최종 결론을 작성하세요:

1. 화재 원인 종합 분석
   - 각 전문가의 신뢰도 점수(증거 위계 적용 후)와 증거를 고려한 평가
   - 가장 가능성 높은 화재 원인 결정

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

명확하고 객관적인 최종 결론을 작성해주세요. 특히 1차/2차 단락흔 구분을 반드시 포함하세요."""
        
        # Vertex AI 모델 호출
        from src.nodes.experts.expert_utils import model, generation_config
        from vertexai.generative_models import Part
        
        if model is None:
            # 모델이 없으면 구조화된 텍스트 기반 종합 수행
            final_verdict = f"""## 화재조사 최종 결론 (Arbiter Agent)

[전문가 리포트 요약]
{reports_text}

[전문가별 신뢰도 점수 (증거 위계 적용 후)]
{weighted_confidence_summary}

{primary_secondary_summary}

{conflict_summary}

[종합 분석]
제공된 전문가 리포트, 신뢰도 점수, 1차/2차 단락흔 판정 결과를 종합하여 분석한 결과:

1. 가장 가능성 높은 화재 원인: {max(weighted_scores.items(), key=lambda x: x[1])[0] if weighted_scores else '결정 불가'} (신뢰도: {max(weighted_scores.values()) if weighted_scores else 0:.1f}%)

2. 1차/2차 단락흔 판정: {'1차 단락흔 (화재 원인)' if determination == 'primary' else '2차 단락흔 (화재 결과)' if determination == 'secondary' else '불확실'}

3. 상충 해결: {len(conflicts)}개의 상충이 해결되었습니다.

각 전문가의 상세 리포트를 참고하여 추가 조사가 필요할 수 있습니다."""
        else:
            parts = [Part.from_text(arbiter_prompt)]
            response = model.generate_content(parts, generation_config=generation_config)
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

