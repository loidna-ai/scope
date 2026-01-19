# Necking Expert Analyst-Critic 패턴 구현 완료

## ✅ 구현 완료 (2026-01-10)

**옵션 B: Final Verdict 레벨 Analyst-Critic 패턴**을 Necking Expert 그래프에 **직접 통합** 완료했습니다.

---

## 📦 구현된 내용

### 1. State 확장 (`src/nodes/necking_nodes.py`)

`NeckingExpertState`에 Debate 필드 추가:

```python
class NeckingExpertState(TypedDict):
    # ... 기존 필드들 ...

    # 5. 최종 판정 (Analyst-Critic Debate)
    debate_iteration: int  # Debate 반복 횟수
    debate_messages: Annotated[List[str], operator.add]  # 대화 이력
    current_hypothesis: Optional[str]  # Analyst 가설
    critique_points: Optional[str]  # Critic 지적
```

### 2. Debate 노드 구현 (3개)

#### Node 1: `verdict_analyst_node`

- **역할**: 분석관 (가설 수립 및 방어)
- **동작**:
  - 최초: `analysis_results` 기반 초기 가설 수립
  - 재분석: Critic 지적 수용 후 가설 수정/방어
- **출력**: `current_hypothesis`, `debate_messages`, `debate_iteration`

#### Node 2: `verdict_critic_node`

- **역할**: 비평가 (가설 검증)
- **동작**:
  - Analyst 가설의 맹점 공격
  - 4가지 검증 관점: 증거 과대해석, 프로파일 누락, 대안 가설, Hotspot 불일치
  - 합의 시 `"NO_OBJECTION"` 반환
- **출력**: `critique_points`, `debate_messages`

#### Node 3: `verdict_finalize_node`

- **역할**: 최종 정리
- **동작**:
  - 합의된 가설 → 최종 보고서 생성
  - Timeout (3턴) → "판독 불가" 처리
  - Debate Log 포함한 상세 보고서
- **출력**: `verdict_report`, `verdict_confidence`, `verdict_result`

### 3. Debate Supervisor (Conditional Edge)

`route_verdict_debate()` 함수:

```python
def route_verdict_debate(state) -> Literal["back_to_analyst", "finalize"]:
    """
    - NO_OBJECTION → finalize
    - 3턴 초과 → finalize (timeout)
    - 그 외 → back_to_analyst (재검토)
    """
```

### 4. 그래프 재구성 (`src/graphs/necking_expert_graph.py`)

**기존**:

```
... → result_aggregator → hotspot_manager (loop)
                        ↓ (end)
                      verdict → END
```

**신규**:

```
... → result_aggregator → hotspot_manager (loop)
                        ↓ (end)
                    verdict_analyst
                        ↓
                    verdict_critic
                        ↓ (supervisor)
          ┌─────────────┴─────────────┐
          ↓                           ↓
    back_to_analyst (loop)      verdict_finalize → END
```

---

## 🎯 핵심 특징

### 1. Main Graph에 직접 통합 ✅ (사용자 제안 반영)

- **장점**:
  - 단일 State 관리 (중첩 그래프 없음)
  - 직관적인 흐름
  - 디버깅 쉬움 (LangSmith에서 전체 추적)

### 2. LangGraph 권장 패턴 준수

- ✅ TypedDict State
- ✅ `operator.add` for messages
- ✅ Conditional edges
- ✅ Recursion limit 제어 (MAX_ITERATIONS=3)

### 3. 보수적 판정 (Conservative Judgment)

- 3턴 토론 후 합의 실패 → "판독 불가"
- 과신 방지 메커니즘 내장

### 4. 투명성 (Transparency)

- 모든 Analyst-Critic 대화 기록 저장
- 최종 보고서에 토론 기록 포함

---

## 📊 워크플로우 다이어그램

**업데이트된 다이어그램**: `outputs/necking_analyst_critic_workflow.png`

핵심 변경점:

- 🔵 파란색: Hotspot 처리 노드 (기존)
- 🟢 초록색: Debate 노드 (신규)
- 2개의 Loop 구조:
  1. Hotspot Processing Loop (기존)
  2. **Analyst-Critic Debate Loop (신규)**

---

## 🧪 테스트 준비

### 단위 테스트 시나리오

1. **정상 합의 (Round 1)**:

   - Analyst: "반단선 High (85%)"
   - Critic: "NO_OBJECTION"
   - 예상: Finalize로 즉시 진행

2. **1턴 재검토 (Round 2)**:

   - Analyst: "반단선 High (85%)"
   - Critic: "슬리빙 불명확"
   - Analyst: "반단선 Medium (65%)" (하향)
   - Critic: "NO_OBJECTION"
   - 예상: 2턴 후 합의

3. **Timeout (Round 3)**:
   - 3턴 토론 후에도 합의 실패
   - 예상: "판독 불가 (Debate Timeout)"

### 실행 방법

```bash
# 가상 환경 활성화
.\activate.ps1

# 테스트 실행 (Notebook 또는 main.py)
# 예: Agent_2_Necking_Expert.ipynb
```

---

## 📁 수정된 파일

1. ✅ `src/nodes/necking_nodes.py`

   - State 확장 (debate 필드)
   - verdict_node 제거
   - verdict_analyst_node, verdict_critic_node, verdict_finalize_node 추가

2. ✅ `src/graphs/necking_expert_graph.py`

   - import 수정
   - route_verdict_debate() 추가
   - build_necking_expert_graph() 재구성
   - initial_state에 debate 필드 추가

3. ✅ `outputs/necking_analyst_critic_workflow.png`

   - 업데이트된 워크플로우 다이어그램

4. ✅ `src/state/necking_debate_state.py` (참고용)
   - 별도 State 정의 (실제로는 미사용, NeckingExpertState에 통합)

---

## 🚀 다음 단계

### Phase 2: 통합 테스트 (권장)

1. **실제 이미지 테스트**:

   - `data/` 디렉토리의 necking 사례 이미지 사용
   - Debate 과정 관찰 및 로그 확인

2. **성능 측정**:

   - 토큰 사용량 (기존 vs Debate)
   - 실행 시간
   - 판정 정확도

3. **임계값 튜닝**:
   - `MAX_ITERATIONS` 최적화 (현재 3턴)
   - Critic의 NO_OBJECTION 조건 조정

### Phase 3: 다른 Expert에 확장 (선택)

검증 완료 후:

- Contact Expert
- Tracking Expert
- 기타 Expert들에 동일 패턴 적용 가능

---

## 💡 사용 예시

### Notebook에서 실행

```python
from src.graphs.necking_expert_graph import necking_expert_wrapper_node
from src.state import InvestigationState

# State 준비
state: InvestigationState = {
    "payload": [...],  # 이미지 데이터
    "hotspots": [...],  # 공통 hotspots
    # ...
}

# 실행
result = necking_expert_wrapper_node(state)

# 결과 확인
print(result["expert_reports"][0])  # Debate 기록 포함
```

### 출력 예시

```
[Necking 전문가 최종 판정 - Analyst-Critic 토론]

## 결론: 반단선 Medium (65%)

## 최종 합의 가설
반단선 Medium (65%)

## 종합 소견
Analyst-Critic 2턴 토론 후 합의 도출.
합의된 판정

## 토론 기록
[Analyst Round 1] {"initial_hypothesis": "반단선 High (85%)", ...}

[Critic Round 1] {"objection_type": "프로파일 누락 간과", ...}

[Analyst Round 2] {"revised_hypothesis": "반단선 Medium (65%)", ...}

[Critic Round 2] {"objection_type": "NO_OBJECTION"}
```

---

## ✨ 결론

**Fire-CSI-Refiner (Analyst-Critic-Supervisor)** 패턴을 Necking Expert에 성공적으로 통합했습니다.

**핵심 성과**:

1. ✅ 사용자 제안 수용: Main Graph에 직접 통합
2. ✅ LangGraph 표준 100% 준수
3. ✅ 보수적 판정 메커니즘 (Timeout 처리)
4. ✅ 투명한 의사결정 (Debate Log)

이제 실제 사례로 테스트하여 효과를 검증할 준비가 완료되었습니다! 🎉

---

_구현 완료일: 2026-01-10_  
_구현자: Antigravity AI_  
_패턴: Fire-CSI-Refiner (Analyst-Critic-Supervisor)_
