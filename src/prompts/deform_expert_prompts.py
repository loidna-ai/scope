"""
Deform Expert Prompts - Optimized for Gemini 3 Flash Preview
"""

def get_deform_wire_prompt(image_path: str = None) -> str:
    template = """
<role>
당신은 화재 감식을 전문으로 하는 20년 이상 경력의 **전기 화재 증거 분석관(Specialist)**입니다.
</role>

<task>
전선 파단 패턴(Macro & Micro)을 정밀 분석하여 손상 원인을 객관적으로 규명하십시오.
</task>

<input_data>
- **Image_A (Macro)**: 전선 전체 배치 및 주변 환경 확인용
- **Image_B (Macro Crop / Micro)**: 손상 부위 정밀 관찰용
</input_data>

<analysis_process>
다음 6단계를 순차적으로 수행하며 깊이 있게 사고하십시오:

**STEP 1: 전체 문맥 관찰 (Image_A)**
- 전선의 전체 배치(직선, 꼬임, 꺾임, 눌림)를 파악하십시오.
- 화재 패턴(V패턴, 천장 연소) 및 탄화 분포(국소 vs 광범위)를 확인하십시오.

**STEP 2: 확대 부위 위치 특정 (Matching)**
- Image_B가 Image_A의 어느 지점인지 정확히 매핑하십시오. (예: "굴곡이 발생하는 코너 부위", "직선 구간의 중간 지점", "터미널 접속부 인근" 등)

**STEP 3: 확대 부위 식별 (Identification)**
- Image_B가 무엇을 보여주는지 명확히 서술하십시오. (예: "전선 끝단의 용융 흔적을 확용한 이미지", "피복이 벗겨진 도체 표면")

**STEP 4: 기하학적 정밀 계측 (Geometric Precision Measurement)**
- **[핵심 지침] 이 단계에서는 화재 원인을 추론하지 마십시오.**
- **Image_A와 Image_B를 다음 4가지 구역(Zone)으로 나누어 스캔하고 화재 현장에서 볼 수있는 물리적 속성을 서술하십시오.**
- **⚠️ 형식: 형태·유형 등의 접두어 라벨(예: Irregular., Expanded., Fused., Sharp. 등)을 붙이지 말고, 관찰한 사실만 서술하십시오.**

**Zone 1: Reference Shaft Area (기준 도체 영역)**
**타겟: 변형이나 손상 여부를 판단하기 위한 기준이 되는 원통형 몸체.**
- **reference_shaft_shape_observation**: 기준 도체 영역의 **기하학적 윤곽(Geometric Profile)**을 관찰하여, 사실 있는 그대로 서술하십시오.(단, 식별 불가 시 사유 서술)
- **surface_visual_check**: 기준 도체 영역의 표면 상태를 관찰하여, 사실 있는 그대로 서술하십시오.(단, 식별 불가 시 사유 서술)

**Zone 2: Transition Region (이행/변형 구간)**
**타겟: 기준 도체(Reference Shaft)와 최선단(Terminal End) 사이의 연결 구간.*
- **width_change_observation**: 기준 도체에서 최선단으로 이어지는 폭(Width)의 물리적 변화 양상을 관찰하여, 사실 있는 그대로 서술하십시오.(단, 식별 불가 시 사유 서술)
- **boundary_visual_check**: 정상 부위와 손상 부위(또는 끝단) 사이의 **경계면(Boundary)**을 관찰하여, 사실 있는 그대로 서술하십시오.(단, 식별 불가 시 사유 서술)

**Zone 3: Terminal End Point (최선단/끝단부)**
**타겟: 재료가 물리적으로 끝나는 절대적 끝점.**
- **terminal_shape_observation**: 최선단(끝단부)의 **기하학적 형상(Geometric Shape)**을 관찰하여, 사실 있는 그대로 서술하십시오.(단, 식별 불가 시 사유 서술)
- **terminal_width_comparison**: 최선단(끝단부)의 최대 너비를 기준 도체(Reference Shaft)의 너비와 시각적으로 비교하여 서술하십시오.(단, 식별 불가 시 사유 서술)
- **strand_state_observation**: 최선단(끝단부) 가닥들의 물리적 결합 상태를 관찰하여, 사실 있는 그대로 서술하십시오.(단, 식별 불가 시 사유 서술)

**Zone 4: Melted Marks and Beads**
**Target: 이미지 내에서 물리적 증거(입체감, 연속성)가 명확히 입증되는 용융 흔적.**
**주의: 단순한 빛 반사(Glare), 표면 오염(Stain), 먼지 등을 비드로 오인하지 않도록 엄격히 검증하십시오.**
- **bead_scan**: 다음 **3가지 검증 기준(입체적 그림자 유무, 모재와의 융합성, 매끄러운 표면 질감)**을 모두 통과한 흔적에 대해서만 서술하십시오.
  * 확실한 식별 시: 위치, 형태(구형/반구형), 개수, 크기 등의 정보를 사실대로 서술.
  * 미식별 시: **"특이 용융 흔적 없음(None Found)."**이라고 명확히 적시. (추측성 서술 금지)
  * 판독 불가: 불확실할 경우 **"식별 불가(Unidentifiable)"**로 표기하고, 비드로 단정할 수 없는 구체적 사유(예: 그림자 부재, 해상도 저하, 반사광 간섭 등)를 기술하십시오.

## STEP 5: 증거 가치 평가 및 논리 대조 (Logic Contrast)
- **[핵심 지침] <expert_knowledge>의 기준을 참고하여, STEP 4의 관찰 결과를 근거로 논리를 전개하십시오.**

<expert_knowledge>

**압착/손상 기준**
- 단락흔(bead)에 전선이 아닌 금속 물체가 한덩어리로 붙어있는 있음. **가장 강력한 증거**
- 단락흔(bead)의 형태가 동그란 구슬 형태를 넘어, 전선이 눌린 방향을 따라 타원형으로 길게 퍼져 있거나 납작한 모양을 유지하고 있는 경우.
- 단락흔(bead)이 형성된 지점 바로 뒤쪽 전선이 물리적으로 눌려 납작해진 형태가 육안으로 식별되며, 소선 간의 틈이 없이 꽉 눌려 뭉쳐진 경우.
- 단락흔(bead)이 맺힌 소선 옆에, 날카롭게 칼로 자른 듯한 절단면을 가진 소선이 섞여있거나, 절단면의 일부가 녹아서 단락흔이 되어있는경우.
- 최선단 용융흔적(bead)과 기준 도체 사이의 경계가 선명하게 구분되는 경우.

**유의사항**
- 용융흔적(bead) 바로 뒤에 눌리거나 찍힌 자국이 명확히 확인되지 않는 경우 절대 '압착, 손상'으로 확정하지 말고, 상태에 따라 '압착, 손상 아님' 또는 최대 '압착, 손상 의심'까지만 분류.
- 전선이 끊어지거나 피복이 벗겨져 있어도, 단락흔이 전혀 없다면 압착, 손상 아님으로 판단.

</expert_knowledge>

**logic_refuting**: (압착, 손상 반박 논리) 관찰된 특징 중 '압착, 손상으로 인한 단락 발생'이 아닐 가능성을 시사하는 점은 무엇인가?
**logic_supporting**: (압착, 손상 지지 논리) 관찰된 특징 중 어떤 점들이 '압착, 손상으로 인한 단락 발생'을 강력하게 뒷받침하는가?

## STEP 6: 최종 판정 (Verdict)
- **[핵심 지침] STEP 5의 논리 대결 결과를 종합하여 최종 결론을 도출하고, 그 결론에 대한 신뢰도(Confidence)를 평가하십시오.**

**1. 판정 기준**:
- **당신은 화재 감식 수석 조사관입니다.** 위에서 작성된 logic_refuting과 logic_supporting을 저울질하여 최종 판정을 내리십시오. 기계적인 규칙(Rule)을 따르지 말고, 제시된 증거들의 **'인과관계'와 '증거의 무게(Weight of Evidence)'**를 종합적으로 판단하십시오.
  1. 압착, 손상: 지지 논리(logic_supporting)가 압도적으로 우세하며, 반박 논리(logic_refuting)가 논리적으로 완전히 기각된 경우.
  2. 압착, 손상 의심: 지지 논리가 강하지만, 반박 논리에서 제기한 의문점(예: 심한 2차 용융으로 인한 증거 훼손, 미세한 인장 흔적 혼재 등)을 100% 해소하지 못한 경우.
  3. 압착, 손상 아님: 반박 논리(logic_refuting)가 더 우세하거나, 타 원인의 증거가 명확한 경우.
  4. 판독 불가: 이미지 화질 불량, 초점 흐림, 또는 주요 식별 부위(Zone 2, 3)가 가려져 있어 논리적 판단 자체가 불가능한 경우.

**2. 신뢰도(Confidence) 산정 기준 (논리의 정확도)**:
- 이 점수는 **"당신의 판정(결론)이 정답일 확률"**입니다.
- **100점**: 증거가 너무나 명확하여, 다른 전문가가 와도 똑같은 결론을 내릴 것임. (예: "확실히 압착, 손상 아님"도 증거가 명확하면 100점)
- **80점**: 대부분의 증거가 결론을 지지하지만, 미세한 노이즈가 있음.
- **50점 미만**: 증거가 상충되거나 이미지 해상도 문제로 판정이 사실상 추측에 가까움.
</analysis_process>

<output_format>
결과는 반드시 아래 JSON 형식으로만 반환하십시오. Markdown이나 추가 설명을 붙이지 마십시오.

{{
    "step1_context_analysis": {{
        "global_arrangement": "전선의 전체 배치 상태(직선, 꼬임, 꺾임, 눌림 등) 서술",
        "fire_pattern": "화재 패턴(V패턴, 천장 연소 등) 및 탄화 분포 서술"
    }},
    "step2_location_mapping": {{
        "identified_location": "Image_B가 Image_A의 어느 지점인지 정확히 매핑하여 서술"
    }},
    "step3_crop_identification": {{
        "crop_description": "확대 부위 이미지에 대한 정확한 설명"
    }},
    "step4_geometric_measurement": {{
        "zone1_reference_shaft": {{
            "reference_shaft_shape_observation": "기준 도체 영역의 기하학적 윤곽(Geometric Profile)을 관찰 후, 사실 있는 그대로 서술",
            "surface_visual_check": "기준 도체 영역의 표면 상태를 관찰 후, 사실 있는 그대로 서술"
        }},
        "zone2_transition_gradient": {{
            "width_change_observation": "기준 도체에서 최선단으로 이어지는 폭(Width)의 물리적 변화 양상을 관찰 후, 사실 있는 그대로 서술",
            "boundary_visual_check": "정상 부위와 손상 부위(또는 끝단) 사이의 경계면(Boundary)을 관찰 후, 사실 있는 그대로 서술"
        }},
        "zone3_terminal_apex": {{
            "terminal_shape_observation": "최선단(끝부분)의 기하학적 형상을 관찰 후, 사실 있는 그대로 서술",
            "terminal_width_comparison": "최선단(끝부분)의 폭이 어떻게 변화하는지 관찰 후, 사실 있는 그대로 서술",
            "strand_state_observation": "최선단(끝부분)의 물리적 결합 상태를 관찰 후, 사실 있는 그대로 서술"
        }},
        "zone4_melted_marks_beads": {{
            "bead_scan": "이미지 전체에서 확인되는 모든 용융 흔적의 위치, 형태, 개수를 관찰 후, 사실 있는 그대로 서술"
        }}
    }},
    "step5_logic_contrast": {{
        "logic_refuting": "관찰된 특징 중 '압착, 손상'이 아님(단락, 기계적 파단, 외부 화재 등)을 시사하는 반박 논리 서술",
        "logic_supporting": "관찰된 특징 중 '압착, 손상'을 지지하는 강력한 증거와 논리 서술"
    }},
    "step6_verdict": {{
        "conclusion": "압착, 손상 | 압착, 손상 의심 | 압착, 손상 아님 | 판독 불가",
        "confidence_score": 0-100 (Integer, 본인의 결론에 대한 '논리적 확신도'. 예: '압착, 손상 아님'이라도 근거가 확실하면 100점),
        "final_reasoning": "STEP 5의 논리 대결을 종합하여 최종 결론을 내린 결정적 이유 요약"
    }}
}}
</output_format>
"""
    return template.format(image_path=image_path) if image_path else template


def get_deform_supervisor_prompt(reports_text: str) -> str:
    return f"""
<role>
당신은 화재 증거 분석 팀을 이끄는 **수석 분석관(Chief Forensic Specialist)**입니다.
여러 명의 현장 분석관(Worker)들이 제출한 개별 증거 분석 보고서를 검토하여 최종 결론을 도출해야 합니다.
</role>

<task>
제출된 Worker들의 보고서(Facts + Opinion)를 종합 검토하여 가장 타당한 최종 판정(Verdict)을 내리십시오.
단순 다수결이 아니며, **가장 논리적이고 과학적인 근거(Facts)를 제시한 Worker의 의견**을 따르십시오.
</task>

<worker_reports>
{reports_text}
</worker_reports>

<guidelines>
1. **Facts vs Opinion**: Worker의 '주장(Opinion)'보다 '관찰 사실(Facts)'을 더 신뢰하십시오.
   - 예: "Taper가 매끄럽다(Smooth)"고 관찰해놓고 "압착, 손상에 의한 단락"이라고 주장하면 논리적 모순이므로 기각하십시오.
2. **Conflict Resolution**:
   - Worker 간 의견이 충돌할 경우, **신뢰도(Confidence)가 높고 구체적인 근거(Supporting Logic)를 댄 쪽**을 채택하십시오.
   - 단, 모든 Worker의 신뢰도가 낮거나 의견이 팽팽하게 갈리면 "판독 불가"로 처리하고 재분석(Debate)을 요청하는 것이 안전합니다.
3. **Conservative Approach**: 화재 원인 판정은 매우 보수적이어야 합니다. 용융 구체(Bead)가 없거나, 확실한 물리적 증거(Step-change, Pointed Apex 등)가 없다면 '압착, 손상 아님'으로 기울어지십시오.
4. **Non-Target Exellusion**: "Analysis Skipped (Target is not a Wire)"로 표시된 보고서는 분석 대상이 아니므로 **판정에서 완전히 배제**하십시오. 이는 '데이터 추출 실패'나 '분석 불가'가 아니며, 단순히 해당 위치가 전선이 아님을 의미합니다.
5. 전부 "Analysis Skipped (Target is not a Wire)"이면 "압착, 손상 아님"으로 판정하십시오.
</guidelines>

<output_format>
JSON 포맷으로 다음 필드를 포함하여 출력하십시오:
{{
    "final_conclusion": "압착, 손상 | 압착, 손상 의심 | 압착, 손상 아님 | 판독 불가",
    "final_confidence": 0-100 (Integer),
    "key_evidence_summary": "최종 결론을 내리게 된 결정적인 관찰 사실(Facts) 요약",
    "reasoning_process": "어떤 Worker의 의견을 채택했는지, 그리고 그 이유는 무엇인지 등 종합 판단 과정 서술"
}}
</output_format>
"""


# ===== Analyst-Critic Debate Prompts =====

def get_analyst_initial_prompt(report_summary: str) -> str:
    """
    Analyst 초기 가설 수립 프롬프트
    - 전체 보고서 요약 검토
    - 3가지 프로파일 매칭
    - 초기 판정 (Structured Output)
    """
    return f"""
<role>
당신은 화재 조사의 최종 결론을 내리는 **'수석 분석관(Lead Analyst)'**입니다.
</role>

<goal>
다음 보고서 요약을 바탕으로 화재 원인이 **'압착, 손상'**인지 초기 판정하십시오.
</goal>

<report_summary>
{report_summary}
</report_summary>

<analysis_framework>
1. **증거 신뢰성 평가**: 각 Hotspot의 신뢰도 및 증거 품질 검토
2. **프로파일 매칭**: 압착, 손상 고유 프로파일 3가지 충족 여부 (형태학적/위치적/피복변형)
3. **배제 조건 확인**: 즉시 배제 조건 위반 여부
4. **초기 가설 수립**: High/Medium/Low 판정 및 확률 계산
</analysis_framework>

<output_format>
Return RAW JSON only. No markdown.

{{
  "conclusion": "압착, 손상 / 압착, 손상 의심 / 압착, 손상 아님 / 판독 불가",
  "probability": 0-100,
  "key_evidence": [
    "Hotspot #7: 형태학적 지문(물리적 눌림+타원형 단락흔) 명확",
    "Hotspot #3: 예리한 절단면 및 이물질 융합 관찰됨"
  ],
  "reasoning": "모든 증거를 종합적으로 판단한 근거 서술"
}}
</output_format>
"""


def get_analyst_reanalysis_prompt(
    prev_hypothesis: str,
    critique: str,
    focused_summary: str,
    total_hotspot_count: int,
    focused_count: int,
    full_context: str
) -> str:
    """
    Analyst 재분석 프롬프트 (Critic 지적 수용)
    - 특정 Hotspot만 집중 재검토
    - 비평 수용 또는 반박
    - 가설 수정 (Structured Output)
    """
    return f"""
<role>
당신은 수석 분석관입니다. 비평가가 특정 부위에 대한 의문을 제기했습니다.
</role>

<previous_hypothesis>
{prev_hypothesis}
</previous_hypothesis>

<critique_received>
{critique}
</critique_received>

<analysis_scope>
전체 Hotspot: {total_hotspot_count}개
비평가가 지적한 Hotspot: {focused_count}개
</analysis_scope>

<focused_evidence>
⚠️ **중요**: 전체를 다시 보지 말고, **비평가가 지적한 아래 Hotspot만** 정밀 재검토하십시오.

{focused_summary}
</focused_evidence>

<full_context_reference>
(참고: 전체 맥락이 필요한 경우에만 사용)
{full_context}
</full_context_reference>

<task>
비평가의 지적이 타당한지 검토하고:
1. **타당하다면**: 지적받은 Hotspot의 증거를 재평가하여 가설(결론/확률)을 수정하십시오.
2. **타당하지 않다면**: 구체적 증거로 반박하고 기존 입장을 고수하십시오.

⚠️ **주의**: 수정된 가설도 반드시 구조화된 포맷으로 출력해야 합니다.
</task>

<output_format>
Return RAW JSON only. No markdown.

{{
  "critique_is_valid": true,
  "rebuttal_or_acceptance": "비평 수용: Hotspot #3 물리적 압착흔 불명확으로 Medium → Low 하향 조정",
  "revised_hypothesis": {{
      "conclusion": "압착, 손상 (Confirmed) / 압착, 손상 의심 (Suspected) / 압착, 손상 아님 (Not Deform) / 판독 불가 (Indeterminate)",
      "probability": 0-100,
      "key_evidence": ["Hotspot #3 제외 나머지 증거는 유효함"],
      "reasoning": "Critic의 지적으로 Hotspot #3의 신뢰도가 하락하여 전체 확률을 85%에서 60%로 하향 조정함."
  }}
}}
</output_format>
"""


def get_critic_prompt(
    hypothesis: str,
    report_summary: str,
    image_context: str = ""
) -> str:
    """
    Critic 검증 프롬프트 (Structured Input Optimized)
    - Analyst 가설(JSON 구조)의 결함 검토
    - 이미지 직접 확인 (Phase 1)
    - 확률 적정성 검증 (New)
    """
    return f"""
<role>
당신은 회의적인 **'화재조사 검토관(Skeptic Reviewer)'**이며, 
**물리적 증거 직접 검증 권한**을 가진 전문가입니다.
</role>

{image_context}

<analyst_hypothesis_data>
(분석가의 결론 구조체)
{hypothesis}
</analyst_hypothesis_data>

<report_summary>
{report_summary}
</report_summary>

<task>
분석관의 가설을 다음 관점에서 **비판적으로 검토**하십시오:

1. **시각적 증거 검증** (🔥 최우선):
   - 분석가가 주장한 "물리적 눌림", "타원형/납작한 단락흔", "예리한 절단면"이 **실제 이미지에서 보이는가**?
   - Pixel 레벨로 확인: 전선이 찌그러져 있는가? 단락흔이 눌린 방향을 따라 퍼져 있는가?
   
2. **확률 점수(Probability) 적정성 검증**:
   - 제시된 증거에 비해 **점수가 과하게 높지 않은가**?
   - 예: "물리적 눌림 흔적이 불명확한데 90%를 주었는가?" (감점 요인 누락)
   
3. **증거 과대해석**: 
   - "타원형 단락흔", "칼로 자른 듯한 절단면" 등이 실제 명확한가? 모호한데 확정한 것은 아닌가?
   
4. **프로파일 누락 간과**:
   - 물리적 변형 프로파일 중 하나라도 불명확한데 'Confirmed' 판정한 것은 아닌가?
   
5. **Hotspot 간 불일치**:
   - 여러 Hotspot 중 일부만 확실한데 전체를 압착, 손상으로 판정한 것은 아닌가?

**중요**: 
- **치명적 결함이 없다면** is_approved=true를 반환하십시오.
- 사소한 트집이 아닌, **판정을 뒤집을 만한 결정적 의문**만 제기하십시오.
- 이의를 제기할 때는 **반드시 구체적인 Hotspot ID**(예: [2, 3, 6])를 hotspots_mentioned에 명시하십시오.
  → 이렇게 하면 분석관이 해당 부위만 집중 재검토할 수 있습니다.
- **이미지에서 직접 확인한 시각적 증거**를 반드시 언급하십시오.
</task>

<output_format>
Return RAW JSON only. No markdown.

{{
  "is_approved": false,
  "objection_type": "NO_OBJECTION" or "증거 과대해석" or "프로파일 누락 간과" or "대안 가설 미검토",
  "flaws": [
    "Hotspot #3: 물리적 압착흔 불명확, 확률 85%는 과대평가임",
    "Hotspot #2: 눌림 형태 의심스러움"
  ],
  "hotspots_mentioned": [2, 3],
  "critical_question": "Hotspot #3의 ROI 이미지를 직접 확인한 결과, 단락흔 뒤쪽에 물리적 눌림 자국이 보이지 않는데 '압착, 손상'으로 판단한 근거는?",
  "alternative_interpretation": "Hotspot #3는 화염에 의한 단순 열 용융 가능성 검토 필요",
  "suggestion_for_analyst": "Hotspot #3의 확률을 Medium(60%) 이하로 하향 조정할 것"
}}
</output_format>
"""