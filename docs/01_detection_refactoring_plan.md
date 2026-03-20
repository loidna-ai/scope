# 탐지 시스템 리팩토링 및 구조 정리 계획 (Refactoring Action Plan)

본 문서는 탐지 시스템의 기술 부채를 해결하고, 유지보수성 및 데이터 흐름의 명확성을 확보하기 위한 단계별 리팩토링 계획을 제시합니다.

| 파일명 | 현재 문제점 및 분석 | 구체적인 리팩토링 계획 (수정/이동/삭제) | 예상되는 영향(Risk) |
| :--- | :--- | :--- | :--- |
| **common_nodes.py** | `hotspot_detector_node` 내부에 슬라이싱, API 배치 호출, NMS 그룹핑, Identity Fusion 로직이 모두 혼재되어 SRP를 심각하게 위반하고 있음. | 1. Identity Fusion 로직을 `src/utils/identity_fusion.py`로 모듈화하여 분리.<br>2. API 배치 호출부를 `src/utils/api_concurrency.py`의 헬퍼 함수로 캡슐화.<br>3. `_update_image_path_in_result`를 `io_utils.py`로 이동. | 비즈니스 로직 분리 과정에서 노드 간 인터페이스(State 업데이트 방식) 불일치 발생 가능. |
| **agent.py** | `analyze_fire_evidence`가 입력 데이터 정제, 리사이징, 파일 IO, GC 로직 등 인프라 성격의 코드를 너무 많이 포함하는 'God Function' 상태임. | 1. 이미지 리사이즈 및 전처리 로직을 `src/utils/image_processing.py`로 일원화.<br>2. 임시 파일 가비지 컬렉션(GC) 로직을 `src/utils/io_utils.py`의 독립 클래스로 추상화. | 초기화 단계의 함수 호출 오버헤드 및 임시 파일 삭제 타이밍 이슈 발생 가능. |
| **hotspot_models.py** | 모델 객체가 단순 데이터 컨테이너 역할만 수행함. Raw Hotspot을 Unified Hotspot으로 변환하는 비즈니스 로직이 각 노드에 흩어져 있음. | 1. `UnifiedHotspot` 클래스에 `from_raw_hotspots` 정적 메서드(Static Method)를 추가하여 데이터 변환 로직을 캡슐화.<br>2. 좌표 데이터 유효성 검사 로직(Validator) 추가. | 데이터 구조 변경 시 모델과 노드 간의 강한 결합도로 인한 광범위한 수정 발생. |
| **state.py** | `InvestigationState`의 `hotspots` 필드가 `List[Dict]` 형태로 관리되어 런타임 타입 안정성이 낮고 부작용(Side-effect)에 취약함. | 1. `hotspots` 필드의 타입을 `List[UnifiedHotspot]`으로 명확히 선언.<br>2. 상태 업데이트 시 불변성(Immutability)을 보장하도록 가공 로직 개선. | LangGraph의 Pydantic 직렬화/역직렬화 과정에서 성능 저하 또는 호환성 경고 발생 가능. |
| **nms.py** | 현재 탐지 이미지별로 NMS를 수행하는 로직이 중복되어 구현되어 있음. | 1. 다중 이미지 리스트를 받아 일괄적으로 NMS를 수행하고 인덱스를 부여하는 `batch_nms` 래퍼 함수 구현.<br>2. 더 이상 사용되지 않는 단일 NMS 레거시 함수(있을 경우) 삭제. | 중복 제거 임계값(Threshold) 변경 시 탐지 정확도에 직접적인 영향. |
| **image_processing.py** | 슬라이싱(Generator)과 전역 좌표 동화(Normalization) 로직이 물리적으로 섞여 있어 테스트가 어려움. | 1. 슬라이싱 엔진과 좌표 매핑(`map_box_to_global`) 로직을 클래스 기반으로 구조화.<br>2. OpenCV 종속성을 가진 필터링 로직을 `utils/cv_filters.py`로 분리 검토. | 좌표 오차 발생 시 핫스팟의 실제 위치와 시각화 간의 괴리 발생. |
| **common_prompts.py** | 프롬프트 텍스트가 Python 파일 내에 하드코딩되어 있어 가독성이 낮고 수정 시 실수가 잦음. | 1. 긴 시스템 프롬프트를 `.txt` 또는 `.md` 템플릿 파일로 외부화하고 로더(Loader)를 통해 호출.<br>2. 버전 관리를 위한 프롬프트 메타데이터 연동. | 파일 I/O 로드 실패 시 전체 시스템 중단(Critical Failure) 위험. |
| **coordinate_utils.py** | 단순 좌표 변환만 수행하며 캐싱이나 이미지 해상도 정보 추적 기능이 미비함. | 1. 반복적인 이미지 사이즈 체크를 줄이기 위해 `LRU Cache` 적용.<br>2. 상대 좌표 <-> 절대 좌표 변환을 전담하는 싱글톤 유틸리티로 강화. | 캐시 갱신 실패 시 캐시된 구 해상도 정보로 인한 좌표 오정렬. |
| **expert_utils.py** | 페이로드 파싱 로직이 하드코딩되어 있어 새로운 메시지 포맷 대응력이 낮음. | 1. 다양한 메시지 프로토콜에 대응하기 위한 파서(Parser) 팩토리 패턴 도입.<br>2. 이미지 데이터 추출과 메타데이터 추출 로직 분리. | 파킹 시 특정 필드 누락 시 이미지 데이터 유실 위험. |

---

### 리팩토링 우선순위
1. **P1: SRP 위반 해결** (`common_nodes.py`, `agent.py`) - 가장 큰 복잡도 병목 구간.
2. **P2: 데이터 모델 강화** (`state.py`, `hotspot_models.py`) - 협업 및 타입 안전성 확보.
3. **P3: 효율성 및 가독성** (`common_prompts.py`, `nms.py`, `image_processing.py`) - 유지보수성 향상.
