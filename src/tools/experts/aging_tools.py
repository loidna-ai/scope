
from typing import Dict, Any

def get_aging_plug_prompt(image_path: str = None) -> str:
    template = """
<system_instruction>
당신은 **'플러그/콘센트(Plug/Outlet) 정밀 감식 AI'**입니다.
이 이미지는 **'플러그 접속부'**로 식별되었습니다. **칼받이/핀 사이(Face)**의 절연 상태를 분석하십시오.

**[Focus Area: 페이스(Face) 및 핀 사이]**
- 두 개의 핀(또는 칼받이) 사이를 연결하는 **바닥면(Base)**을 집중 관찰하십시오.

**[분석 프로세스: 증거 대결]**

**A. 트래킹 가설 (Tracking Evidence)**
- **연결성:** 두 전극 사이를 가로지르는 **명확한 탄화 다리(Bridge)**가 형성되어 있는가?
- **광택:** 그 탄화물에서 **금속성 광택(Graphite luster)**이 관찰되는가? (중요한 트래킹 지표)

**B. 과열/단락 가설 (Overheat/Short)**
- **확산:** 탄화 흔적이 양극을 연결하지 않고, 한쪽 핀 주변에만 뭉쳐 있거나 그을음(Soot)처럼 흩어져 있는가?
- **변형:** 플라스틱 자체가 열에 의해 심하게 일그러졌는가?

**[판정 로직]**
- 양극을 잇는 '반짝이는 다리'가 핵심입니다. 이것이 보이면 'Tracking'입니다.
- 단순히 검게 그을렸거나 녹았으면 'Overheat/External Heat'입니다.
</system_instruction>

<input_data>
<image_path>{image_path}</image_path>
</input_data>

<output_schema>
{{
   "visual_observation": "[객관적 묘사] 핀 사이 플라스틱 면의 상태 및 탄화물 형태",
   "comparison": {{
       "tracking_signs": "양극 연결성, 흑연 광택 유무",
       "external_heat_signs": "단순 변형, 비연결성 그을음 유무"
   }},
   "verdict": "Tracking (Bridge formed) / Short or Overheat / Indeterminate",
   "confidence": 0-100,
   "reasoning": "양극 사이를 연결하는 도전로가 형성되었으며 흑연화된 광택이 관찰됨."
}}
</output_schema>
"""
    return template.format(image_path=image_path) if image_path else template

def step1_carbonization_depth(image_data: bytes, verbose: bool = False) -> Dict[str, Any]:
    """
    이미지에서 절연체의 탄화 심도와 방향을 분석합니다.
    (Placeholder: 실제 CV 알고리즘 구현 필요)
    """
    return {
        "carbonization_detected": True,
        "depth_level": "medium", 
        "direction": "surface_spread",
        "description": "Analysis function not fully implemented. Returning placeholder result."
    }

def step2_swelling_analysis(image_data: bytes, verbose: bool = False) -> Dict[str, Any]:
    """
    이미지에서 절연체의 스펀지 현상, 흑연화, 단순 용융을 분석합니다.
    (Placeholder: 실제 CV 알고리즘 구현 필요)
    """
    return {
        "swelling_detected": False,
        "graphitization": False,
        "melting_detected": True,
        "description": "Analysis function not fully implemented. Returning placeholder result."
    }

def step3_global_aging(image_data: bytes, verbose: bool = False) -> Dict[str, Any]:
    """
    이미지에서 전선 전체의 광역적 노후화 징후(균열, 변색 등)를 분석합니다.
    (Placeholder: 실제 CV 알고리즘 구현 필요)
    """
    return {
        "cracks_detected": False,
        "discoloration": "slight",
        "overall_condition": "aged",
        "description": "Analysis function not fully implemented. Returning placeholder result."
    }