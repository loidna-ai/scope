# [구현 계획서] 통합 하이브리드 화재 징후 분석 시스템 (Integrated Analysis System)

본 문서는 `integrated_analysis_design.md` 설계안을 바탕으로 단일(Single), 다각도(Deep), 다중 지점(Wide) 화재 징후 분석 시스템을 구현하기 위한 세부 단계별(Phase) 이행 계획을 정의합니다.

---

## Phase 1: 상태 파라미터 및 입력 처리 개편 (State & Input Refactoring)

**목표:** 다중 이미지 입력을 처리할 수 있도록 그래프 상태 및 진입점을 구조적으로 확장합니다.

1. **`InvestigationState` 스키마 수정 (`src/state.py`)**
   - 기존의 단일 `image_path` 필드를 `image_paths: List[str]` 형태로 확장하거나 유연하게 처리할 수 있도록 구조 변경.
   - 다중 이미지 환경에 맞게 `payload` 추출 로직 수정.
2. **에이전트 입력 래퍼 로직 수정 (`src/agent.py`)**
   - `analyze_fire_evidence` 함수에서 입력되는 다중 이미지를 순회하며 각각 임시 경로(tempfile)로 저장하고 관리하는 로직 추가 (`extract_images_from_payload`).
3. **좌표계 정규화 유틸리티 구현**
   - 다중 이미지 간 해상도 차이를 보정하기 위해 BBox 좌표를 0~1000 상대 좌표계로 변환하는 유틸리티 작성.

---

## Phase 2: 적응형 핫스팟 탐지기 고도화 (Adaptive Hotspot Detection)

**목표:** 다중 이미지를 분석하여 동일 객체를 식별(Deep)하거나 독립 지점(Wide)으로 분류하는 **통합 핫스팟 패키지** 생성 로직을 구현합니다.

1. **탐지 노드 리팩토링 (`src/nodes/common_nodes.py`)**
   - 단일 이미지를 순회하며 기본 탐지(Grid Slicing Scan) 수행.
   - 2장 이상의 이미지가 입력된 경우, **Identity Fusion(동일 인물/객체 식별) 프롬프트**를 추가 호출.
2. **교차 식별(Cross-View) 로직 추가**
   - Vision LLM에 다수의 이미지와 각 탐지된 BBox를 시각화하여 전달하고, "A 이미지의 1번 박스와 B 이미지의 2번 박스는 동일한 부품인가?"를 묻는 연결성(Relationship) 매핑 프롬프트 구현.
3. **Unified Hotspot Package 스키마 적용**
   - 탐지 결과를 묶어 `boxes`, `source_images` 등 여러 이미지의 좌표 및 경로를 포함하는 `Unified Hotspot` 구조체로 병합 생성.

---

## Phase 3: 전문가 교차 분석 융합 (Expert Fusion & Preprocessing)

**목표:** 각 분야별 전문가(Worker) 모델이 여러 각도의 뷰(다중 ROI)를 조합하여 객체 하나를 입체적으로 분석하게 만듭니다.

1. **다중 ROI 전처리 (`src/nodes/preprocessor_node.py`)**
   - Unified Hotspot Package 내부의 각 이미지 소스별 Bbox를 바탕으로 여러 장의 ROI 이미지를 안전하게 Crop & Enhance 수행.
   - Component Classifier 역시 다각도 이미지를 입력받도록 프롬프트 및 페이로드 개선 (필요시 병합 로직 결합).
2. **작업자 노드 및 이미지 핸들링 개편 (`src/nodes/expert_worker_utils.py` 및 도메인 `nodes.py`)**
   - `call_evidence_api` 호출 시 `roi_image_path`를 리스트 형태로 입력 가능하도록 변경.
   - `ExpertImageLoader`에서 여러 장의 원본 및 ROI를 병렬로 로드하도록 확장.
3. **전문가 시각 검증 프롬프트 고도화 (`src/prompts/*_expert_prompts.py`)**
   - "첨부된 다각도 사진들(Image 1, Image 2...)을 종합하여..." 라는 식의 입체 데이터 전용 지시문 추가.
   - "사각지대 부정(Negative Proof) 원칙: 한 각도에서라도 결함이 아님이 명백할 경우, 의심 수준을 낮출 것" 규칙 적용.

---

## Phase 4: 아비터 장면 종합 판정 (Scene Synthesis)

**목표:** 개별 핫스팟이 아닌 거시적 관점(현장 전반, Wide)에서 사건의 전후 맥락 및 상관관계를 도출합니다.

1. **Debate Data Extractor 데이터 정렬 기준 확장 (`src/nodes/arbiter_nodes/debate_data_extractor.py`)**
   - 단순 나열이 아닌, 이미지 구역(공간적 위치) 단위 그룹핑 로직 추가하여 아비터에 전달하는 컨텍스트 강화.
2. **현장 시나리오 추론 방침 적용 (`src/prompts/arbiter_debate_prompts.py`)**
   - `judge_node` 및 `moderator_node`에 "서로 다른 지점(Wide Mode)의 결함 간의 선후 관계 / 인과 관계를 추론하여 최초 발화 지점을 특정하라"는 지시어 추가.

---

## Phase 5: 안정성 및 최적화 (Stability & Optimization)

**목표:** 복잡한 다중 다각도 분석에 따른 API 리밋 ও 병목 현상을 제어합니다.

1. **API 동시성 제어 강화 (`src/utils/api_concurrency.py` 도입 또는 고도화)**
   - Gemini Vision 등 높은 토큰을 요구하는 API의 Rate Limit (RPM/TPM) 에러 방지를 위한 Semaphore/Queue 기반 전역 제어기 적용.
2. **임시 파일(Temp Files) 및 메모리 누수 방지 조치 강화**
   - 생성된 N배수의 ROI 이미지에 대하여 처리가 끝난 후(Cleanup) 명확히 삭제하는 Garbage Collection 보완 로직(`cleanup_temp_files` 확장) 작성.
3. **유닛 및 통합 테스트 구성**
   - Single, Deep, Wide 3가지 시나리오를 각각 테스트할 수 있는 Mock Data Set 마련.
