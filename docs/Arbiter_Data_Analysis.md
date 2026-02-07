# Arbiter 데이터 분석 및 개선 제안

## 1. 현재 데이터 구조 분석

### 1.1 각 전문가 노드가 반환하는 데이터

#### Contact, Deform, Necking 전문가 공통 구조:
```python
{
    "expert_reports": List[str],  # 리포트 텍스트
    "expert_analysis_results": {
        "expert_name": {
            "multi_hotspot_results": [...],  # 각 hotspot별 분석 결과
            "final_verdict_result": {  # best_result = specialist_result
                "conclusion": str,           # 결론
                "verdict": str,              # 판정 (Conclusion + Reasoning)
                "confidence": int,           # 신뢰도 (0-100)
                "visual_description": str    # 시각적 특징
            }
        }
    },
    "expert_confidence_scores": {"expert_name": int},
    "expert_evidence": {
        "expert_name": [
            {
                "evidence": str,    # 증거 텍스트
                "details": str      # 상세 설명
            }
        ]
    }
}
```

### 1.2 Arbiter가 필요로 하는 데이터

#### Fact Checker 요구사항:
- `conclusion`: 전문가의 결론 ✅
- `verdict`: 전문가의 상세 판정 ✅
- `visual_description`: 시각적 특징 ✅
- `evidence`: 증거 리스트 ✅
- `reasoning`: 논리적 근거 ⚠️ (현재 `verdict`를 사용)

#### Judge 요구사항:
- `expert_opinions`: 모든 전문가의 구조화된 의견 ✅
- `expert_reports`: 전문가 리포트 텍스트 ✅
- `debate_messages`: 논쟁 메시지 히스토리 ✅
- `expert_confidence_scores`: 신뢰도 점수 ✅

#### Debater 요구사항:
- `expert_opinion`: 전문가 의견 구조체 ✅
  - `conclusion`: 결론 ✅
  - `confidence`: 신뢰도 ✅
  - `evidence`: 증거 리스트 ✅
  - `reasoning`: 논리적 근거 ⚠️ (현재 `verdict`를 사용)
  - `verdict`: 상세 판정 ✅
  - `visual_description`: 시각적 특징 ✅

## 2. 발견된 문제점

### 2.1 ⚠️ **중요: `reasoning` 필드 부재**

**현재 상황:**
- `specialist_result`에는 `reasoning` 필드가 없음
- `debate_data_extractor.py`에서 `reasoning`을 `verdict`로 대체 사용:
  ```python
  "reasoning": final_result.get("verdict", "")  # 상세 판정을 논리로 사용
  ```

**문제점:**
1. **의미적 혼동**: `verdict`는 "판정 결론"이고, `reasoning`은 "논리적 근거"인데 동일하게 사용됨
2. **Fact Check 정확도 저하**: Fact Checker가 `reasoning`을 기대하지만 실제로는 `verdict`를 받음
3. **Debater 프롬프트 품질 저하**: Debater가 논리적 근거를 제대로 활용하지 못함

### 2.2 ⚠️ **증거 데이터 구조 불일치**

**현재 상황:**
- `expert_evidence`는 `[{"evidence": str, "details": str}]` 형식
- Fact Checker는 `evidence_list`를 받아서 `evidence_texts`로 변환:
  ```python
  evidence_texts = [ev.get("evidence", "") for ev in evidence_list if ev.get("evidence")]
  ```

**문제점:**
- `details` 필드가 Fact Check에 활용되지 않음
- 증거의 상세 설명이 검증 과정에서 누락됨

### 2.3 ⚠️ **`multi_hotspot_results` 미활용**

**현재 상황:**
- 각 전문가는 `multi_hotspot_results`에 모든 hotspot별 분석 결과를 저장
- Arbiter는 `final_verdict_result`만 사용

**문제점:**
- 개별 hotspot의 상세 분석 정보가 논쟁에 활용되지 않음
- 여러 hotspot 중 일부만 문제가 있는 경우, 전체적인 판정에 반영되지 않을 수 있음

### 2.4 ⚠️ **신뢰도 점수 중복**

**현재 상황:**
- `expert_confidence_scores`에 별도로 저장
- `final_verdict_result.confidence`에도 저장

**문제점:**
- 데이터 중복 (심각하지 않지만 일관성 문제)

## 3. 개선 제안

### 3.1 🔧 **`reasoning` 필드 추가 (우선순위: 높음)**

**방법 1: `specialist_result`에 `reasoning` 필드 추가**
```python
# src/nodes/contact_nodes.py, deform_nodes.py, necking_nodes.py
"specialist_result": {
    "conclusion": sr_conclusion,
    "verdict": worker_verdict,
    "confidence": report_confidence,
    "visual_description": observations,
    "reasoning": evidence_result.reasoning  # 추가
}
```

**방법 2: `verdict_finalize_node`에서 `reasoning` 추출**
```python
# src/nodes/contact_nodes.py (verdict_finalize_node)
best_result = s_res.copy()
if "reasoning" not in best_result:
    # verdict에서 reasoning 추출 또는 별도 생성
    best_result["reasoning"] = extract_reasoning_from_verdict(best_result.get("verdict", ""))
```

**권장: 방법 1** (데이터 소스에서 직접 제공)

### 3.2 🔧 **증거 데이터 활용 개선 (우선순위: 중간)**

**개선 방안:**
```python
# src/nodes/arbiter_nodes/debate_data_extractor.py
evidence_texts = []
for ev in evidence_list:
    evidence_text = ev.get("evidence", "")
    details = ev.get("details", "")
    if evidence_text:
        if details:
            evidence_texts.append(f"{evidence_text}: {details}")
        else:
            evidence_texts.append(evidence_text)
```

### 3.3 🔧 **`multi_hotspot_results` 활용 (우선순위: 낮음)**

**개선 방안:**
- Judge 프롬프트에 `multi_hotspot_results` 요약 추가
- Fact Checker가 개별 hotspot 증거도 검증

### 3.4 🔧 **데이터 일관성 개선 (우선순위: 낮음)**

**개선 방안:**
- `expert_confidence_scores` 제거하고 `final_verdict_result.confidence`만 사용
- 또는 반대로 `final_verdict_result`에서 `confidence` 제거

## 4. 즉시 수정 권장 사항

### 4.1 **`reasoning` 필드 추가**

각 전문가 노드의 `specialist_result` 생성 부분 수정:

**Contact/Deform/Necking 노드:**
```python
# src/nodes/contact_nodes.py, deform_nodes.py, necking_nodes.py
# analyze_hotspot_worker 함수 내부

if evidence_result:
    reasoning_text = evidence_result.reasoning if hasattr(evidence_result, 'reasoning') else ""
    # 또는 verdict에서 추출
    if not reasoning_text:
        reasoning_text = extract_reasoning_from_verdict(worker_verdict)
else:
    reasoning_text = "Extraction failed"

analysis_entry = {
    ...
    "specialist_result": {
        "conclusion": sr_conclusion,
        "verdict": worker_verdict,
        "confidence": report_confidence,
        "visual_description": observations,
        "reasoning": reasoning_text  # 추가
    },
    ...
}
```

**`debate_data_extractor.py` 수정:**
```python
# src/nodes/arbiter_nodes/debate_data_extractor.py
expert_opinions[expert_name] = {
    "conclusion": final_result.get("conclusion", ""),
    "confidence": expert_confidence_scores.get(expert_name, 0),
    "verdict": final_result.get("verdict", ""),
    "visual_description": final_result.get("visual_description", ""),
    "evidence": evidence_texts,
    "reasoning": final_result.get("reasoning", "")  # verdict 대신 reasoning 사용
}
```

### 4.2 **증거 데이터 활용 개선**

```python
# src/nodes/arbiter_nodes/debate_data_extractor.py
evidence_texts = []
for ev in evidence_list:
    evidence_text = ev.get("evidence", "")
    details = ev.get("details", "")
    if evidence_text:
        if details:
            evidence_texts.append(f"{evidence_text}\n상세: {details}")
        else:
            evidence_texts.append(evidence_text)
```

## 5. 검증 체크리스트

- [x] `specialist_result`에 `reasoning` 필드 추가됨 (Contact, Deform, Necking 노드)
- [x] `debate_data_extractor.py`에서 `reasoning` 필드 사용 확인
- [x] 증거 `details` 필드가 Fact Check에 활용되도록 개선됨
- [ ] Fact Checker가 `reasoning`을 올바르게 활용하는지 확인 (테스트 필요)
- [ ] Debater 프롬프트가 `reasoning`을 활용하는지 확인 (테스트 필요)
- [ ] 테스트 실행하여 데이터 흐름 정상 작동 확인

## 6. 구현 완료 사항

### 6.1 `reasoning` 필드 추가 (완료)

**수정된 파일:**
- `src/nodes/contact_nodes.py`: `specialist_result`에 `reasoning` 필드 추가
- `src/nodes/deform_nodes.py`: `specialist_result`에 `reasoning` 필드 추가 (step6_verdict.final_reasoning 사용)
- `src/nodes/necking_nodes.py`: `specialist_result`에 `reasoning` 필드 추가 (step6_verdict.final_reasoning 사용)
- `src/nodes/arbiter_nodes/debate_data_extractor.py`: `reasoning` 필드를 올바르게 사용하도록 수정

### 6.2 증거 데이터 활용 개선 (완료)

**수정된 파일:**
- `src/nodes/arbiter_nodes/debate_data_extractor.py`: 증거 `details` 필드를 Fact Check에 포함하도록 개선

## 6. 참고 사항

- 현재 시스템은 동작하지만, `reasoning` 필드 부재로 인해 논쟁 품질이 저하될 수 있음
- `verdict`와 `reasoning`의 구분이 명확하지 않으면 LLM이 혼동할 수 있음
- 증거 `details`를 활용하면 Fact Check 정확도 향상 가능
