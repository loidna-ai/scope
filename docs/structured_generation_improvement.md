# 구조화된 생성(Structured Generation) 개선 방안

## 📋 개요

기존 리포트의 "파싱(Post-Parsing)" 방식 대신, **생성 단계에서부터 구조화된 출력**을 사용하는 방식으로 개선합니다.

> **핵심**: 이미 전문가 노드(`verdict_analyst_node`)에서 사용 중인 **동일한 패턴**을 Judge 노드에도 적용합니다.

---

## 🔍 현재 상황 분석

### ❌ 현재 문제점 (Post-Parsing 방식)

**1. 최종 판정 생성 위치**
- `src/nodes/arbiter_nodes/judge_node.py` (라인 98): `call_gemini_text()` → 텍스트 생성
- `src/nodes/arbiter_node.py` (라인 251): `client.models.generate_content()` → 텍스트 생성

**2. 이중 과금 문제**
```
[현재 흐름]
LLM이 텍스트 생성 (비용 A)
    ↓
main.py의 parse_final_verdict()가 텍스트를 읽고 정규식으로 파싱
    ↓ (실패 시)
LLM이 텍스트를 다시 읽고 JSON 변환 (비용 B) ← 이중 과금!
```

**3. 지연 시간 증가**
- 생성 시간: ~2초
- 파싱 시간: ~1초 (LLM 파싱 사용 시)
- **총 지연: ~3초**

**4. 정확도 문제**
- 원본 텍스트의 뉘앙스를 파싱 과정에서 놓칠 수 있음
- 정규식 실패 시 Fallback 필요

### ✅ 이미 구조화된 출력을 사용하는 부분

**전문가 노드들:**
- `verdict_analyst_node` (Contact, Deform, Necking)
- `response_mime_type: "application/json"`
- `response_json_schema: AnalystHypothesis.model_json_schema()`
- ✅ **이미 구조화된 출력 사용 중**

---

## 🎯 개선 방안: 구조화된 생성 (Shift Left)

### 핵심 아이디어

**생성 단계에서부터 구조화된 출력 사용** → 파싱 단계 제거

```
[개선된 흐름]
LLM이 처음부터 JSON 생성 (비용 A만 발생)
    ↓
Pydantic 모델로 직접 파싱
    ↓
main.py에서 구조화된 데이터 사용
```

### 비교표

| 구분 | 리포트의 제안 (Post-Parsing) | 개선된 제안 (Structured Generation) |
|------|------------------------------|-------------------------------------|
| **흐름** | LLM이 텍스트 생성 → LLM이 텍스트를 읽고 JSON 변환 | LLM이 처음부터 JSON 생성 |
| **비용** | 생성 비용 + 파싱 비용 (입력 토큰 과다) | 생성 비용 (파싱 비용 $0) |
| **속도** | 생성 시간 + 파싱 시간 (약 1~2초 추가) | 생성 시간 (추가 지연 0초) |
| **정확도** | 원본 텍스트의 뉘앙스를 파싱 과정에서 놓칠 수 있음 | 생성 의도 그대로 데이터화 |
| **유지보수** | 정규식 패턴 관리 필요 | Pydantic 모델만 관리 |

---

## 📝 구체적인 구현 전략

### Step 1: Pydantic 모델 정의

**`src/models/verdict_models.py` (신규 생성)**

```python
"""
최종 판정 구조화 모델
Judge/Arbiter 노드에서 구조화된 출력으로 사용
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Literal

class ZoneInfo(BaseModel):
    """Zone별 상세 정보"""
    zone_number: int = Field(ge=1, le=10, description="Zone 번호")
    description: str = Field(description="Zone 설명 (예: 압착부 경계)")
    observation: str = Field(description="Zone 관찰 결과")

class ExpertReportSummary(BaseModel):
    """전문가 리포트 요약 (최종 판정에 포함)"""
    expert_name: Literal["CONTACT", "DEFORM", "NECKING"] = Field(description="전문가 이름")
    conclusion: Literal["유력", "의심", "아님", "해당 없음", "판독 불가"] = Field(description="판정 결과")
    confidence: Optional[float] = Field(None, ge=0, le=100, description="신뢰도 퍼센트")
    key_evidence: str = Field(description="핵심 근거 한 줄 요약")

class FinalVerdictResult(BaseModel):
    """최종 판정 구조화 데이터"""
    # 핵심 정보
    verdict: str = Field(description="최종 판정 결과 (예: 접촉불량(유력), 압착·손상(의심))")
    confidence_score: float = Field(ge=0, le=100, description="신뢰도 점수 (0-100)")
    confidence_level: Literal["High", "Medium", "Low"] = Field(description="신뢰도 레벨")
    
    # 판정 근거
    reasoning_summary: str = Field(description="판정의 논리적 근거 요약 (2-3문장)")
    key_evidence: List[str] = Field(
        max_length=5,
        description="판정에 사용된 핵심 증거 목록 (최대 5개)"
    )
    
    # Zone 정보
    zones: List[ZoneInfo] = Field(
        default_factory=list,
        description="Zone별 상세 정보 (Zone 1, 3, 4 등)"
    )
    
    # 전문가 요약
    expert_summaries: List[ExpertReportSummary] = Field(
        description="각 전문가의 판정 요약"
    )
    
    # 권고 사항
    recommendations: List[str] = Field(
        default_factory=list,
        description="추가 조사 권고 사항"
    )
    
    # 사용자용 리포트 본문 (선택적)
    report_body_markdown: Optional[str] = Field(
        None,
        description="사용자에게 보여줄 상세 리포트 본문 (Markdown 형식). "
                    "없으면 구조화된 데이터로부터 자동 생성 가능."
    )
```

### Step 2: Judge 노드 수정

**`src/nodes/arbiter_nodes/judge_node.py` 수정**

> **핵심**: 전문가 노드(`verdict_analyst_node`)와 **완전히 동일한 패턴** 사용

**전문가 노드 패턴 (참고):**
```python
# src/nodes/contact_nodes.py의 verdict_analyst_node (라인 863-920)
config_dict = {
    "temperature": 1.0,
    "response_mime_type": "application/json",
    "response_json_schema": AnalystHypothesis.model_json_schema(),
    "safety_settings": safety_settings
}
response = await asyncio.to_thread(
    client.models.generate_content,
    model=model_name,
    contents=system_prompt,
    config=types.GenerateContentConfig(**config_dict)
)
analyst_result = AnalystHypothesis.model_validate_json(response.text)
```

**Judge 노드도 동일하게:**
```python
"""
Judge 노드 - 구조화된 출력으로 변경
전문가 노드와 동일한 패턴 사용
"""
from typing import Dict, Any
from src.states.arbiter_debate_state import ArbiterDebateState
from src.prompts.arbiter_debate_prompts import build_judge_prompt
from src.models.verdict_models import FinalVerdictResult
from src.utils.genai_client import get_genai_client
from google import genai
from google.genai import types
import config
import os
from src.utils.logging_config import setup_logger

logger = setup_logger(__name__)

def judge_node(state: ArbiterDebateState) -> Dict[str, Any]:
    """
    Judge: 최종 판정 (구조화된 출력)
    
    Args:
        state: ArbiterDebateState
        
    Returns:
        최종 판정이 포함된 상태 업데이트
    """
    logger.info("Judge node: Starting structured final verdict generation")
    
    messages = state.get("debate_messages", [])
    expert_opinions = state.get("expert_opinions", {})
    expert_reports = state.get("expert_reports", [])
    consensus_reached = state.get("consensus_reached", False)
    
    # 실격 확인
    failures = state.get("fact_check_failures", {})
    disqualified = [expert for expert, count in failures.items() if count >= 3]
    
    if disqualified:
        # 실격 처리 (기존 로직 유지)
        remaining_experts = {k: v for k, v in expert_opinions.items() if k not in disqualified}
        verdict_text = generate_disqualification_verdict(disqualified, remaining_experts, messages)
        
        # 실격 케이스는 텍스트로 반환 (하위 호환성)
        return {
            "final_verdict": verdict_text,
            "final_verdict_structured": None,  # 구조화 데이터 없음
            "debate_messages": [{
                "speaker": "judge",
                "content": verdict_text,
                "validated": True,
                "stage": "judgment",
                "round_num": state.get("current_round", 1)
            }]
        }
    
    # 정상적인 논쟁 종료 - 구조화된 출력으로 최종 판정 생성
    try:
        prompt = build_judge_prompt(
            expert_opinions,
            messages,
            expert_reports,
            consensus_reached
        )
        
        # Gemini Client 및 모델 설정
        client = get_genai_client()
        model_name = os.environ.get("GEMINI_MODEL_NAME", config.GEMINI_MODEL_NAME)
        
        # 🔥 구조화된 출력 설정 (전문가 노드와 동일한 패턴)
        safety_settings_block_none = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        
        # Thinking Config (지원 모델에만) - 전문가 노드와 동일
        thinking_supported_models = ["gemini-2.0-flash-exp", "gemini-2.5-flash", "gemini-2.5-pro"]
        config_dict = {
            "temperature": 1.0,  # 공식 문서 권장사항: 1.0으로 통일
            "response_mime_type": "application/json",
            "response_json_schema": FinalVerdictResult.model_json_schema(),  # ← 전문가와 동일한 패턴
            "safety_settings": safety_settings_block_none
        }
        if any(m in model_name for m in thinking_supported_models):
            config_dict["thinking_config"] = types.ThinkingConfig(thinking_level="high")
        
        logger.debug("Judge: Calling LLM for structured final verdict")
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(**config_dict)
        )
        
        # Pydantic 모델로 파싱 (전문가 노드와 동일한 방식)
        response_text = getattr(response, 'text', None)
        finish_reason = "Unknown"
        if hasattr(response, 'candidates') and response.candidates:
            finish_reason = getattr(response.candidates[0], 'finish_reason', "Unknown")
        
        if not response_text:
            raise ValueError(f"Gemini API 응답 텍스트가 비어있습니다. (Finish Reason: {finish_reason})")
        
        # 🔥 구조화된 데이터 파싱 (전문가 노드와 동일: model_validate_json 사용)
        verdict_structured = FinalVerdictResult.model_validate_json(response_text)
        
        # 하위 호환성을 위한 텍스트 생성 (기존 코드와 호환)
        verdict_text = _format_verdict_text(verdict_structured)
        
        logger.info(f"Judge: Structured final verdict generated (confidence: {verdict_structured.confidence_score}%)")
        
        return {
            # [구조화 데이터] - 전문가 노드의 "analyst_hypothesis"와 동일한 패턴
            "final_verdict_structured": verdict_structured,
            
            # [하위 호환성] - 전문가 노드의 "current_hypothesis"와 동일한 패턴
            "final_verdict": verdict_text,
            
            "debate_messages": [{
                "speaker": "judge",
                "content": verdict_text,
                "validated": True,
                "stage": "judgment",
                "round_num": state.get("current_round", 1)
            }]
        }
        
    except Exception as e:
        logger.error(f"Judge: LLM call failed - {e}", exc_info=True)
        # Fallback: 간단한 판정 생성
        verdict_text = f"""## 화재조사 최종 결론 (Arbiter Agent)

[오류]
LLM 호출 실패: {str(e)}

[전문가 의견 요약]
{format_debate_summary(messages)}

[임시 판정]
각 전문가의 의견을 종합하여 판정하세요."""
        
        return {
            "final_verdict": verdict_text,
            "final_verdict_structured": None,
            "debate_messages": [{
                "speaker": "judge",
                "content": verdict_text,
                "validated": False,
                "stage": "judgment",
                "round_num": state.get("current_round", 1)
            }]
        }


def _format_verdict_text(verdict: FinalVerdictResult) -> str:
    """
    구조화된 판정 데이터를 텍스트 형식으로 변환 (하위 호환성)
    """
    lines = [
        f"**최종 판정**: {verdict.verdict}",
        f"**신뢰도**: {verdict.confidence_score:.1f}% ({verdict.confidence_level})",
        "",
        "**판정 근거:**",
        verdict.reasoning_summary,
        "",
        "**핵심 증거:**",
    ]
    
    for i, evidence in enumerate(verdict.key_evidence, 1):
        lines.append(f"{i}. {evidence}")
    
    if verdict.zones:
        lines.append("")
        lines.append("**Zone 정보:**")
        for zone in verdict.zones:
            lines.append(f"- Zone {zone.zone_number} ({zone.description}): {zone.observation}")
    
    if verdict.recommendations:
        lines.append("")
        lines.append("**추가 조사 권고 사항:**")
        for i, rec in enumerate(verdict.recommendations, 1):
            lines.append(f"{i}. {rec}")
    
    return "\n".join(lines)
```

### Step 3: 프롬프트 수정

**`src/prompts/arbiter_debate_prompts.py` 수정**

```python
def build_judge_prompt(
    expert_opinions: Dict,
    debate_messages: List[Dict],
    expert_reports: List[str],
    consensus_reached: bool
) -> str:
    """
    Judge 프롬프트 구성 (구조화된 출력용)
    
    중요: 이 프롬프트는 JSON Schema에 맞춰 응답하도록 설계됨
    """
    # ... 기존 프롬프트 구성 로직 ...
    
    return f"""당신은 화재조사 수석 조사관(Judge)입니다.
제공된 전문가 분석 결과와 토론 내용을 종합하여 최종 판정을 내리세요.

[입력 데이터]
- 전문가 의견: {expert_opinions}
- 토론 메시지: {len(debate_messages)}개
- 전문가 리포트: {len(expert_reports)}개
- 합의 도달 여부: {consensus_reached}

[판정 지침]
1. 3명의 전문가(Contact, Deform, Necking)의 의견을 종합하여 최종 판정을 내리세요.
2. 신뢰도 점수는 0-100 사이의 값으로 설정하세요.
3. 핵심 증거는 최대 5개까지 나열하세요.
4. Zone 정보는 분석에 사용된 Zone만 포함하세요 (Zone 1, 3, 4 등).
5. 각 전문가의 판정 요약을 expert_summaries에 포함하세요.

[출력 형식]
반드시 제공된 JSON Schema에 맞춰 응답하세요.
- verdict: 최종 판정 결과 (예: "접촉불량(유력)", "압착·손상(의심)")
- confidence_score: 신뢰도 점수 (0-100)
- confidence_level: 신뢰도 레벨 (High: 80+, Medium: 60-79, Low: <60)
- reasoning_summary: 판정 근거 요약 (2-3문장)
- key_evidence: 핵심 증거 목록 (최대 5개)
- zones: Zone별 상세 정보
- expert_summaries: 각 전문가의 판정 요약
- recommendations: 추가 조사 권고 사항 (있는 경우)

[전문가 리포트]
{chr(10).join(f'--- {i+1}번 전문가 ---{chr(10)}{report}' for i, report in enumerate(expert_reports))}

위 정보를 바탕으로 구조화된 최종 판정을 생성하세요."""
```

### Step 4: main.py 수정

**`main.py`의 파싱 함수들을 구조화된 데이터 사용으로 변경**

```python
# 기존: parse_final_verdict() 함수 사용
# 개선: 구조화된 데이터 직접 사용

def format_investigation_result(
    final_verdict: str,  # 하위 호환성 유지
    final_verdict_structured: Optional[FinalVerdictResult],  # 구조화 데이터
    expert_reports: List[str],
    arbiter_debate_messages: List[Dict[str, Any]],
    input_image_path: str,
    timestamp: str
) -> str:
    """
    분석 결과를 실무용 보고서 형식으로 포맷팅
    
    Args:
        final_verdict: 최종 판정 텍스트 (하위 호환성)
        final_verdict_structured: 구조화된 판정 데이터 (우선 사용)
        ...
    """
    output = []
    image_name = Path(input_image_path).name
    
    # 🔥 구조화된 데이터 우선 사용
    if final_verdict_structured:
        verdict_info = {
            "verdict": final_verdict_structured.verdict,
            "confidence": f"{final_verdict_structured.confidence_score:.1f}%",
            "confidence_level": final_verdict_structured.confidence_level
        }
        reasoning_text = final_verdict_structured.reasoning_summary
        zones = final_verdict_structured.zones
        recommendations = final_verdict_structured.recommendations
    else:
        # Fallback: 기존 정규식 파싱 (하위 호환성)
        verdict_info = parse_final_verdict(final_verdict)
        reasoning_text = None
        zones = []
        recommendations = []
    
    # 헤더 섹션
    output.extend(_format_report_header(timestamp, image_name, verdict_info))
    
    # Executive Summary 섹션
    if final_verdict_structured:
        output.extend(_format_executive_summary_structured(final_verdict_structured))
    else:
        summary_lines, reasoning_text = _format_executive_summary(final_verdict, verdict_info)
        output.extend(summary_lines)
    
    # 전문가 리포트 섹션
    output.extend(_format_expert_reports_section(expert_reports))
    
    # 증거 분석 섹션
    if final_verdict_structured and zones:
        output.extend(_format_evidence_breakdown_structured(zones))
    else:
        output.extend(_format_evidence_breakdown(reasoning_text))
    
    # 권고 사항 섹션
    if final_verdict_structured and recommendations:
        output.extend(_format_recommendations_structured(recommendations))
    else:
        output.extend(_format_recommendations(final_verdict))
    
    # AI 추론 로그 섹션
    output.append(_format_audit_trail_section(arbiter_debate_messages or []))
    
    return "\n".join(output)
```

---

## ⚠️ 위험 요소 재검토

### ❌ 리포트의 "정규식 Fallback" 전략의 문제점

**문제:**
- 프롬프트가 바뀌어 출력 형식이 조금이라도 변하면 정규식은 즉시 깨짐
- LLM 파싱을 도입하는 이유가 정규식 관리를 안 하기 위함인데, Fallback을 위해 정규식을 유지하는 것은 모순

**개선안:**

**1. Retry Logic (Self-Correction)**
```python
def judge_node_with_retry(state: ArbiterDebateState, max_retries: int = 2) -> Dict[str, Any]:
    """JSON 파싱 실패 시 재시도"""
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(...)
            verdict_structured = FinalVerdictResult.model_validate_json(response.text)
            return {"final_verdict_structured": verdict_structured, ...}
        except Exception as e:
            if attempt < max_retries - 1:
                # 에러 메시지를 포함해 재요청
                error_prompt = f"{original_prompt}\n\n[이전 시도 오류]\n{str(e)}\n\n위 오류를 수정하여 다시 응답하세요."
                continue
            else:
                # 최종 실패 시 기본값 반환
                return {"final_verdict_structured": None, ...}
```

**2. Strict Mode (Pydantic Validation 강화)**
```python
# Pydantic 모델에 엄격한 검증 추가
class FinalVerdictResult(BaseModel):
    # ...
    
    @field_validator('confidence_score')
    @classmethod
    def validate_confidence(cls, v):
        if not 0 <= v <= 100:
            raise ValueError("confidence_score must be between 0 and 100")
        return v
    
    @model_validator(mode='after')
    def validate_expert_summaries(self):
        if len(self.expert_summaries) != 3:
            raise ValueError("expert_summaries must contain exactly 3 experts")
        return self
```

---

## 💰 비용 절감 효과

### 현재 방식 (Post-Parsing)

```
1. 최종 판정 생성: ~2,000 토큰 입력, ~1,500 토큰 출력
   비용: (2,000/1M * $0.075) + (1,500/1M * $0.30) = $0.0006

2. 파싱 (LLM 사용 시): ~3,500 토큰 입력, ~750 토큰 출력
   비용: (3,500/1M * $0.075) + (750/1M * $0.30) = $0.0005

총 비용: $0.0011 (약 1.5원)
총 지연: ~3초
```

### 개선된 방식 (Structured Generation)

```
1. 최종 판정 생성 (구조화): ~2,000 토큰 입력, ~1,000 토큰 출력 (JSON)
   비용: (2,000/1M * $0.075) + (1,000/1M * $0.30) = $0.00045

2. 파싱: 없음 (Pydantic 모델로 직접 파싱)

총 비용: $0.00045 (약 0.6원)
총 지연: ~2초

비용 절감: 59% 감소
지연 감소: 33% 감소
```

---

## 📋 마이그레이션 로드맵

### Phase 1: 모델 정의 및 Judge 노드 수정 (1주)

1. ✅ **Pydantic 모델 정의**
   - `src/models/verdict_models.py` 생성
   - `FinalVerdictResult`, `ZoneInfo`, `ExpertReportSummary` 정의

2. ✅ **Judge 노드 수정**
   - `src/nodes/arbiter_nodes/judge_node.py` 수정
   - 구조화된 출력 사용
   - 하위 호환성 유지 (텍스트도 반환)

3. ✅ **프롬프트 수정**
   - `src/prompts/arbiter_debate_prompts.py` 수정
   - JSON Schema 준수 지시 추가

### Phase 2: main.py 통합 (1주)

4. ✅ **main.py 수정**
   - `format_investigation_result()` 함수 수정
   - 구조화된 데이터 우선 사용
   - 정규식 파싱은 Fallback으로만 사용

5. ✅ **테스트**
   - 기존 테스트 케이스로 검증
   - 구조화된 데이터와 텍스트 파싱 결과 비교

### Phase 3: 정규식 코드 제거 (1주)

6. ✅ **과감한 전환**
   - 정규식 Fallback 제거
   - Retry Logic으로 대체
   - 정규식 패턴 상수 제거

7. ✅ **최적화**
   - 불필요한 코드 제거
   - 문서화 업데이트

---

## ✅ 종합 추천

### 핵심 원칙

1. **Shift Left**: 생성 단계에서 구조화
2. **No Fallback**: 정규식 Fallback 제거, Retry Logic 사용
3. **하위 호환성**: 기존 코드와 호환 유지 (점진적 전환)

### 우선순위

1. **즉시**: Pydantic 모델 정의
2. **1주 내**: Judge 노드 수정
3. **2주 내**: main.py 통합
4. **3주 내**: 정규식 코드 제거

이 방식으로 **비용 59% 절감**, **지연 33% 감소**, **정확도 향상**을 달성할 수 있습니다.
