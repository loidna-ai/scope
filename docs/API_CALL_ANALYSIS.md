# AI 모델 호출 조건 분석 (429 RESOURCE_EXHAUSTED 대응)

## 1. 현재 설정 요약

| 설정 | 값 | 위치 | 용도 |
|------|-----|------|------|
| GEMINI_TIER1_RPM | 30 | config.py | Flash 전용 |
| GEMINI_TIER1_CONCURRENT | 2 | config.py | Flash 전용 |
| GEMINI_PRO_RPM | 15 | config.py | Pro 전용 |
| GEMINI_PRO_CONCURRENT | 1 | config.py | Pro 전용 |
| GEMINI_MODEL_NAME | gemini-2.5-flash | config.py | Flash |
| GEMINI_PRO_MODEL_NAME | gemini-2.5-pro | config.py | Pro |

**Rate Limiter 분리**: Flash와 Pro는 `acquire_api_slot(model_type)`으로 별도 풀 사용 (안티패턴 해소).

## 2. API 호출 흐름 검증

### ✅ Rate Limiter 적용 여부
- **모든** Gemini API 호출이 `async_retry_with_backoff` → `acquire_api_slot()` 경유
- `acquire_api_slot()`: 전역 Semaphore(2) + Rate Limiter(30 RPM) 공유
- 적용 위치: Hotspot Detector, Preprocessor, Contact/Necking Workers, Supervisor, Arbiter, Report Generator

### ✅ 호출 경로
```
Hotspot Detector (2 batches 병렬) → async_retry_with_backoff ✓
Preprocessor (2 hotspots 병렬)   → async_retry_with_backoff ✓
Contact Worker (2 workers 병렬)  → async_retry_with_backoff ✓
Necking Worker (2 workers 병렬) → async_retry_with_backoff ✓
Contact Supervisor              → async_retry_with_backoff ✓
Necking Supervisor               → async_retry_with_backoff ✓
```

## 3. 429 발생 원인 분석

### Vertex AI 공식 문서 요약
- **Preview 모델**: Standard PayGo Usage Tiers **미적용** → 별도 제한
- **429 의미**: 고정 할당량 초과가 아니라 **일시적 리소스 경합**
- **권장**: Traffic smoothing, 급격한 burst 회피, 지수 백오프 재시도

### 실제 동시 호출 시나리오
1. **Hotspot**: 2 batches → `asyncio.gather`로 **동시 2회** 호출
2. **Preprocessor**: 2 hotspots → **동시 2회** classify
3. **Contact + Necking**: Fan-Out으로 **동시 실행**
   - Contact Worker 2개 + Necking Worker 2개 = 최대 4개 태스크
   - Semaphore(2)로 **동시 2개만** API 호출
4. **Supervisor**: Workers 완료 후 Contact/Necking Supervisor가 **동시에** 시작 가능
   - 이 시점에 2개 Supervisor가 동시에 Pro 모델 호출 → 429 가능성 ↑

### 모델별 사용
- **gemini-2.5-flash**: Hotspot, Preprocessor, Workers
- **gemini-2.5-pro**: Supervisor, Judge, Debater

→ Flash와 Pro는 **별도 할당량**이지만, Preview 모델은 공통 풀에서 경합 가능

## 4. 권장 조치

### A. 즉시 적용 가능 (config.py)
| 설정 | 현재 | 권장 | 이유 |
|------|------|------|------|
| GEMINI_TIER1_CONCURRENT | 2 | **1** | Preview 모델 burst 완화 |
| GEMINI_TIER1_RPM | 30 | **15~20** | Preview 안정성 |

### B. 429 재시도 강화 (retry_utils.py)
- 429 대기: 현재 10s, 20s, 40s (지수 백오프)
- Preview 모델: **20s, 40s, 80s**로 연장 검토

### C. Traffic Smoothing (선택)
- `acquire_api_slot()` 획득 후 **최소 2~3초 대기** 추가
- 급격한 burst 완화

## 5. 결론

- **호출 조건**: 모든 경로가 `acquire_api_slot`을 통해 제한 적용됨 ✅
- **429 원인**: Preview 모델의 제한적 용량 + burst 트래픽
- **조치**: `GEMINI_TIER1_CONCURRENT=1`, `GEMINI_TIER1_RPM=15`로 완화 후 재테스트 권장
