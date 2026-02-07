"""
Arbiter Debate 프롬프트 템플릿
각 노드에서 사용할 프롬프트를 정의합니다.
"""
from typing import Dict, List

def format_debate_summary(messages: List[Dict]) -> str:
    """논쟁 메시지 히스토리를 요약"""
    summary_parts = []
    for msg in messages:
        speaker = msg.get("speaker", "")
        content = msg.get("content", "")
        stage = msg.get("stage", "")
        round_num = msg.get("round_num", 0)
        
        if speaker in ["contact", "deform", "necking"]:
            summary_parts.append(f"[Round {round_num}, {stage}] {speaker.upper()} 전문가:\n{content}\n")
    
    return "\n".join(summary_parts) if summary_parts else "논쟁 기록이 없습니다."

def format_opponent_arguments(messages: List[Dict], current_expert: str) -> str:
    """상대방 전문가들의 의견 요약"""
    opponent_parts = []
    for msg in messages:
        speaker = msg.get("speaker", "")
        if speaker != current_expert and speaker in ["contact", "deform", "necking"]:
            opponent_parts.append(f"[{speaker.upper()} 전문가]\n{msg.get('content', '')}\n")
    
    return "\n".join(opponent_parts) if opponent_parts else "상대방 의견이 없습니다."

def format_expert_opinions(expert_opinions: Dict) -> str:
    """전문가 의견 요약"""
    parts = []
    for expert_name, opinion in expert_opinions.items():
        parts.append(f"""
[{expert_name.upper()} 전문가]
- 결론: {opinion.get('conclusion', 'N/A')}
- 신뢰도: {opinion.get('confidence', 0)}%
- 증거: {', '.join(opinion.get('evidence', []))}
- 논리: {opinion.get('reasoning', 'N/A')}
""")
    return "\n".join(parts)

def build_opening_prompt(expert_opinion: Dict, expert_name: str) -> str:
    """Opening 라운드 프롬프트"""
    conclusion = expert_opinion.get("conclusion", "")
    confidence = expert_opinion.get("confidence", 0)
    evidence = expert_opinion.get("evidence", [])
    reasoning = expert_opinion.get("reasoning", "")
    
    return f"""당신은 {expert_name.upper()} 분석 전문가입니다.

[당신의 분석 결과]
- 결론: {conclusion}
- 신뢰도: {confidence}%
- 증거: {', '.join(evidence) if evidence else '증거 없음'}
- 논리: {reasoning}

[지시사항]
다른 전문가들(Contact, Deform, Necking) 앞에서 자신의 의견을 명확하고 설득력 있게 제시하세요.
1. 자신의 결론을 강력히 주장하세요
2. 증거와 논리를 바탕으로 자신의 분석이 정확함을 보여주세요
3. 객관적이고 전문적인 톤을 유지하세요
4. 다른 전문가의 의견을 언급하지 마세요 (이번 라운드는 자신의 의견 제시만)

자신의 의견을 제시하세요."""

def build_rebuttal_prompt(expert_opinion: Dict, expert_name: str, debate_history: List[Dict]) -> str:
    """Rebuttal 라운드 프롬프트"""
    conclusion = expert_opinion.get("conclusion", "")
    confidence = expert_opinion.get("confidence", 0)
    evidence = expert_opinion.get("evidence", [])
    reasoning = expert_opinion.get("reasoning", "")
    
    opponent_summary = format_opponent_arguments(debate_history, expert_name)
    
    return f"""당신은 {expert_name.upper()} 분석 전문가입니다.

[상대방 전문가들의 의견]
{opponent_summary}

[당신의 분석 결과]
- 결론: {conclusion}
- 신뢰도: {confidence}%
- 증거: {', '.join(evidence) if evidence else '증거 없음'}
- 논리: {reasoning}

[지시사항]
상대방의 의견에 대해 반박하거나 지지하세요.
1. 상대방의 논리적 오류나 약점을 지적하세요
2. 자신의 증거가 더 강력함을 보여주세요
3. 상대방의 의견과 자신의 의견이 일치하는 부분이 있다면 지지하세요
4. 객관적이고 전문적인 톤을 유지하세요

상대방의 의견에 대해 반박하거나 지지하세요."""

def build_final_prompt(expert_opinion: Dict, expert_name: str, debate_history: List[Dict]) -> str:
    """Final Argument 라운드 프롬프트"""
    conclusion = expert_opinion.get("conclusion", "")
    confidence = expert_opinion.get("confidence", 0)
    evidence = expert_opinion.get("evidence", [])
    
    debate_summary = format_debate_summary(debate_history)
    
    return f"""당신은 {expert_name.upper()} 분석 전문가입니다.

[전체 논쟁 요약]
{debate_summary}

[당신의 분석 결과]
- 결론: {conclusion}
- 신뢰도: {confidence}%
- 증거: {', '.join(evidence) if evidence else '증거 없음'}

[지시사항]
이전 라운드의 논쟁을 바탕으로 최종 의견을 제시하세요.
1. 논쟁 과정에서 제시된 모든 의견을 고려하세요
2. 합의가 가능하다면 합의하고, 합의 내용을 명시하세요
3. 합의가 불가능하다면 자신의 의견을 최종적으로 강조하세요
4. 다른 전문가의 의견도 존중하면서 자신의 결론을 제시하세요

최종 의견을 제시하세요."""

def build_judge_prompt(
    expert_opinions: Dict,
    debate_messages: List[Dict],
    expert_reports: List[str],
    consensus_reached: bool
) -> str:
    """Judge 노드용 프롬프트"""
    debate_summary = format_debate_summary(debate_messages)
    opinions_summary = format_expert_opinions(expert_opinions)
    
    return f"""당신은 화재조사 최종 판정 Judge입니다.

[논쟁 요약]
{debate_summary}

[전문가 의견]
{opinions_summary}

[전문가 리포트]
{chr(10).join(expert_reports) if expert_reports else '전문가 리포트 없음'}

[합의 상태]
{'합의 도달' if consensus_reached else '합의 미도달'}

[판정 지시사항]
1. 각 전문가의 의견을 객관적으로 평가하세요
2. 논쟁 과정에서 제시된 증거와 논리를 종합하세요
3. 합의가 이루어졌다면 합의 내용을 반영하세요
4. 합의가 이루어지지 않았다면:
   - 각 전문가의 신뢰도 점수와 증거의 강도를 고려하세요
   - 가장 강력한 증거를 가진 전문가의 의견을 채택하거나
   - 다수결로 결정하세요
5. 판단 불가한 경우 (증거 부족, 모든 전문가 신뢰도 낮음 등) UNDETERMINED을 선언하세요

[출력 형식]
다음 형식으로 최종 판정을 작성하세요:

## 화재조사 최종 결론 (Arbiter Agent)

[종합 분석]
(각 전문가의 의견을 종합한 분석)

[최종 판정]
(화재 원인 결정 또는 UNDETERMINED)

[판정 근거]
(판정에 대한 상세 근거)

[추가 조사 필요 사항]
(필요한 경우)

최종 판정을 작성하세요."""

def build_fact_check_prompt(
    message: str,
    expert_opinion: Dict,
    evidence_list: List[Dict]
) -> str:
    """
    Fact Check용 LLM 프롬프트 (Factcheck-GPT + AXCEL 방식)
    
    Args:
        message: 전문가가 제시한 메시지
        expert_opinion: 전문가의 의견 딕셔너리
        evidence_list: 전문가의 증거 리스트
        
    Returns:
        구조화된 프롬프트 문자열
    """
    conclusion = expert_opinion.get("conclusion", "")
    verdict = expert_opinion.get("verdict", "")
    evidence_texts = [ev.get("evidence", "") for ev in evidence_list if ev.get("evidence")]
    
    return f"""
<role>
당신은 화재조사 증거 검증 전문가(Fact Checker)입니다.
전문가의 주장과 증거 간의 일관성을 객관적으로 검증하는 것이 당신의 임무입니다.
</role>

<task>
다음 전문가의 주장이 제시된 증거와 논리적으로 일치하는지 검증하세요.

**검증 기준:**
1. **주장-증거 일치성**: 전문가의 결론(conclusion)이 증거 리스트에서 지지되는가?
2. **논리적 일관성**: 전문가의 판정(verdict)이 메시지 내용과 논리적으로 일치하는가?
3. **증거 활용도**: 메시지에서 제시된 증거들이 실제 증거 리스트와 일치하는가?
</task>

<expert_claim>
**결론 (Conclusion)**: {conclusion}
**판정 (Verdict)**: {verdict}
**메시지 내용**: {message}
</expert_claim>

<evidence_list>
{chr(10).join([f"- {ev}" for ev in evidence_texts]) if evidence_texts else "증거 없음"}
</evidence_list>

<verification_steps>
다음 3단계를 순차적으로 수행하세요:

**STEP 1: 주장-증거 일치성 검증**
- 전문가의 결론("{conclusion}")이 증거 리스트에서 직접적으로 또는 간접적으로 지지되는가?
- 증거가 결론을 뒷받침하는 논리적 근거를 제공하는가?

**STEP 2: 논리적 일관성 검증**
- 전문가의 판정("{verdict}")이 메시지 내용과 논리적으로 일치하는가?
- 메시지에서 언급된 증거와 판정 사이에 논리적 연결이 있는가?

**STEP 3: 증거 활용도 검증**
- 메시지에서 언급된 증거들이 실제 증거 리스트에 포함되어 있는가?
- 메시지가 증거를 과대해석하거나 왜곡하지 않았는가?
</verification_steps>

<output_format>
반드시 다음 JSON 형식으로만 반환하세요. Markdown이나 추가 설명을 붙이지 마세요.

{{
    "is_consistent": true or false,
    "consistency_score": 0-100,
    "verification_details": {{
        "claim_evidence_match": {{
            "is_supported": true or false,
            "reasoning": "결론이 증거에 의해 지지되는지에 대한 상세한 이유"
        }},
        "logical_consistency": {{
            "is_consistent": true or false,
            "reasoning": "판정과 메시지 간 논리적 일관성에 대한 상세한 이유"
        }},
        "evidence_usage": {{
            "is_accurate": true or false,
            "reasoning": "증거 활용의 정확성에 대한 상세한 이유"
        }}
    }},
    "overall_reasoning": "전체 검증 결과에 대한 종합적인 설명",
    "issues_found": [
        "발견된 일관성 문제 목록 (없으면 빈 배열)"
    ]
}}
</output_format>
"""
