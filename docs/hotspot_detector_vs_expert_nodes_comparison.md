# 핫스팟 디텍터 vs 전문가 노드 API 호출 방식 비교

## 📊 비교 개요

### 핫스팟 디텍터 (`common_nodes.py`)
- 위치: `src/nodes/common_nodes.py`
- 용도: 이미지 패치 분석으로 Hotspot 탐지
- API 호출 방식: **네이티브 async API** 사용

### 전문가 노드 (`necking_nodes.py`, `deform_nodes.py`, `contact_nodes.py`)
- 위치: `src/nodes/necking_nodes.py`, `src/nodes/deform_nodes.py`, `src/nodes/contact_nodes.py`
- 용도: Hotspot별 상세 분석 (Component Classification, Evidence Collection, Debate)
- API 호출 방식: **동기 API를 비동기로 변환** (`asyncio.to_thread`)

---

## 🔍 상세 비교

### 1. API 호출 방식

#### 핫스팟 디텍터
```python
# common_nodes.py:162-170
async def _call_api(**kwargs):
    used_model = kwargs.get("model_name", model_name)
    # 네이티브 async API 사용 (스레드풀 의존 제거)
    resp = await client.aio.models.generate_content(
        model=used_model,
        contents=[prompt, image_part],
        config=api_config
    )
    return resp

response = await async_retry_with_backoff(
    _call_api,
    max_retries=3,
    context_name=f"Patch {patch_idx}",
    model_name=model_name
)
```

**특징**:
- ✅ `client.aio.models.generate_content` 사용 (네이티브 async)
- ✅ 스레드풀 불필요 (순수 async)
- ✅ 성능상 이점 (컨텍스트 스위칭 없음)

#### 전문가 노드
```python
# necking_nodes.py:134-147
async def _call_classifier_api(client, model_name, parts, safety_settings):
    """Component Classification API 호출"""
    response = await asyncio.to_thread(
        client.models.generate_content,  # 동기 API
        model=model_name,
        contents=parts,
        config={...}
    )
    validate_gemini_response(response, context_name=...)
    return response

response = await async_retry_with_backoff(
    _call_classifier_api,
    client=client,
    model_name=model_name,
    parts=parts,
    safety_settings=safety_settings_block_none,
    max_retries=5,
    context_name=f"Worker #{hotspot_id} Classifier"
)
```

**특징**:
- ⚠️ `client.models.generate_content` 사용 (동기 API)
- ⚠️ `asyncio.to_thread`로 비동기 변환 (스레드풀 사용)
- ⚠️ 성능 오버헤드 (컨텍스트 스위칭 발생)

---

### 2. Safety Settings

#### 핫스팟 디텍터
```python
# common_nodes.py:125-130
# Safety settings: BLOCK_NONE
safety_settings_block_none = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]
```

**문제점**: 하드코딩되어 있음 (공통 함수 미사용)

#### 전문가 노드
```python
# necking_nodes.py:170
# [Gemini Official Best Practice] Safety settings BLOCK_NONE
safety_settings_block_none = get_safety_settings()
```

**장점**: 공통 함수 사용 (중앙 관리)

---

### 3. Rate Limit / Semaphore 제어

#### 둘 다 동일
```python
# async_retry_with_backoff 내부에서 처리
async with acquire_api_slot():  # 전역 rate limit + semaphore
    return await func(*args, **kwargs)
```

**공통점**:
- ✅ `acquire_api_slot()` 사용 (전역 제어)
- ✅ `AsyncLimiter` + `threading.Semaphore` 조합
- ✅ Hotspot Detector와 Expert 노드가 동일한 제한 공유

---

### 4. Response 검증

#### 핫스팟 디텍터
```python
# common_nodes.py:178-198
# 응답 처리 (Safety rating 로직 통합)
is_safety_blocked = False
if not hasattr(response, "candidates") or not response.candidates:
    hotspots = []
else:
    candidate = response.candidates[0]
    
    # Safety block 체크
    is_safety_blocked = (
        hasattr(candidate, "safety_ratings") 
        and candidate.safety_ratings
        and any(r.probability in ["HIGH", "MEDIUM"] for r in candidate.safety_ratings)
    )
    
    if is_safety_blocked:
        logger.warning(f"Patch {patch_idx}: Safety block detected. Skipping.")
    else:
        response_text = getattr(response, "text", None)
        if response_text:
            parsed = HotspotDetectionResult.model_validate_json(response_text)
            hotspots = parsed.hotspots
```

**특징**: 직접 처리 (Safety rating 체크 포함)

#### 전문가 노드
```python
# necking_nodes.py:146
validate_gemini_response(response, context_name=f"Worker #{hotspot_id} Classifier")
```

**특징**: 공통 함수 사용 (`expert_api_utils.validate_gemini_response`)

---

### 5. 재시도 로직

#### 둘 다 동일
```python
response = await async_retry_with_backoff(
    _call_api,  # 또는 _call_classifier_api 등
    max_retries=3,  # 또는 5
    context_name=...,
    model_name=model_name
)
```

**공통점**:
- ✅ `async_retry_with_backoff` 사용
- ✅ Exponential backoff + jitter
- ✅ Smart fallback (503 에러 시 모델 전환)
- ✅ Daily retry budget guard

---

## ⚠️ 발견된 문제점

### 1. **API 호출 방식 불일치 (중요도: 높음)**

**문제**: 핫스팟 디텍터는 네이티브 async API를 사용하지만, 전문가 노드는 동기 API를 스레드로 변환합니다.

**영향**:
- 성능 차이: 네이티브 async가 더 효율적
- 일관성 부족: 같은 프로젝트 내에서 다른 패턴 사용
- 유지보수 어려움: 두 가지 패턴을 모두 이해해야 함

**개선 방안**:
- 전문가 노드도 네이티브 async API (`client.aio.models.generate_content`) 사용
- 또는 핫스팟 디텍터도 동기 API로 통일 (하지만 성능 저하)

**권장**: 전문가 노드를 네이티브 async API로 변경

---

### 2. **핫스팟 디텍터의 Safety Settings 하드코딩 (중요도: 중간)**

**문제**: 핫스팟 디텍터에서 Safety Settings가 하드코딩되어 있습니다.

**현재 코드**:
```python
# common_nodes.py:125-130
safety_settings_block_none = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    ...
]
```

**개선 방안**:
```python
from src.utils.expert_config import get_safety_settings

safety_settings_block_none = get_safety_settings()
```

---

### 3. **핫스팟 디텍터의 Response 검증 (중요도: 낮음)**

**문제**: 핫스팟 디텍터는 직접 Response 검증을 수행합니다.

**개선 방안**:
- `validate_gemini_response()` 함수 사용 고려
- 단, Safety rating 체크는 핫스팟 디텍터만 필요하므로 유지 가능

---

## 📋 전문가 노드 API 함수 설정 확인

### 현재 상태

#### ✅ 잘 설정된 부분
1. **Rate Limit/Semaphore**: `async_retry_with_backoff` 내부의 `acquire_api_slot()` 사용
2. **재시도 로직**: `async_retry_with_backoff` 사용 (핫스팟 디텍터와 동일)
3. **Safety Settings**: 공통 함수 사용 (`get_safety_settings()`)
4. **Response 검증**: 공통 함수 사용 (`validate_gemini_response()`)

#### ⚠️ 개선 필요 부분
1. **API 호출 방식**: 동기 API를 스레드로 변환 (`asyncio.to_thread`)
   - 핫스팟 디텍터처럼 네이티브 async API 사용 권장

---

## 🎯 권장 개선 사항

### 즉시 개선 (High Priority)

1. **전문가 노드 API 호출을 네이티브 async로 변경**
   ```python
   # 현재 (동기 API)
   response = await asyncio.to_thread(
       client.models.generate_content,
       ...
   )
   
   # 개선 (네이티브 async)
   response = await client.aio.models.generate_content(
       model=model_name,
       contents=parts,
       config=config
   )
   ```

2. **핫스팟 디텍터 Safety Settings 공통화**
   ```python
   from src.utils.expert_config import get_safety_settings
   safety_settings_block_none = get_safety_settings()
   ```

### 단기 개선 (Medium Priority)

3. **공통 API 함수 실제 사용**
   - `expert_api_utils.py`의 공통 함수들을 실제로 사용하도록 변경
   - 내부 `_call_*_api` 함수들을 제거

---

## 📊 성능 비교 예상

### 네이티브 async API (`client.aio.models.generate_content`)
- ✅ 컨텍스트 스위칭 없음
- ✅ 메모리 효율적
- ✅ 더 빠른 응답 시간

### 동기 API + 스레드 (`asyncio.to_thread`)
- ⚠️ 스레드풀 오버헤드
- ⚠️ 컨텍스트 스위칭 발생
- ⚠️ 메모리 사용량 증가

**예상 성능 향상**: 네이티브 async로 변경 시 약 10-20% 성능 개선 예상

---

## 결론

**핫스팟 디텍터와 전문가 노드의 주요 차이점**:

1. **API 호출 방식**: 핫스팟 디텍터는 네이티브 async, 전문가 노드는 동기 API 변환
2. **Safety Settings**: 핫스팟 디텍터는 하드코딩, 전문가 노드는 공통 함수 사용
3. **Response 검증**: 핫스팟 디텍터는 직접 처리, 전문가 노드는 공통 함수 사용

**공통점**:
- Rate Limit/Semaphore 제어 방식 동일
- 재시도 로직 동일 (`async_retry_with_backoff`)

**권장 사항**:
1. 전문가 노드를 네이티브 async API로 변경 (성능 향상)
2. 핫스팟 디텍터의 Safety Settings 공통화 (일관성 향상)
