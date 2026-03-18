# 프로젝트 워크플로우

## 개요

화재조사 AI 멀티 에이전트 시스템은 이미지를 입력받아 **공통 탐지 및 전처리 파이프라인**을 거친 후, **LangGraph Map-Reduce** 패턴이 적용된 복수의 최고 전문가 에이전트들에게 분석을 병렬 배분하고, 최종적으로 **Arbiter Agent**가 각 전문가의 증거를 종합 합의 조율하는 워크플로우를 가집니다.

---

## 전체 워크플로우 다이어그램

```text
┌─────────────────────────────────────────────────────────────────┐
│                        main.py (진입점)                          │
│        python main.py [image_path]                              │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
        ┌────────────────────────────────┐
        │  1. 공통 전처리 & 핫스팟 탐지    │
        │     (Hotspot Detector)          │
        └────────────────┬───────────────┘
                         │
                         ▼
        ┌────────────────────────────────┐
        │  2. 공통 사전 필터링             │
        │     (Preprocessor)              │
        └────────────────┬───────────────┘
                         │
                         ▼
        ┌────────────────────────────────┐
        │  3. 멀티 에이전트 병렬 분석      │
        │     (Map-Reduce & Debate)       │
        └────────────────┬───────────────┘
                         │
                         ▼
        ┌────────────────────────────────┐
        │  4. 최종 논쟁 및 판정 종합       │
        │     (Arbiter Agent Debate)      │
        └────────────────────────────────┘
```

---

## 1. 공통 전처리 & 핫스팟 탐지 (Hotspot Detector)

원본 이미지에서 전기화재의 단서(단락흔 등)가 될 수 있는 관심영역(Hotspot)을 Slicing과 NMS를 융합하여 정밀하게 다수 탐지합니다.

- **노드**: `hotspot_detector_node` (`src/nodes/common_nodes.py`)
- **수행 과정**:
  1. 원본 이미지를 다중 패치(Patch)로 분할 (Overlap 적용으로 경계 유실 방지).
  2. 병렬로 여러 패치를 Gemini Vision API에 던져 Hotspot 개별 식별 및 좌표 도출.
  3. 모든 패치에서의 좌표를 전역 공간(Global Position)으로 통합 변환.
  4. **NMS (Non-Maximum Suppression)** 알고리즘 기반으로 중복 식별 영역 제거 및 통합.

---

## 2. 공통 사전 필터링 (Preprocessor)

탐지된 수많은 Hotspot들에 대해 기초적 전처리를 단방향으로 완료하여, 뒤에 이어진 다수 전문가 모듈에서의 반복적인 중복 처리를 방지합니다.

- **노드**: `preprocess_hotspots_node` (`src/nodes/preprocessor_node.py`)
- **수행 과정**:
  1. 각 BBox 단위로 이미지 Crop 수행 (`_crop_roi`).
  2. Component Classification 프로세스로 해당 지점이 어떤 속성을 갖는지 1차 분류 (`_classify`).
  3. 화질 개선이 필요한 경우 Real-ESRGAN 모델을 사용해 화질 향상 (`_enhance_roi`).
  4. 도출된 모든 결과를 상태(`preprocessed_hotspots`)에 캐싱 처리.

---

## 3. 멀티 에이전트 병렬 분석 (Map-Reduce & Debate)

실제로 활성화된 전문가들 (**Contact, Necking**)은 공통된 형태의 서브그래프를 가지며, 각각 병렬로 실행됩니다. (Deform, Aging은 비활성)

### 서브그래프 워크플로우 (예: `src/graphs/contact_expert_graph.py`)

```text
START
  │
  ├─→ distribute_work (Fan-Out 기반 라우팅)
  │     └─→ Hotspot 단위로 LangGraph `Send` 객체 생성
  │
  ├─→ analyze_hotspot_worker (Worker, Map 연산 동시 실행)
  │     └─→ 개별 위치/패턴/특징을 각 환경에 맞춰 정밀 조사 API 질의
  │
  ├─→ supervisor_verdict (Fan-In 및 Reduce)
  │     └─→ Worker 처리 결과를 전부 모아 초기 대표 가설 도출
  │
  ├─→ Analyst-Critic Debate (조건부)
  │     ├─→ verdict_analyst (분석관: 가설 및 논리 고도화)
  │     ├─→ verdict_critic (비평가: 논리 허점 공격, 대안 검토)
  │     └─→ Loop (최대 3턴) OR 합의
  │
  └─→ verdict_finalize
        └─→ 최종 리포트 및 전문가 신뢰도 점수 확정
        └─→ END
```

**주요 특징**:

- **Send API 활용 병렬성 보장**: LangGraph의 분산 처리를 통해 한 전문가가 N개의 Hotspot을 Map 형식으로 매핑하여 동시성있게 판독합니다.
- **Analyst-Critic 논쟁 (Debate)**: 빠른 결론 도출을 피하고, AI 객체 내부적으로 검토와 비판 루프를 만들어 오판 및 증거의 과잉 해석을 효과적으로 차단합니다.

---

## 4. 최종 판단 종합 (Arbiter Agent)

모든 최고 전문가 에이전트의 개별 보고서와 신뢰도(Confidence) 정보가 집계되면 최종 판정 관문을 지나는 중재자(Arbiter)가 나섭니다.

- **서브그래프**: `src/graphs/arbiter_expert_graph.py`
- 각각 다른 관점을 가지는 전문가들(Contact, Necking)의 리포트 내용이 서로 상충하는지 자체 검사합니다. 중재자 내부의 `judge`, `moderator` 등이 합의를 조정합니다.
- **ARBITER_CONFIDENCE_THRESHOLD**: Judge 진입 전, 전문가 평균 신뢰도가 `config.ARBITER_CONFIDENCE_THRESHOLD`(기본 60%) 미만이면 LLM 호출 없이 "판단 불가(UNDETERMINED)"를 즉시 반환합니다.

---

## 데이터 스테이트

데이터 흐름은 LangGraph State (`TypedDict`) 상에 보존되어 부수효과(Side-Effect)를 방지합니다.

### InvestigationState (전역 메인 그래프)

```python
class InvestigationState(TypedDict):
    payload: List[Any]  # 분석 데이터
    image_path: Optional[str]  # 이미지 물리 경로
    hotspots: Optional[List[Dict]]  # 전처리 탐지 원시 좌표
    preprocessed_hotspots: Optional[List[Dict]]  # 1회성 사전 필터 저장소
    expert_reports: List[str]  # reducer : operator.add
    expert_analysis_results: dict  # reducer : merge_dicts
    expert_confidence_scores: dict # reducer : merge_dicts
    expert_evidence: dict          # reducer : merge_dicts
    final_verdict: Optional[str]
    final_verdict_structured: Optional[Any]
    arbiter_debate_messages: Optional[List[Dict]]
    errors: List[str]
```

---

## 출력 처리

`outputs/{image_name}/` 디렉터리에 다음 데이터들이 최종 산출 되어 저장됩니다:

- `investigation_result.json` (시스템 연산 과정들의 축적된 데이터)
- `investigation_result.txt` (최종 요약 판단을 볼 수 있는 직관적인 리포트)
- `full_pipeline.png` (옵션 파라미터를 이용해 얻는 디버그 시각화)

---

## 주요 개선 이력 요약

- **2026.01**: Map-Reduce 구조 변경 완료 (Send API 도입) 및 내부 각 전문가별 Analyst-Critic 자가 논쟁 패턴 적용.
- **2026.02**: `ThreadSafeRateLimiter` 구축을 통한 무제한적인 API Call 에 의한 제한 대응.
- **2026.02**: 노드 파일 재배치 및 레거시 파일 정리.
- **2026.03**: Arbiter Agent 개선 - ARBITER_CONFIDENCE_THRESHOLD 적용, FinalVerdictResult 동적화(2~4명), expert_opinions 비었을 때 UNDETERMINED, Fact Check 재발언 프롬프트 보강, debate_init 노드 명확화.
