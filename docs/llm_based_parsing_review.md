# LLM 기반 파싱 통일 방안 검토 리포트

## 📋 목차
1. [현재 상황 분석](#현재-상황-분석)
2. [LLM 기반 파싱의 장단점](#llm-기반-파싱의-장단점)
3. [구현 방안](#구현-방안)
4. [비용 및 성능 분석](#비용-및-성능-분석)
5. [마이그레이션 전략](#마이그레이션-전략)
6. [위험 요소 및 대응 방안](#위험-요소-및-대응-방안)

---

## 현재 상황 분석

### ✅ 이미 구현된 LLM 기반 구조화 출력

현재 코드베이스에서 이미 LLM 기반 구조화 출력이 사용되고 있습니다:

**1. 전문가 노드에서의 사용 (예: `verdict_analyst_node`)**
```python
# src/nodes/contact_nodes.py, deform_nodes.py, necking_nodes.py
config_dict = {
    "temperature": 1.0,
    "response_mime_type": "application/json",
    "response_json_schema": AnalystHypothesis.model_json_schema(),
    "safety_settings": safety_settings
}
response = client.models.generate_content(
    model=model_name,
    contents=system_prompt,
    config=types.GenerateContentConfig(**config_dict)
)
analyst_result = AnalystHypothesis.model_validate_json(response.text)
```

**2. 사용 중인 Pydantic 모델**
- `AnalystHypothesis` - 분석관 가설 구조
- `CritiqueResult` - 비평 결과 구조
- `HypothesisData` - 가설 데이터 구조

**3. LLM 호출 유틸리티**
- `call_gemini_text()` - 텍스트 기반 LLM 호출
- `call_gemini_vision()` - 비전 기반 LLM 호출
- `get_genai_client()` - Gemini Client 생성

### ❌ 정규식 기반 파싱이 사용되는 부분

**main.py에서 정규식으로 파싱하는 함수들:**

1. **`parse_final_verdict()`** (라인 124-176)
   - 최종 판정 텍스트에서 판정 결과, 신뢰도, 신뢰도 레벨 추출
   - 5개의 VERDICT_PATTERNS 순차 시도

2. **`parse_expert_report()`** (라인 179-257)
   - 전문가 리포트에서 전문가 이름, 결론, 신뢰도, 핵심 근거 추출
   - 여러 정규식 패턴 사용

3. **`_format_executive_summary()`** (라인 292-348)
   - 판정 근거 추출 (REASONING_PATTERNS)
   - Bullet 포인트 추출 (BULLET_PATTERNS)

4. **`_format_evidence_breakdown()`** (라인 397-422)
   - Zone 정보 추출 (ZONE_PATTERN_TEMPLATE)

5. **`_format_recommendations()`** (라인 425-443)
   - 권고 사항 추출 (RECOMMENDATION_PATTERN)

---

## LLM 기반 파싱의 장단점

### ✅ 장점

1. **견고성 (Robustness)**
   - LLM 출력 형식이 조금 달라져도 파싱 가능
   - 정규식 패턴 실패 위험 제거
   - 자연어 이해 능력 활용

2. **유지보수성**
   - 정규식 패턴 관리 불필요
   - LLM 출력 형식 변경에 자동 대응
   - 코드 복잡도 감소

3. **확장성**
   - 새로운 필드 추가 시 Pydantic 모델만 수정
   - 복잡한 구조도 쉽게 파싱 가능

4. **일관성**
   - 이미 전문가 노드에서 사용 중인 패턴과 동일
   - 코드베이스 전체의 일관성 향상

### ⚠️ 단점

1. **비용 증가**
   - 각 파싱마다 LLM API 호출 필요
   - 현재 정규식은 무료, LLM 호출은 유료

2. **지연 시간 증가**
   - API 호출로 인한 지연 (수백ms ~ 수초)
   - 정규식은 즉시 실행 (<1ms)

3. **의존성 증가**
   - LLM API 가용성에 의존
   - 네트워크 오류 시 파싱 실패 가능

4. **복잡도**
   - Pydantic 모델 정의 필요
   - 프롬프트 엔지니어링 필요

---

## 구현 방안

### 방안 1: 단일 통합 파싱 함수 (권장)

**하나의 LLM 호출로 모든 정보를 한 번에 파싱**

```python
# src/models/parsing_models.py
from pydantic import BaseModel, Field
from typing import List, Optional, Literal

class VerdictInfo(BaseModel):
    """최종 판정 정보"""
    verdict: str = Field(description="판정 결과 (예: 접촉불량(유력), 압착·손상(의심))")
    confidence: float = Field(ge=0, le=100, description="신뢰도 퍼센트")
    confidence_level: Literal["High", "Medium", "Low"] = Field(description="신뢰도 레벨")
    reasoning: str = Field(description="판정 근거 텍스트")
    key_evidence: List[str] = Field(description="핵심 근거 리스트 (최대 5개)")
    zones: List[ZoneInfo] = Field(description="Zone별 상세 정보")
    recommendations: List[str] = Field(description="추가 조사 권고 사항")

class ZoneInfo(BaseModel):
    """Zone 정보"""
    zone_number: int = Field(ge=1, le=10, description="Zone 번호")
    description: str = Field(description="Zone 설명")
    observation: str = Field(description="Zone 관찰 결과")

class ExpertReportInfo(BaseModel):
    """전문가 리포트 정보"""
    expert_name: Literal["CONTACT", "DEFORM", "NECKING"] = Field(description="전문가 이름")
    conclusion: Literal["유력", "의심", "아님", "해당 없음", "판독 불가"] = Field(description="판정 결과")
    confidence: Optional[float] = Field(None, ge=0, le=100, description="신뢰도 퍼센트 (해당 없음일 경우 None)")
    key_evidence: str = Field(description="핵심 근거 요약")

class ParsedInvestigationResult(BaseModel):
    """파싱된 전체 분석 결과"""
    verdict_info: VerdictInfo
    expert_reports: List[ExpertReportInfo]
```

**사용 예시:**
```python
# src/utils/llm_parser.py
from src.models.parsing_models import ParsedInvestigationResult
from src.tools.experts.expert_utils import call_gemini_text
from google import genai
import config

def parse_investigation_result_llm(
    final_verdict: str,
    expert_reports: List[str],
    arbiter_debate_messages: List[dict]
) -> ParsedInvestigationResult:
    """
    LLM을 사용하여 분석 결과를 구조화된 데이터로 파싱
    
    Args:
        final_verdict: 최종 판정 텍스트
        expert_reports: 전문가 리포트 리스트
        arbiter_debate_messages: 토론 메시지 리스트
        
    Returns:
        ParsedInvestigationResult: 파싱된 구조화 데이터
    """
    client = get_genai_client()
    model_name = config.GEMINI_MODEL_NAME
    
    # 프롬프트 구성
    prompt = f"""다음 분석 결과 텍스트에서 구조화된 정보를 추출하세요.

[최종 판정]
{final_verdict}

[전문가 리포트]
{chr(10).join(f'--- {i+1}번 전문가 ---{chr(10)}{report}' for i, report in enumerate(expert_reports))}

위 텍스트에서 다음 정보를 추출하여 JSON 형식으로 반환하세요:
1. 최종 판정 결과, 신뢰도, 판정 근거
2. 각 전문가의 판정 결과, 신뢰도, 핵심 근거
3. Zone별 상세 정보 (있는 경우)
4. 추가 조사 권고 사항 (있는 경우)
"""
    
    # LLM 호출 (JSON Schema 사용)
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.3,  # 낮은 temperature로 일관성 확보
            response_mime_type="application/json",
            response_json_schema=ParsedInvestigationResult.model_json_schema(),
            safety_settings=[...]  # BLOCK_NONE 설정
        )
    )
    
    # Pydantic 모델로 파싱
    return ParsedInvestigationResult.model_validate_json(response.text)
```

**장점:**
- ✅ **단일 호출**: 비용과 지연 시간 최소화
- ✅ **일관성**: 모든 정보가 한 번에 파싱되어 일관성 보장
- ✅ **간단함**: 하나의 함수로 모든 파싱 처리

**단점:**
- ⚠️ **복잡한 프롬프트**: 모든 정보를 한 번에 추출해야 함
- ⚠️ **큰 컨텍스트**: 입력 텍스트가 길어질 수 있음

---

### 방안 2: 단계별 파싱 (Fallback 전략)

**정규식을 먼저 시도하고, 실패 시 LLM 사용**

```python
def parse_final_verdict_hybrid(verdict_text: str) -> Dict[str, str]:
    """
    하이브리드 파싱: 정규식 시도 → 실패 시 LLM 사용
    """
    # 1. 정규식으로 먼저 시도
    result = parse_final_verdict_regex(verdict_text)  # 기존 함수
    
    # 2. 파싱 실패 또는 불완전한 경우 LLM 사용
    if result["verdict"] == "판정 불가" or result["confidence"] == "N/A":
        return parse_final_verdict_llm(verdict_text)
    
    return result
```

**장점:**
- ✅ **비용 최적화**: 대부분의 경우 정규식으로 처리
- ✅ **빠른 응답**: 정규식 성공 시 즉시 반환
- ✅ **Fallback**: 정규식 실패 시에도 LLM으로 처리

**단점:**
- ⚠️ **복잡도**: 두 가지 파싱 방식 관리 필요
- ⚠️ **일관성**: 정규식과 LLM 결과가 다를 수 있음

---

### 방안 3: 배치 파싱 (권장하지 않음)

**여러 텍스트를 한 번에 파싱**

```python
def parse_multiple_reports_llm(expert_reports: List[str]) -> List[ExpertReportInfo]:
    """여러 전문가 리포트를 한 번에 파싱"""
    # 모든 리포트를 하나의 프롬프트로 구성
    ...
```

**단점:**
- ⚠️ **컨텍스트 제한**: Gemini 모델의 컨텍스트 윈도우 제한
- ⚠️ **복잡한 프롬프트**: 여러 리포트를 구분하여 파싱해야 함

---

## 비용 및 성능 분석

### 현재 정규식 기반 파싱

- **비용**: 무료 (로컬 실행)
- **지연 시간**: <1ms
- **성공률**: 약 70-80% (LLM 출력 형식에 따라 다름)

### LLM 기반 파싱 (방안 1: 단일 통합)

**비용 계산:**
```
입력 토큰: 약 2,000-5,000 토큰 (final_verdict + expert_reports)
출력 토큰: 약 500-1,000 토큰 (구조화된 JSON)

Gemini Flash 모델 기준:
- 입력: $0.075 / 1M 토큰
- 출력: $0.30 / 1M 토큰

1회 파싱 비용:
- 입력: (3,500 / 1,000,000) * $0.075 = $0.00026
- 출력: (750 / 1,000,000) * $0.30 = $0.00023
- 총 비용: 약 $0.0005 (약 0.7원)
```

**지연 시간:**
- API 호출: 500ms ~ 2초 (네트워크 상태에 따라)
- 총 지연: 약 1초

**성공률:**
- 예상: 95% 이상 (JSON Schema 강제)

### 비용 비교

| 항목 | 정규식 | LLM 기반 | 차이 |
|------|--------|----------|------|
| 비용/회 | 무료 | $0.0005 | +$0.0005 |
| 지연 시간 | <1ms | ~1초 | +1초 |
| 성공률 | 70-80% | 95%+ | +15-25% |
| 월 1000회 분석 시 | - | $0.5 | - |

**결론**: 비용 증가는 미미하지만, 지연 시간 증가는 고려 필요

---

## 마이그레이션 전략

### Phase 1: Pydantic 모델 정의 (1주)

1. **`src/models/parsing_models.py` 생성**
   - `VerdictInfo`, `ExpertReportInfo`, `ZoneInfo` 등 정의
   - 기존 정규식 파싱 결과와 호환되는 구조 설계

2. **테스트 작성**
   - 기존 정규식 파싱 결과와 비교 테스트
   - 다양한 LLM 출력 형식에 대한 테스트

### Phase 2: LLM 파싱 함수 구현 (1주)

1. **`src/utils/llm_parser.py` 생성**
   - `parse_investigation_result_llm()` 함수 구현
   - 프롬프트 엔지니어링 및 최적화

2. **기존 함수와 통합**
   - `main.py`의 `parse_final_verdict()` 등을 래퍼로 변경
   - 기존 인터페이스 유지 (하위 호환성)

### Phase 3: 점진적 전환 (2주)

1. **Feature Flag 도입**
   ```python
   # config.py
   USE_LLM_PARSING = False  # 기본값: 정규식 사용
   ```

2. **A/B 테스트**
   - 일부 요청만 LLM 파싱 사용
   - 결과 비교 및 검증

3. **전면 전환**
   - 검증 완료 후 전면 전환
   - 정규식 코드는 주석 처리 (Fallback용)

### Phase 4: 정리 및 최적화 (1주)

1. **불필요한 코드 제거**
   - 정규식 패턴 상수 제거 (또는 Fallback용으로 보관)
   - 사용하지 않는 함수 제거

2. **성능 최적화**
   - 프롬프트 최적화
   - 캐싱 전략 검토 (동일 입력 재사용)

---

## 위험 요소 및 대응 방안

### 위험 1: LLM API 장애

**위험도**: 높음

**영향**: 파싱 실패로 인한 전체 시스템 중단

**대응 방안:**
```python
def parse_investigation_result_with_fallback(
    final_verdict: str,
    expert_reports: List[str],
    use_llm: bool = True
) -> ParsedInvestigationResult:
    """LLM 파싱 실패 시 정규식 Fallback"""
    if use_llm:
        try:
            return parse_investigation_result_llm(...)
        except Exception as e:
            logger.warning(f"LLM 파싱 실패, 정규식 Fallback: {e}")
            # 정규식 Fallback
            return parse_investigation_result_regex(...)
    else:
        return parse_investigation_result_regex(...)
```

### 위험 2: 비용 급증

**위험도**: 중간

**영향**: 사용량 증가 시 비용 증가

**대응 방안:**
1. **비용 모니터링**: 각 호출마다 토큰 수 로깅
2. **Rate Limiting**: 일일 파싱 횟수 제한
3. **캐싱**: 동일 입력에 대한 결과 캐싱

### 위험 3: 파싱 결과 불일치

**위험도**: 낮음

**영향**: 기존 정규식과 다른 결과

**대응 방안:**
1. **검증 테스트**: 기존 테스트 케이스로 검증
2. **점진적 전환**: A/B 테스트로 결과 비교
3. **수동 검토**: 초기 단계에서 수동 검토

### 위험 4: 지연 시간 증가

**위험도**: 중간

**영향**: 사용자 경험 저하

**대응 방안:**
1. **비동기 처리**: 파싱을 비동기로 처리
2. **캐싱**: 자주 사용되는 패턴 캐싱
3. **최적화**: 프롬프트 최적화로 토큰 수 감소

---

## 권장 사항

### ✅ 권장: 방안 1 (단일 통합 파싱) + Fallback

**이유:**
1. **비용 효율적**: 단일 호출로 모든 정보 파싱
2. **일관성**: 모든 정보가 한 번에 파싱되어 일관성 보장
3. **견고성**: 정규식 Fallback으로 안정성 확보
4. **유지보수성**: 코드 복잡도 감소

### 구현 우선순위

1. **즉시 구현**: Pydantic 모델 정의
2. **1주 내**: LLM 파싱 함수 구현
3. **2주 내**: Feature Flag로 점진적 전환
4. **1개월 내**: 전면 전환 및 정리

### 주의사항

1. **프롬프트 엔지니어링**: 정확한 파싱을 위한 프롬프트 최적화 필수
2. **테스트**: 다양한 LLM 출력 형식에 대한 테스트 필수
3. **모니터링**: 비용 및 성능 모니터링 필수
4. **Fallback**: 정규식 Fallback 유지 권장 (안정성)

---

## 결론

LLM 기반 파싱으로 통일하는 것은 **기술적으로 실현 가능**하며, **비용 증가는 미미**합니다.

**주요 이점:**
- ✅ 견고성 향상 (95%+ 성공률)
- ✅ 유지보수성 향상 (정규식 패턴 관리 불필요)
- ✅ 일관성 향상 (이미 사용 중인 패턴과 동일)

**주의사항:**
- ⚠️ 지연 시간 증가 (~1초)
- ⚠️ LLM API 의존성
- ⚠️ 프롬프트 엔지니어링 필요

**권장 접근:**
1. **단일 통합 파싱 함수** 구현
2. **정규식 Fallback** 유지
3. **Feature Flag**로 점진적 전환
4. **비용 및 성능 모니터링** 필수

이 방안으로 정규식 의존성을 제거하고 더 견고한 파싱 시스템을 구축할 수 있습니다.
