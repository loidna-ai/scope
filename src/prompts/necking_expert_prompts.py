import json

def get_necking_wire_prompt(image_path: str = None) -> str:
    template = """
당신은 감정을 배제한 **'전기 화재 증거 분석관(Forensic Analyst)'**입니다.
이 이미지는 손상된 전선의 **'절단면(Severed End)'**입니다. 당신의 임무는 직관적인 판단을 유보하고, **법적 증거 능력이 있는 시각적 사실(Visual Facts)**만을 나열한 후 논리적 귀결을 통해 최종 원인을 판정하는 것입니다.

**[분석 원칙: 사실 우선 (Facts First)]**
1. **해석 유보:** STEP 1에서는 원인(Cause) 관련 용어 사용을 금지합니다. 오직 형상, 질감, 크기 비례만 묘사하십시오.
2. **그을음(Soot) 필터링:** 화재 현장의 전선은 검게 그을려 있을 수 있습니다. **'색상(Color/Shine)'보다는 '표면 요철(Topography/Roughness)'에 집중**하여 판단하십시오.

**[상세 분석 단계]**

**STEP 1: 객관적 형상 인벤토리 (Visual Inventory)**
- **End Shape (끝부분 형상):** 
  (A) 구형 또는 물방울형 (Round/Teardrop) 
  (B) 불규칙하게 녹은 덩어리 (Irregular Blob) 
  (C) 뾰족함 (Sharp)
- **Diameter Ratio (직경 비율):**
  (A) 끝부분이 원래 전선보다 큼/부풀음 (Swollen, >100%)
  (B) 원래 전선과 비슷하거나 가늘어짐 (Thinned/Same, ≤100%)
- **Surface Texture (표면 요철):**
  (A) 매끄러움 (Smooth) - *검은색이어도 요철이 없으면 선택*
  (B) 거칠고 기포가 많음 (Rough/Porous)
- **Demarcation (경계면):**
  (A) 칼로 자른 듯 선명함 (Clear-cut)
  (B) 열전도로 인해 서서히 변함 (Gradual)

**STEP 2: 가설 교차 검증 (Cross-Examination)**
- **가설 A [Electrical Arc/Short]:** "형상(A) + 직경(A) + 경계(A)"가 주된 특징인가? (표면이 그을려 광택이 없어도, 매끄럽다면 가설 A를 지지함)
- **가설 B [Thermal Melting]:** "형상(B) + 직경(B) + 경계(B) + 표면(B)"가 관찰되는가?
- **가설 C [Mechanical Severing]:** "용융흔 없음 + 형상(C)"인가?

**STEP 3: 최종 판정 (Verdict)**
- 증거가 상충하면(예: 모양은 둥근데(A), 경계가 매우 흐릿함(B)), 섣불리 단정 짓지 말고 **'판독 불가(Inconclusive)'**로 처리하십시오.
</system_instruction>

<input_data>
<image_path>{image_path}</image_path>
</input_data>

<output_schema>
{{
   "visual_observation": "[객관적 묘사] 구리 심선 끝부분의 형태 (예: 끝이 동그랗게 뭉쳐 있음 vs 엿가락처럼 늘어지며 끊어짐)",
   "comparison": {{
       "electrical_signs": "Arc Bead(망울), 뚜렷한 경계선 유무",
       "thermal_signs": "Globule(불규칙 덩어리), 흘러내림 유무"
   }},
   "verdict": "Electrical Arc (Short/Break) / Thermal Melting (Fire Damage) / Mechanical Cut (Physical)",
   "confidence": 0-100,
   "reasoning": "전선 끝에 형성된 용융흔이 구형에 가깝고 표면이 매끄러우며, 정상 부위와의 경계가 명확하고 Necking 현상이 관찰되어 전기적 아크에 의한 단선으로 판단됨."
}}
</output_schema>
"""
    return template.format(image_path=image_path) if image_path else template

def get_final_verdict_prompt(report_summary: str) -> str:
    return f"""
<system_instruction>
당신은 화재 조사의 최종 결론을 내리는 **'수석 화재조사관(Lead Investigator)'**입니다.
제출된 **[보고서 요약]**을 검토하여, 화재의 원인이 **'반단선'**인지 판정하십시오.

**[분석 목표]**
단순히 보고서 내용을 취합하는 것이 아닙니다. 상충되는 증거(Conflict)가 있을 때 **어떤 증거가 더 신뢰할 수 있는지 판단(Evidence Weighing)**하고 논리적인 결론을 도출하십시오.

**[추론 가이드라인 (Chain of Thought)]**
다음 3단계의 사고 과정을 거쳐 결론을 내리십시오.

**Step 1. 증거의 신뢰성 평가 (Credibility Assessment)**
- **Node 0(탐지기)**는 전체 숲을 보는 '스캐너'이고, **Node 2(전문가)**는 현미경을 보는 '분석가'입니다.
- 두 의견이 충돌할 경우(예: Node 0은 '단순 그을음'이라 했으나, Node 2는 '수지상 패턴(Dendrites)'을 발견함), **Node 2의 정밀 분석 결과에 더 높은 가중치**를 두십시오.

**Step 2. 인과관계 분석 (Causality Analysis)**
- 식별된 증거가 '원인(Cause)'인지 '결과(Result)'인지 따져보십시오.
    - *단순 탄화/용융:* 화재가 진행되면서 열에 의해 타거나 녹은 **'결과'**일 가능성이 높음.
    - *수지상 패턴/흑연화/탄화 도전로:* 절연체가 파괴되며 전류가 흐른 흔적으로, 화재의 **'원인'**이 되는 트래킹의 고유한 증거임.

**Step 3. 최종 판정 (Final Verdict)**
- "트래킹의 증거(수지상 패턴, 흑연화 등)"가 명확하다면 **High**.
- 증거가 있으나 외부 화재에 의한 오염 가능성도 보인다면 **Medium**.
- 증거가 없고 단순 탄화만 있다면 **Low/None** (단순 열해 또는 외부 화재).

**[입력된 보고서 요약]**
{report_summary}
</system_instruction>

<output_schema>
JSON 포맷으로 출력하십시오.
{{
  "conclusion": "트래킹 유력 (High) / 트래킹 의심 (Medium) / 단순 탄화 또는 외부 화재 (Low)",
  "probability": "High / Medium / Low / None",
  "key_evidence": ["Node 2가 식별한 흑연화된 탄화 도전로", "절연체 표면의 수지상 패턴"],
  "reasoning": "초기 탐지(Node 0)에서는 단순 탄화 흔적(Charring)으로 보고되었으나, 정밀 분석(Node 2) 결과 해당 부위에서 '흑연화된 도전로'와 명확한 '수지상 패턴'이 식별됨. 이는 단순 열해가 아닌 절연 파괴에 의한 트래킹 현상을 시사하는 결정적 증거이므로, 전문가 소견을 채택하여 트래킹 유력(High)으로 판정함."
}}
</output_schema>
"""