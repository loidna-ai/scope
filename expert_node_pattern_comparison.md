# 전문가 노드 패턴 vs Judge 노드 패턴 비교

## ✅ 핵심 답변

**네, 전문가 노드에서 사용하는 방식을 똑같이 사용합니다.**

---

## 📊 패턴 비교

### 현재: 전문가 노드 (`verdict_analyst_node`)

**위치**: `src/nodes/contact_nodes.py` (라인 863-920)

```python
# 1. Config 설정
config_dict = {
    "temperature": 1.0,
    "response_mime_type": "application/json",  # ← 구조화된 출력
    "response_json_schema": AnalystHypothesis.model_json_schema(),  # ← Pydantic 스키마
    "safety_settings": safety_settings_block_none
}

# 2. Thinking Config (지원 모델에만)
thinking_supported_models = ["gemini-2.0-flash-exp", "gemini-2.5-flash", "gemini-2.5-pro"]
if any(m in model_name for m in thinking_supported_models):
    config_dict["thinking_config"] = types.ThinkingConfig(thinking_level="high")

# 3. API 호출
response = await asyncio.to_thread(
    client.models.generate_content,
    model=model_name,
    contents=system_prompt,
    config=types.GenerateContentConfig(**config_dict)
)

# 4. Pydantic 모델로 파싱
response_text = getattr(response, 'text', None)
if not response_text:
    raise ValueError(f"Gemini API 응답 텍스트가 비어있습니다.")

analyst_result = AnalystHypothesis.model_validate_json(response_text)  # ← Pydantic 파싱

# 5. 반환 (구조화 데이터 + 하위 호환성)
return {
    "analyst_hypothesis": analyst_result,  # ← 구조화 데이터
    "current_hypothesis": analyst_result.get_hypothesis(),  # ← 하위 호환성 (텍스트)
    ...
}
```

### 개선: Judge 노드 (`judge_node`)

**위치**: `src/nodes/arbiter_nodes/judge_node.py` (수정 예정)

```python
# 1. Config 설정 (전문가 노드와 동일한 패턴)
config_dict = {
    "temperature": 1.0,  # 공식 문서 권장사항: 1.0으로 통일
    "response_mime_type": "application/json",  # ← 동일
    "response_json_schema": FinalVerdictResult.model_json_schema(),  # ← 동일 패턴
    "safety_settings": safety_settings_block_none  # ← 동일
}

# 2. Thinking Config (전문가 노드와 동일)
thinking_supported_models = ["gemini-2.0-flash-exp", "gemini-2.5-flash", "gemini-2.5-pro"]
if any(m in model_name for m in thinking_supported_models):
    config_dict["thinking_config"] = types.ThinkingConfig(thinking_level="high")

# 3. API 호출 (전문가 노드와 동일)
response = client.models.generate_content(
    model=model_name,
    contents=prompt,
    config=types.GenerateContentConfig(**config_dict)
)

# 4. Pydantic 모델로 파싱 (전문가 노드와 동일)
response_text = getattr(response, 'text', None)
if not response_text:
    raise ValueError(f"Gemini API 응답 텍스트가 비어있습니다.")

verdict_structured = FinalVerdictResult.model_validate_json(response_text)  # ← 동일한 방식

# 5. 반환 (구조화 데이터 + 하위 호환성)
return {
    "final_verdict_structured": verdict_structured,  # ← 구조화 데이터 (analyst_hypothesis와 동일)
    "final_verdict": _format_verdict_text(verdict_structured),  # ← 하위 호환성 (current_hypothesis와 동일)
    ...
}
```

---

## 🔍 차이점 분석

### 동일한 부분 (100% 동일)

| 항목 | 전문가 노드 | Judge 노드 | 비고 |
|------|------------|------------|------|
| **구조화 출력 설정** | `response_mime_type: "application/json"` | 동일 | ✅ |
| **스키마 지정** | `response_json_schema: Model.model_json_schema()` | 동일 | ✅ |
| **파싱 방식** | `Model.model_validate_json(response_text)` | 동일 | ✅ |
| **Safety Settings** | `BLOCK_NONE` | 동일 | ✅ |
| **Thinking Config** | 지원 모델에만 추가 | 동일 | ✅ |
| **하위 호환성** | 구조화 데이터 + 텍스트 반환 | 동일 | ✅ |

### 차이점 (의도적인 차이)

| 항목 | 전문가 노드 | Judge 노드 | 이유 |
|------|------------|------------|------|
| **Temperature** | `1.0` | `1.0` | 공식 문서 권장사항: 1.0으로 통일 |
| **Pydantic 모델** | `AnalystHypothesis` | `FinalVerdictResult` | 목적이 다름 |
| **반환 키** | `analyst_hypothesis` | `final_verdict_structured` | 의미상 차이 |

---

## 💡 왜 동일한 패턴을 사용하는가?

### 1. 일관성 (Consistency)

```python
# 전문가 노드
analyst_result = AnalystHypothesis.model_validate_json(response_text)

# Judge 노드
verdict_structured = FinalVerdictResult.model_validate_json(response_text)

# → 동일한 패턴으로 코드베이스 일관성 유지
```

### 2. 검증된 패턴 (Proven Pattern)

- 전문가 노드에서 이미 성공적으로 사용 중
- Retry Logic, Error Handling 등이 이미 구현됨
- 테스트 케이스가 존재함

### 3. 유지보수성 (Maintainability)

- 동일한 패턴이면 버그 수정이 한 번에 적용됨
- 새로운 개발자가 이해하기 쉬움
- 코드 리뷰가 간단해짐

### 4. 확장성 (Extensibility)

- 향후 다른 노드에도 동일한 패턴 적용 가능
- 공통 유틸리티 함수 추출 가능

---

## 📝 실제 코드 비교

### 전문가 노드 (현재 코드)

```python
# src/nodes/contact_nodes.py:863-920
async def _call_analyst_api(client, model_name, system_prompt, safety_settings):
    """Analyst API 호출"""
    thinking_supported_models = ["gemini-2.0-flash-exp", "gemini-2.5-flash", "gemini-2.5-pro"]
    config_dict = {
        "temperature": 1.0,
        "response_mime_type": "application/json",
        "response_json_schema": AnalystHypothesis.model_json_schema(),
        "safety_settings": safety_settings
    }
    if any(m in model_name for m in thinking_supported_models):
        config_dict["thinking_config"] = types.ThinkingConfig(thinking_level="high")
    
    response = await asyncio.to_thread(
        client.models.generate_content,
        model=model_name,
        contents=system_prompt,
        config=types.GenerateContentConfig(**config_dict)
    )
    return response

# 사용
response = await async_retry_with_backoff(
    _call_analyst_api,
    client=client,
    model_name=model_name,
    system_prompt=system_prompt,
    safety_settings=safety_settings_block_none,
    max_retries=5,
    context_name="Analyst"
)

analyst_result = AnalystHypothesis.model_validate_json(response.text)
```

### Judge 노드 (개선 예정 코드)

```python
# src/nodes/arbiter_nodes/judge_node.py (수정 예정)
async def _call_judge_api(client, model_name, prompt, safety_settings):
    """Judge API 호출 (전문가 노드와 동일한 패턴)"""
    thinking_supported_models = ["gemini-2.0-flash-exp", "gemini-2.5-flash", "gemini-2.5-pro"]
    config_dict = {
        "temperature": 1.0,  # 공식 문서 권장사항: 1.0으로 통일
        "response_mime_type": "application/json",  # ← 동일
        "response_json_schema": FinalVerdictResult.model_json_schema(),  # ← 동일 패턴
        "safety_settings": safety_settings  # ← 동일
    }
    if any(m in model_name for m in thinking_supported_models):
        config_dict["thinking_config"] = types.ThinkingConfig(thinking_level="high")  # ← 동일
    
    response = await asyncio.to_thread(
        client.models.generate_content,
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(**config_dict)
    )
    return response

# 사용 (전문가 노드와 동일한 패턴)
response = await async_retry_with_backoff(
    _call_judge_api,
    client=client,
    model_name=model_name,
    prompt=prompt,
    safety_settings=safety_settings_block_none,
    max_retries=5,
    context_name="Judge"
)

verdict_structured = FinalVerdictResult.model_validate_json(response.text)  # ← 동일한 방식
```

---

## ✅ 결론

**네, 전문가 노드에서 사용하는 방식을 똑같이 사용합니다.**

### 동일한 부분
- ✅ `response_mime_type: "application/json"`
- ✅ `response_json_schema: Model.model_json_schema()`
- ✅ `Model.model_validate_json(response_text)` 파싱
- ✅ Safety Settings (`BLOCK_NONE`)
- ✅ Thinking Config (지원 모델에만)
- ✅ 하위 호환성 (구조화 데이터 + 텍스트 반환)

### 차이점 (의도적)
- Temperature: `1.0`으로 통일 (공식 문서 권장사항)
- Pydantic 모델: `AnalystHypothesis` vs `FinalVerdictResult` (목적 차이)

이렇게 하면 **코드베이스 일관성**을 유지하면서 **검증된 패턴**을 재사용할 수 있습니다.
