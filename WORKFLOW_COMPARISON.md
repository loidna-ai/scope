# Contact Expert 워크플로우 비교: 일반 모드 vs ReAct 모드

## 개요

이 문서는 `contact_expert`를 기준으로 **일반 모드**와 **ReAct 모드**의 워크플로우 차이점을 설명합니다.

---

## 1. 일반 모드 (Normal Mode)

### 실행 경로
```
main.py → run_investigation_pipeline() → build_investigation_graph()
```

### 전체 워크플로우

```
START
  │
  ├─→ [병렬 실행]
  │     │
  │     ├─→ contact_expert (서브그래프)
  │     │     │
  │     │     ├─→ step1_location (위치적 맥락 확인)
  │     │     ├─→ step2_spectral (색채 스펙트럼 분석)
  │     │     ├─→ step3_thermal (열적 구배 분석)
  │     │     ├─→ step4_surface (금속 표면 분석)
  │     │     └─→ finalize (신뢰도 계산, 리포트 생성)
  │     │
  │     ├─→ dielectric_expert (서브그래프)
  │     ├─→ mechanical_expert (서브그래프)
  │     ├─→ tracking_expert (서브그래프)
  │     └─→ strand_fracture_expert (서브그래프)
  │
  └─→ chief_investigator (Arbiter Agent)
        │
        ├─→ 시각적 특징 추출
        ├─→ 1차/2차 단락흔 판정
        ├─→ 상충 해결 논리 적용
        ├─→ 증거 위계 적용
        └─→ 최종 결론 도출
              │
              └─→ END
```

### Contact Expert 실행 상세

**서브그래프 구조:**
```
contact_expert 서브그래프:
  START
    │
    ├─→ step1_location
    │     └─→ step2_spectral
    │           └─→ step3_thermal
    │                 └─→ step4_surface
    │                       └─→ finalize
    │                             └─→ END
```

**각 Step의 역할:**
1. **step1_location**: 이미지에서 용융흔 위치 식별 (접속점 여부 확인)
2. **step2_spectral**: 아산화동(Cu₂O) 의심 색상 패턴 분석
3. **step3_thermal**: 열적 구배(Thermal Gradient) 패턴 분석
4. **step4_surface**: 금속 표면의 전기적 부식 흔적 분석
5. **finalize**: 신뢰도 점수 계산, 증거 수집, 리포트 생성

**특징:**
- ✅ 5명의 전문가가 병렬로 실행됨
- ✅ 각 전문가는 독립적인 서브그래프로 실행됨
- ✅ Contact Expert는 4단계 순차 분석을 수행함
- ✅ 모든 전문가 완료 후 Arbiter가 종합 분석함

---

## 2. ReAct 모드 (ReAct Mode)

### 실행 경로
```
main.py → run_react_agent_parallel_mode() → build_investigation_graph_with_react()
```

### 전체 워크플로우

```
START
  │
  ├─→ [병렬 실행]
  │     │
  │     ├─→ contact_expert (서브그래프) ← [ReAct 에이전트 통합]
  │     │     │
  │     │     ├─→ step1_location
  │     │     │     └─→ [조건부: react_agent 또는 step2]
  │     │     │           └─→ react_agent (LLM이 도구 선택)
  │     │     │                 └─→ step2_spectral
  │     │     │                       └─→ [조건부: react_agent 또는 step3]
  │     │     │                             └─→ step3_thermal
  │     │     │                                   └─→ [조건부: react_agent 또는 step4]
  │     │     │                                         └─→ step4_surface
  │     │     │                                               └─→ [조건부: react_agent 또는 finalize]
  │     │     │                                                     └─→ finalize
  │     │     │
  │     ├─→ dielectric_expert (서브그래프) ← [ReAct 에이전트 통합]
  │     ├─→ mechanical_expert (서브그래프) ← [ReAct 에이전트 통합]
  │     ├─→ tracking_expert (서브그래프) ← [ReAct 에이전트 통합]
  │     └─→ strand_fracture_expert (서브그래프) ← [ReAct 에이전트 통합]
  │
  └─→ chief_investigator (Arbiter Agent)
        │
        ├─→ 시각적 특징 추출
        ├─→ 1차/2차 단락흔 판정
        ├─→ 상충 해결 논리 적용
        ├─→ 증거 위계 적용
        └─→ 최종 결론 도출 (5명의 전문가 리포트 종합)
              │
              └─→ END
```

### Contact Expert 실행 상세

**ReAct 에이전트가 통합된 서브그래프 구조:**
```
contact_expert 서브그래프:
  START
    │
    ├─→ step1_location
    │     └─→ [조건부 엣지: 신뢰도 < 70이면 react_agent]
    │           │
    │           ├─→ react_agent (LLM이 상황 판단 및 도구 선택)
    │           │     │
    │           │     ├─→ [ReAct 에이전트 내부 그래프]
    │           │     │     │
    │           │     │     ├─→ agent_node (LLM 추론)
    │           │     │     │     │
    │           │     │     │     └─→ [LLM이 도구 호출 결정]
    │           │     │     │           │
    │           │     │     │           ├─→ tools_node (도구 실행)
    │           │     │     │           │     │
    │           │     │     │           │     ├─→ enhance_image
    │           │     │     │           │     ├─→ apply_clahe_filter
    │           │     │     │           │     ├─→ crop_image
    │           │     │     │           │     └─→ analyze_image_morphology
    │           │     │     │           │
    │           │     │     │           └─→ [최종 답변 생성]
    │           │     │     │
    │           │     │     └─→ [조건부 엣지: 도구 호출 여부에 따라 분기]
    │           │     │
    │           │     └─→ [InvestigationState로 변환]
    │           │
    │           └─→ step2_spectral
    │                 └─→ [조건부 엣지: 신뢰도 < 70이면 react_agent]
    │                       └─→ step3_thermal
    │                             └─→ [조건부 엣지: 신뢰도 < 70이면 react_agent]
    │                                   └─→ step4_surface
    │                                         └─→ [조건부 엣지: 신뢰도 < 70이면 react_agent]
    │                                               └─→ finalize
    │                                                     └─→ END
```

**특징:**
- ✅ **ReAct 에이전트가 각 전문가 서브그래프 내부에 통합됨** (LangGraph 공식 권장 방식)
- ✅ Step별로 신뢰도가 70 미만이면 react_agent 호출
- ✅ react_agent 내부의 LLM이 상황을 판단하고 필요할 때만 도구를 선택
- ✅ LLM이 자유롭게 도구를 선택 (enhance_image, apply_clahe_filter, crop_image, analyze_image_morphology 등)
- ✅ 도구가 필요 없다고 판단되면 바로 최종 답변 제공
- ✅ 5명의 전문가가 병렬로 실행됨 (메인 그래프 레벨에는 react_agent 없음)

---

## 3. 주요 차이점 비교표

| 항목 | 일반 모드 | ReAct 모드 |
|------|----------|-----------|
| **그래프 빌더** | `build_investigation_graph()` | `build_investigation_graph_with_react()` |
| **병렬 실행 노드** | 5개 (전문가만) | 5개 (전문가만, react_agent는 서브그래프 내부) |
| **Contact Expert 실행** | 1회 (병렬 실행에서 직접) | 1회 (병렬 실행에서 직접) |
| **Contact Expert 구조** | 순차 실행 (서브그래프) | 조건부 엣지 포함 (서브그래프 내부에 react_agent 통합) |
| **ReAct 에이전트** | 없음 | 각 전문가 서브그래프 내부에 통합됨 |
| **도구 사용** | 없음 | Step별 신뢰도가 낮을 때 react_agent 호출, LLM이 도구 선택 |
| **이미지 자동 향상** | 없음 | Step별 신뢰도 기반으로 react_agent 호출, LLM이 필요시 도구 사용 |
| **최종 종합** | Arbiter가 5명 전문가 리포트 종합 | Arbiter가 5명 전문가 리포트 종합 |
| **사용자 상호작용** | 없음 | 각 전문가 서브그래프 내부에서 동적으로 도구 사용 |

---

## 4. 실행 시나리오 비교

### 시나리오 1: 일반 모드 실행

```
1. 이미지 전처리 완료
2. InvestigationState 초기화
   - payload: [이미지 데이터, 텍스트 데이터]
   - expert_reports: []
   - ...

3. 그래프 실행 시작
   ├─→ contact_expert 시작
   │     ├─→ step1 실행 (LLM 호출)
   │     ├─→ step2 실행 (LLM 호출)
   │     ├─→ step3 실행 (LLM 호출)
   │     ├─→ step4 실행 (LLM 호출)
   │     └─→ finalize 실행 (리포트 생성)
   │
   ├─→ dielectric_expert 시작 (병렬)
   ├─→ mechanical_expert 시작 (병렬)
   ├─→ tracking_expert 시작 (병렬)
   └─→ strand_fracture_expert 시작 (병렬)

4. 모든 전문가 완료 대기

5. chief_investigator 실행
   └─→ 최종 결론 도출

6. 종료
```

### 시나리오 2: ReAct 모드 실행 (모든 Step의 신뢰도가 높아 react_agent가 호출되지 않는 경우)

```
1. 이미지 전처리 완료
2. InvestigationState 초기화
   - payload: [이미지 데이터, 텍스트 데이터]
   - task: "이미지를 분석하고 화재 원인을 조사하세요.\n이미지 경로: ..."
   - expert_reports: []
   - ...

3. 그래프 실행 시작
   ├─→ contact_expert 시작 (병렬 실행)
   │     ├─→ step1 실행 (LLM 호출)
   │     │     └─→ 신뢰도 85% → react_agent 호출 안함
   │     │           └─→ step2_spectral 실행 (LLM 호출)
   │     │                 └─→ 신뢰도 80% → react_agent 호출 안함
   │     │                       └─→ step3_thermal 실행 (LLM 호출)
   │     │                             └─→ 신뢰도 75% → react_agent 호출 안함
   │     │                                   └─→ step4_surface 실행 (LLM 호출)
   │     │                                         └─→ 신뢰도 82% → react_agent 호출 안함
   │     │                                               └─→ finalize 실행 (리포트 생성)
   │     │
   ├─→ dielectric_expert 시작 (병렬)
   ├─→ mechanical_expert 시작 (병렬)
   ├─→ tracking_expert 시작 (병렬)
   └─→ strand_fracture_expert 시작 (병렬)

4. 모든 전문가 완료 대기

5. chief_investigator 실행
   └─→ 최종 결론 도출 (5명 전문가 리포트 종합)

6. 종료
```

### 시나리오 3: ReAct 모드 실행 (Step별 신뢰도가 낮아 react_agent가 호출되고 도구를 사용하는 경우)

```
1. 이미지 전처리 완료
2. InvestigationState 초기화
   - payload: [이미지 데이터, 텍스트 데이터]
   - task: "이미지를 분석하고 화재 원인을 조사하세요.\n이미지 경로: ..."
   - expert_reports: []
   - ...

3. 그래프 실행 시작
   ├─→ contact_expert 시작 (병렬 실행)
   │     ├─→ step1 실행 (LLM 호출)
   │     │     └─→ 신뢰도 65% → react_agent 호출
   │     │           └─→ react_agent 실행
   │     │                 ├─→ LLM이 상황 분석
   │     │                 ├─→ LLM이 enhance_image 도구 선택 및 실행
   │     │                 └─→ 향상된 이미지 정보 반환
   │     │                       └─→ step2_spectral 실행 (향상된 이미지 사용)
   │     │                             └─→ 신뢰도 55% → react_agent 호출
   │     │                                   └─→ react_agent 실행
   │     │                                         ├─→ LLM이 상황 분석
   │     │                                         ├─→ LLM이 apply_clahe_filter 도구 선택 및 실행
   │     │                                         └─→ 필터 적용된 이미지 정보 반환
   │     │                                               └─→ step3_thermal 실행
   │     │                                                     └─→ 신뢰도 78% → react_agent 호출 안함
   │     │                                                           └─→ step4_surface 실행
   │     │                                                                 └─→ 신뢰도 72% → react_agent 호출 안함
   │     │                                                                       └─→ finalize 실행 (리포트 생성)
   │     │
   ├─→ dielectric_expert 시작 (병렬)
   │     └─→ [각 Step별로 신뢰도 기반 react_agent 호출]
   ├─→ mechanical_expert 시작 (병렬)
   │     └─→ [각 Step별로 신뢰도 기반 react_agent 호출]
   ├─→ tracking_expert 시작 (병렬)
   │     └─→ [각 Step별로 신뢰도 기반 react_agent 호출]
   └─→ strand_fracture_expert 시작 (병렬)
         └─→ [각 Step별로 신뢰도 기반 react_agent 호출]

4. 모든 전문가 완료 대기

5. chief_investigator 실행
   └─→ 최종 결론 도출 (5명 전문가 리포트 종합)

6. 종료
```

---

## 5. Contact Expert 관점에서의 차이점

### 공통점
- ✅ **Step 실행 순서 동일**: step1 → step2 → step3 → step4 → finalize
- ✅ **분석 로직 동일**: 각 Step의 프롬프트와 분석 함수가 동일함
- ✅ **결과 형식 동일**: `expert_reports`, `expert_analysis_results`, `expert_confidence_scores` 형식 동일

### 차이점

| 항목 | 일반 모드 | ReAct 모드 |
|------|----------|-----------|
| **서브그래프 구조** | 순차 실행만 (조건부 엣지 없음) | 조건부 엣지 포함 (react_agent 통합) |
| **실행 횟수** | 1회 (항상) | 1회 (항상) |
| **실행 컨텍스트** | 직접 병렬 실행 | 직접 병렬 실행 (서브그래프 내부에 react_agent 통합) |
| **이미지 편집 도구 사용** | 없음 | Step별 신뢰도가 낮을 때 react_agent 호출, LLM이 도구 선택 |
| **도구 선택 방식** | 없음 | LLM이 상황을 판단하고 필요할 때만 도구 선택 |
| **다른 전문가와의 관계** | 동등한 병렬 실행 | 동등한 병렬 실행 (각 전문가가 독립적으로 react_agent 사용) |
| **최종 종합** | Arbiter가 5명 전문가 리포트 종합 | Arbiter가 5명 전문가 리포트 종합 |

---

## 6. 코드 레벨 차이점

### 일반 모드
```python
# main.py
if args.normal_mode:
    run_investigation_pipeline(...)

# src/agent.py
def build_investigation_graph():
    builder.add_node("contact", build_contact_expert_graph())
    # ... 다른 전문가들
    add_investigation_edges(builder)  # react_agent 없음
```

### ReAct 모드
```python
# main.py
else:  # 기본값
    run_react_agent_parallel_mode(...)

# src/agent.py
def build_investigation_graph_with_react():
    # 각 전문가 서브그래프 내부에 react_agent가 통합됨
    builder.add_node("contact", build_contact_expert_graph())  # 내부에 react_agent 포함
    # ... 다른 전문가들 (각각 내부에 react_agent 포함)
    add_investigation_edges(builder)  # react_agent는 서브그래프 내부에 있음

# src/graphs/contact_expert_graph.py
def build_contact_expert_graph():
    builder.add_node("step1_location", node_step1_location)
    builder.add_node("react_agent", react_agent_wrapper_node)  # 서브그래프 내부
    # ... 다른 step들
    
    # 조건부 엣지: 신뢰도 < 70이면 react_agent 호출
    builder.add_conditional_edges(
        "step1_location",
        should_use_react_agent_contact_step1,
        {"react_agent": "react_agent", "step2_spectral": "step2_spectral"}
    )
    # ... 다른 조건부 엣지들
```

---

## 7. 성능 및 리소스 사용 비교

### 일반 모드
- **Contact Expert 실행 횟수**: 1회
- **총 LLM 호출 수**: Contact Expert당 4회 (step1~4)
- **병렬 실행 노드**: 5개
- **예상 실행 시간**: 모든 전문가 중 가장 느린 전문가의 실행 시간

### ReAct 모드 (모든 Step의 신뢰도가 높아 react_agent가 호출되지 않는 경우)
- **Contact Expert 실행 횟수**: 1회
- **총 LLM 호출 수**: Contact Expert당 4회 (step1~4)
- **병렬 실행 노드**: 5개 (전문가만)
- **예상 실행 시간**: 모든 전문가 중 가장 느린 전문가의 실행 시간

### ReAct 모드 (Step별 신뢰도가 낮아 react_agent가 호출되는 경우)
- **Contact Expert 실행 횟수**: 1회
- **총 LLM 호출 수**: Contact Expert당 4회 (step1~4) + react_agent LLM 호출 (신뢰도 낮은 Step마다)
- **병렬 실행 노드**: 5개 (전문가만, react_agent는 서브그래프 내부)
- **예상 실행 시간**: 모든 전문가 중 가장 느린 전문가의 실행 시간 (react_agent 호출 포함)
- **이미지 편집 도구 사용**: Step별 신뢰도가 70 미만일 때 react_agent 호출, LLM이 필요시 도구 선택

---

## 8. 권장 사항

### 일반 모드를 사용하는 경우
- ✅ 표준화된 분석 프로세스가 필요한 경우
- ✅ 리소스 사용을 최소화하고 싶은 경우
- ✅ 모든 전문가가 항상 실행되어야 하는 경우
- ✅ 실행 시간을 예측 가능하게 유지하고 싶은 경우

### ReAct 모드를 사용하는 경우
- ✅ 사용자 질문에 동적으로 응답해야 하는 경우
- ✅ 분석 과정을 투명하게 보고 싶은 경우 (ReAct 에이전트의 사고 과정)
- ✅ 추가적인 분석이 필요할 수 있는 경우
- ✅ 사용자와의 상호작용이 필요한 경우

### 주의사항
- ✅ ReAct 에이전트가 각 전문가 서브그래프 내부에 통합되어 독립적으로 동작합니다 (LangGraph 공식 권장 방식).
- ✅ Step별로 신뢰도가 70 미만일 때만 react_agent가 호출됩니다.
- ✅ react_agent 내부의 LLM이 상황을 판단하고 필요할 때만 도구를 선택합니다 (ReAct 패턴 준수).
- ✅ 도구 선택은 LLM이 자유롭게 결정하며, 도구가 필요 없다고 판단되면 바로 최종 답변을 제공합니다.

---

## 9. 시각적 워크플로우 다이어그램

### 일반 모드
```
┌─────────────────────────────────────────────────────────┐
│                    START                                │
└─────────────────────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
   ┌────────┐      ┌────────┐      ┌────────┐
   │contact │      │dielec. │      │mech.   │
   │expert  │      │expert  │      │expert  │
   └────────┘      └────────┘      └────────┘
        │               │               │
        ▼               ▼               ▼
   ┌────────┐      ┌────────┐      ┌────────┐
   │tracking│      │strand  │      │        │
   │expert  │      │fracture│      │        │
   └────────┘      └────────┘      └────────┘
        │               │               │
        └───────────────┼───────────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │  chief_investigator    │
            │  (Arbiter Agent)       │
            └───────────────────────┘
                        │
                        ▼
                      END
```

### ReAct 모드
```
┌─────────────────────────────────────────────────────────┐
│                    START                                │
└─────────────────────────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
   ┌────────┐      ┌────────┐      ┌────────┐
   │contact │      │dielec. │      │mech.   │
   │expert  │      │expert  │      │expert  │
   │(내부에 │      │(내부에 │      │(내부에 │
   │react_  │      │react_  │      │react_  │
   │agent)  │      │agent)  │      │agent)  │
   └────────┘      └────────┘      └────────┘
        │               │               │
        ▼               ▼               ▼
   ┌────────┐      ┌────────┐
   │tracking│      │strand  │
   │expert  │      │fracture│
   │(내부에 │      │expert  │
   │react_  │      │(내부에 │
   │agent)  │      │react_  │
   └────────┘      │agent)  │
                   └────────┘
        │               │
        └───────────────┼───────────────┘
                        │
                        ▼
            ┌───────────────────────┐
            │  chief_investigator   │
            │  (Arbiter Agent)      │
            │  (5명 리포트 종합)    │
            └───────────────────────┘
                        │
                        ▼
                      END
```

---

## 10. 결론

**Contact Expert 관점에서:**
- **일반 모드**: 순차 실행만, 예측 가능한 실행 흐름
- **ReAct 모드**: 조건부 엣지 포함, Step별 신뢰도 기반으로 react_agent 호출

**전체 시스템 관점에서:**
- **일반 모드**: 5명의 전문가가 병렬 실행 후 종합
- **ReAct 모드**: 5명의 전문가가 병렬 실행 후 종합 (각 전문가 서브그래프 내부에 react_agent 통합)

**선택 기준:**
- **일반 모드**: 표준화된 분석, 리소스 효율성 중시
- **ReAct 모드**: 동적 이미지 편집, Step별 신뢰도 기반 자동 개선, LLM이 상황에 맞게 도구 선택

**최근 변경사항 (2024):**
- ✅ **ReAct 에이전트가 각 전문가 서브그래프 내부에 통합됨** (LangGraph 공식 권장 방식)
- ✅ Step별로 신뢰도가 70 미만일 때 react_agent 호출 (조건부 엣지 사용)
- ✅ react_agent 내부의 LLM이 상황을 판단하고 필요할 때만 도구를 선택 (ReAct 패턴 준수)
- ✅ 메인 그래프 레벨의 react_agent 노드 제거 (서브그래프 내부로 이동)
- ✅ 각 전문가가 독립적으로 ReAct 기능을 사용하여 모듈화 및 확장성 향상

