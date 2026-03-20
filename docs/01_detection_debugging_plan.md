# 탐지 단계별 디버깅 계획 (Detection Debugging Plan)

탐지 시스템(PHASE 1)에서 발생하는 복합적인 문제들을 해결하기 위해, 프로그램 실행 흐름에 따라 6단계로 나누어 디버깅을 진행합니다.

---

## 📅 단계별 디버깅 워크플로우

### 1단계: 입력 데이터 및 페이로드 무결성 (Input & Payload)
*   **목적**: 분석 시작 전, 원본 이미지와 페이로드 데이터가 올바르게 준비되었는지 확인.
*   **체크리스트**:
    - [ ] `main.py`에서 이미지 파일 로드 및 Base64 인코딩이 손실 없이 이루어지는가?
    - [ ] `create_payload_from_image`가 지원하는 모든 확장자(JPG, PNG 등)에 대해 정상 작동하는가?
    - [ ] `src/agent.py`에서 임시 파일로 복원된 이미지의 해상도나 품질에 저하가 없는가?
*   **디버깅 도구**: `debug/` 폴더에 생성된 임시 이미지 직접 확인, `payload` 크기 로깅.

### 2단계: 이미지 슬라이싱 및 패치 생성 (Slicing & Patching)
*   **목적**: 고해상도 이미지를 분석 가능한 크기의 패치로 정확히 나누는지 확인.
*   **체크리스트**:
    - [ ] `HOTSPOT_PATCH_SIZE`와 `HOTSPOT_OVERLAP` 설정에 따라 누락되는 영역 없이 패치가 생성되는가?
    - [ ] 블러(Blur) 및 에지(Edge) 필터링 임계값이 너무 높아 유효한 증거가 포함된 패치가 버려지지는 않는가?
    - [ ] 다중 이미지 입력 시, 각 이미지별로 독립적인 패치 리스트가 관리되는가?
*   **디버깅 도구**: `slice_multiple_images` 실행 후 생성된 샘플 패치들을 `debug/patches/`에 저장하여 시각화.

### 3단계: Gemini API 응답 및 파싱 (API & Prompt)
*   **목적**: LLM이 관심 영역(Hotspot)을 정확히 찾아내고 구조화된 데이터를 반환하는지 확인.
*   **체크리스트**:
    - [ ] `get_micro_evidence_prompt`가 현재 모델(Pro 2.0 등)의 성능을 최적으로 끌어내는가?
    - [ ] `HotspotDetectionResult` Pydantic 모델의 JSON Schema가 API 응답과 일치하는가?
    - [ ] `HOTSPOT_BATCH_SIZE` 설정 시, 여러 장의 패치가 섞여서 좌표 혼선이 발생하지 않는가?
*   **디버깅 도구**: `batch_process_hotspots` 전후의 API Request/Response JSON Raw 데이터 로깅.

### 4단계: 좌표 복원 및 전역 매핑 (Coordinate Mapping)
*   **목적**: 패치 내의 로컬 좌표를 전체 이미지의 전역 좌표로 정확히 변환하는지 확인.
*   **체크리스트**:
    - [ ] `map_hotspots_to_global` 함수에서 패치 오프셋(x, y)과 스케일링이 정확히 계산되는가?
    - [ ] 리사이즈된 이미지에서 탐지된 좌표가 원본 크기 해상도로 역변환될 때 오차가 발생하는가?
    - [ ] [ymin, xmin, ymax, xmax] 순서가 시스템 전체(OpenCV, Gemini)에서 일관되게 유지되는가?
*   **디버깅 도구**: 전역 좌표로 복원된 Bounding Box를 원본 이미지에 그려서 `debug/global_mapping.jpg`로 저장.

### 5단계: 중복 제거 및 객체 통합 (NMS & Identity Fusion)
*   **목적**: 동일한 객체에 대한 중복 탐지를 제거하고, 서로 다른 앵글의 이미지를 통합.
*   **체크리스트**:
    - [ ] `perform_batch_nms`의 `IOU_THRESHOLD`가 적절하여 인접한 서로 다른 객체를 지우지는 않는가?
    - [ ] `run_identity_fusion`이 서로 다른 파일(앵글)에서 찍힌 동일 핫스팟을 'Unified ID'로 잘 묶어주는가?
    - [ ] 통합 과정에서 Confidence Score나 Severity Score가 잘못 평균화되거나 유실되지 않는가?
*   **디버깅 도구**: NMS 전후의 Hotspot 개수 변화 및 Fusion 그룹핑 결과 로깅.

### 6단계: 공유 전처리 (Preprocessing - Crop, Enhance, Classify)
*   **목적**: 전문가 분석 전, 최적화된 ROI 이미지를 생성하고 컴포넌트를 분류.
*   **체크리스트**:
    - [ ] `_crop_roi` 시 여유 공간(Padding)이 충분하여 전문가 분석에 방해가 되지 않는가?
    - [ ] `ImageEnhancer`의 Super-Resolution 결과가 실질적으로 가독성을 높여주는가? (노이즈 확인)
    - [ ] `ComponentClassification` 결과가 실제 부품(전선, 단자 등)과 일치하는가?
    - [ ] 시각화 결과(`visual_report`)에 표시되는 상자와 데이터가 최종 결과값과 일치하는가?
*   **디버깅 도구**: `preprocessed_hotspots`에 저장된 각 핫스팟의 `roi_image_path`와 `component_type` 전수 조사.

---

## 🛠 공통 디버깅 전략

1.  **단일 패치 테스트**: 전체 이미지 대신 문제가 발생하는 특정 구역의 패치 하나만 API에 던져서 응답 확인.
2.  **Mocking API**: API 비용 절감 및 로직 검증을 위해 예상되는 JSON 응답을 파일로 저장해두고 Mocking하여 좌표 변환 및 NMS 로직 집중 테스트.
3.  **Visual Debugging**: 모든 단계의 중간 결과물(Crop 이미지, 좌표가 그려진 전체 이미지)을 로컬에 저장하여 육안으로 검증.
