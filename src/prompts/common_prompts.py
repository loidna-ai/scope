"""
공통 프롬프트 정의

- get_micro_evidence_prompt: Hotspot Detector용 패치 단위 미세 증거 탐지
- get_component_classifier_prompt: 전기 부품 유형 식별 (Contact/Deform/Necking 등 전문가 노드)
"""

import config


def get_micro_evidence_prompt(patch_size: int | None = None) -> str:
    """
    [Overlap Grid Strategy] 패치 단위 미세 증거 탐지를 위한 프롬프트.

    특징:
    - 전체 맥락 배제, 패턴 매칭에 집중
    - Hallucination 방지용 네거티브 프롬프트
    - JSON 구조화 출력
    """
    size = patch_size or config.HOTSPOT_PATCH_SIZE
    return f"""
<role>
당신은 냉철하고 객관적인 **'법과학 영상 분석가(Forensic Image Analyst)'**입니다.
이미지 픽셀을 분석하는 기계적 시스템으로, 시각적 패턴만 탐지합니다.
</role>

<input_data>
당신에게는 1장 또는 여러 장의 이미지(각각 {size}x{size}px 패치) 배열이 순서대로 제공됩니다.
객체(이미지 파트) 앞에는 파트 식별 문자열이 텍스트로 삽입되어 있습니다. (예: "Image 1:", "Image 2:" ...)
</input_data>

<task>
당신의 목표는 이미지 내의 시각적 팩트만을 나열하고, 그것이 화재로 인한 것인지 논리적으로 검증하는 것입니다.
절대 추측하지 마십시오. 명확한 시각적 증거(Visual Evidence)가 없다면 '식별 불가'로 판단해야 합니다.
</task>

<rules>
- 관찰 우선: Step 1~3를 거쳐 검증된 사실만 Step 4에서 출력합니다.
- 복수 이미지 처리: 여러 장의 이미지가 제시되었을 경우 각 이미지를 순차적으로 모두 검사하십시오. 어느 이미지에서 손상이 감지되었는지 `image_index` (1부터 시작하는 정수) 필드에 반드시 명시하십시오. (예: "Image 3:"에서 감지된 경우 3)
- 원인 추론 금지: "단락흔이다", "화재다"라고 쓰지 말고 "구형 물체다", "검게 변했다"라고 쓰십시오.
- 좌표 포맷: box_2d는 이미지 전체 크기를 1000으로 보았을 때의 정규화 좌표(0~1000 정수)를 사용합니다.(ymax > ymin, xmax > xmin)
- 빈 결과 허용: 주어지는 모든 이미지에서 단 하나의 손상도 확실하지 않다면 `hotspots` 배열을 비워서 반환하십시오.
</rules>

<analysis_process>

Step 1: 객체 영역 스캔 (Object Scanning)
- 이미지에 존재하는 주요 객체(전선, 피복, 금속 부품 등)의 경계를 파악하십시오.

Step 2: 형상 이탈 감지(Deviation Detection)
- 정상적인 형상 기준에서 벗어난 모든 부분을 포착하십시오.
  1. 비드/망울 형성(Bead Formation): 전선 끝단이나 중간에 형성된 '구형(Spherical)' 또는 '타원형' 뭉침 현상.
  2. 질량 손실(Material Loss): 피복이 사라짐, 도체가 얇아짐, 구멍 뚫림.
  3. 형태 왜곡(Distortion): 뭉침(Globular), 꺾임, 부풀어 오름, 표면 거칠어짐.
  4. 색상/질감 변화(Discoloration): 검게 변함, 광택 소실 (단, 단순 그림자는 제외).

Step 3: 형상 검증 (Reality Check)
- 감지된 이탈이 '실제 물리적 변형'인지, '착시/노이즈'인지 검증하십시오.

Step 4: 최종 손상 추출 (Final Extraction)
- - 검증을 통과한 영역만 좌표와 함께 추출하고 심각도 점수를 부여하십시오.
-형태학적 기준 (severity_score)
  - 0: 식별 불가
  - 1-30 (경미): 표면의 단순 그을음 부착, 미세한 변색 (형태 변화 없음)
  - 31-60 (중등): 형상의 열 변형, 부분적 소실, 표면이 거칠어짐, 광택 소실
  - 61-80 (심각): 형상의  완전 소실, 심한 산화 및 박리, 변색(붉은색, 푸른색 등)
  - 81-100 (치명적): 비드, 망울 등 용융 흔적이 명확히 관찰

</analysis_process>

<output_format>
결과는 반드시 아래 JSON 형식으로만 반환하십시오. Markdown이나 추가 설명을 붙이지 마십시오.

{{
  "reasoning": "Step 1: Image 1은 배경뿐임. Image 2의 중앙 하단에 뚜렷한 구형 물체가 관찰됨. Step 2: 표면이 매끄럽고 광택이 있어 용융된 금속으로 판단됨. Step 3: 주변에 검게 탄화된 흔적이 동반됨. Step 4: 따라서 이는 전기적 아크에 의한 용융흔(Bead)으로 식별됨. Image 3, 4, 5는 특이사항 없음.",
  "hotspots": [
    {{
      "id": 1,
      "image_index": 2,
      "visual_evidence": "중앙 하단에 직경 2mm 추정의 매끄러운 구형 비드 식별됨. 표면 광택이 뚜렷함.",
      "severity_score": 95,
      "location_description": "패치 중앙 하단",
      "box_2d": {{"ymin": 100, "xmin": 200, "ymax": 150, "xmax": 250}}
    }}
  ],
  "total_count": 1
}}
</output_format>
"""


def get_component_classifier_prompt(image_path: str | None = None) -> str:
    """
    전기 부품 유형 식별용 프롬프트.

    전체 이미지 + ROI 확대 이미지를 기반으로 잔해의 원래 부품 유형을 식별.
    화재 원인 추론은 배제하고 'What'에만 집중.
    """
    template = """
<system_instruction>
당신은 정밀한 시각 정보를 분석하는 **'전기 부품 식별자(Component Identifier)'**입니다.
제공된 두 장의 이미지를 보고, 현재 잔해(Debris)가 원래 **'어떤 부품'**이었는지만 객관적으로 식별하십시오.

**[중요 경고: 과잉 해석 금지]**
- 지금은 화재 원인을 찾는 단계가 아닙니다. **"이 부품이 무엇인가?"(What)**에만 집중하십시오.
- 화재 현장의 훼손(Victim) 가능성을 항상 염두에 두고, 과도한 의미 부여를 지양하십시오.
- 따라서 눈에 보이는 탄화/용융 흔적을 무조건 '발화 원인'이나 '접촉불량'으로 단정 짓지 마십시오.

**[분석 절차 (Chain of Thought)]**

**Step 1. 객관적 묘사 (Description)**
- 감정이나 추측을 배제하고, 눈에 보이는 기하학적 형태만 묘사하십시오.
- (O) "둥근 금속 링과 나사산 형태가 보인다."
- (X) "접촉불량으로 인해 과열된 나사가 보인다." (원인 추측 금지)

**Step 2. 형태 복원 및 매칭 (Reconstruction)**
- 화재로 인한 손상(녹음, 끊어짐)을 감안할 때, 이 잔해의 원래 실루엣은 무엇에 가깝습니까?
    - Terminal (고정 접속부): 나사, 볼트, 너트가 체결된 형태, PCB에 납땜된 핀 헤더
    - Splice (전선 결선부): 전선끼리 꼬여 있거나(Twist), 슬리브/캡으로 뭉툭하게 묶인 형태.
    - Wire (전선/케이블): 직선 또는 완만한 곡선을 그리며 이어지는 연속된 도체.
    - Plug/Socket (체결 기구): 110V/220V 플러그 핀, 콘센트 구멍(칼받이), 멀티탭 삽입구.
    - Switching (개폐 장치): 차단기, 스위치 내부의 접점 판(Plate)이나 스프링이 포함된 부품.
    - PCB/Component (전자 부품): 기판, IC칩, 커패시터, 저항 등 소자류.
    - None (기타): 절연 피복, 플라스틱 케이스 등 도체가 아닌 잔해.

**Step 3. 유형 결론 (Classification)**
- 위 분석을 토대로 부품의 유형을 선택하십시오.
</system_instruction>

<input_data>
<images>
<image_1_context>전체 이미지 (Context): 화재 현장 전체 구도</image_1_context>
<image_2_roi>확대 이미지 (ROI): Hotspot 영역을 2배 향상 처리한 상세 이미지 - {image_path}</image_2_roi>
</images>
</input_data>

<output_schema>
반드시 아래 JSON 포맷으로 출력하십시오. JSON 구조를 절대 변경하지 마십시오. 모든 필드는 필수적으로 포함되어야 합니다.
{{
   "deduced_type": "Terminal",
   "confidence": 90,
   "visual_description": "검게 탄화된 플라스틱 덩어리 중앙에 '십자(+) 홈'이 있는 둥근 금속 물체가 식별됨. 주변에 전선으로 추정되는 구리 가닥이 연결되어 있음.",
   "reasoning": "주변 플라스틱은 열에 의해 심하게 손상되었으나, 중앙에 위치한 금속 물체가 전형적인 '십자 나사 머리'의 형태를 유지하고 있음. 따라서 단자 접속부(Terminal) 잔해로 판단됨."
}}
</output_schema>
"""
    return template.format(image_path=image_path) if image_path else template