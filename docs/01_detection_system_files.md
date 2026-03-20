# 탐지 시스템 관련 파일 목록 (Detection System Files)

본 프로젝트의 **1단계: 적응형 핫스팟 탐지 및 Identity Fusion** 과정과 관련된 주요 파일 리스트입니다.

## 1. 노드 및 로직 (Nodes & Logic)
- **[common_nodes.py](file:///v:/Projects/P_04_Scope/src/nodes/common_nodes.py)**: 메인 탐지 노드인 `hotspot_detector_node`가 위치하며, 이미지 슬라이싱 배치 처리 및 **Identity Fusion** 전략이 구현되어 있습니다.
- **[nms.py](file:///v:/Projects/P_04_Scope/src/utils/nms.py)**: 탐지된 중복 핫스팟을 제거하고 정교화하는 NMS(Non-Maximum Suppression) 알고리즘이 포함되어 있습니다.

## 2. 데이터 모델 (Data Models)
- **[hotspot_models.py](file:///v:/Projects/P_04_Scope/src/models/hotspot_models.py)**: 탐지 결과(`HotspotDetectionResult`), 다중 뷰 병합 모델(`UnifiedHotspot`), 그리고 매핑 결과(`IdentityFusionResult`) 정의를 담고 있습니다.
- **[state.py](file:///v:/Projects/P_04_Scope/src/state.py)**: 탐지 단계에서 생성되는 `image_paths` 및 `hotspots` 상태 필드를 정의합니다.

## 3. 프롬프트 엔진 (Prompt Engine)
- **[common_prompts.py](file:///v:/Projects/P_04_Scope/src/prompts/common_prompts.py)**: 
    - `get_micro_evidence_prompt`: 패치 단위 정밀 탐지용 지시문.
    - `get_identity_fusion_prompt`: 다중 이미지 간 객체 병합/분리 판단용 지시문.

## 4. 유틸리티 및 전처리 (Utilities)
- **[image_processing.py](file:///v:/Projects/P_04_Scope/src/utils/image_processing.py)**: 고해상도 이미지의 **Overlap Grid Slicing** 및 좌표 역매핑(`map_box_to_global`)을 담당합니다.
- **[coordinate_utils.py](file:///v:/Projects/P_04_Scope/src/utils/coordinate_utils.py)**: 해상도 독립적 분석을 위한 BBox 상대 좌표(0-1000) 정규화 도구입니다.

## 5. 입력 인프라 (Input Infrastructure)
- **[expert_utils.py](file:///v:/Projects/P_04_Scope/src/tools/experts/expert_utils.py)**: 페이로드에서 다중 이미지를 안정적으로 추출하여 탐지 파이프라인으로 연결합니다.
- **[agent.py](file:///v:/Projects/P_04_Scope/src/agent.py)**: 탐지 노드의 시작점이며, 초기 이미지 저장 및 탐지 결과에 따른 리소스 정리를 관리합니다.

---

### 탐지 시스템 파일 목록 (Summary)
@common_nodes.py
@nms.py
@hotspot_models.py
@state.py
@common_prompts.py
@image_processing.py
@coordinate_utils.py
@expert_utils.py
@agent.py
