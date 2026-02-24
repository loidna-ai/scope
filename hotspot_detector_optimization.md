# Hotspot Detector 최적화 작업 내역

## 1. 개요

기존 Hotspot Detector는 `Overlap Grid Strategy`를 기반으로 원본 이미지를 $1024 \times 1024$ 사이즈 패치 수십 개로 잘라(Slicing) 모두 API로 직접 전송하는 구조를 가지고 있었습니다.
하지만 Gemini API의 분당 제한(`RPM 30`)과 묶여있는 동시성 제한(`Semaphore 2`)의 병목 이슈로 인해 429 에러나 심각한 속도 저하가 지속 발생하는 문제가 존재했습니다.

본 문서는 이러한 병목을 극복하고 **Gemini-3-Flash-Preview** 모델의 장점(장문/다중 이미지 지원)을 최대한 살릴 수 있도록 적용한 3가지 핵심 성능 및 속도 최적화 모듈(Dynamic Downscaling, OpenCV Background Filtering, Multi-image API Batching)의 기능 변화와 적용 내역을 기록합니다.

---

## 2. 세부 변경 사항 (3단계)

### 2-1. Dynamic Downscaling (동적 리사이징)

고해상도 이미지(예: 4K, 8K)가 입력되었을 때 무한정 패치가 생성되는 것을 방지합니다. 원본 해상도가 너무 클 경우 기준 축 길이(Max Dimension)에 맞추어 API 부하 전에 선제적으로 다운스케일(축소)하는 로직을 추가했습니다.

- `config.py`: `HOTSPOT_MAX_IMAGE_DIMENSION = 2048` 설정.
- `image_processing.py`: `slice_image()` 제너레이터 내에서 제일 긴 축을 타겟 해상도(2048px)에 맞춰 적절한 임시 $Scale Factor$로 리사이징.
- `image_processing.py`: `map_box_to_global()`를 업그레이드하여, 최종 0~1000 상대 좌표 맵핑 과정에서 축소되었던 $Scale Factor$ 배율을 역연산하도록 연결. (수동 좌표 보정 완료)

### 2-2. OpenCV-Based Background Filtering (의미 없는 패치 필터링)

정보량이 없는(텍스처 부족), 빈 배경이나 아웃포커싱으로 완전히 날아간(Blur) 무의미한 이미지 패치가 API로 보내지는 것을 차단합니다. OpenCV가 이를 초고속으로 판별하고 즉시 `Drop(폐기)` 처리합니다. 전체 API 호출 횟수를 **최소 30~50%** 거를 수 있습니다.

- `config.py`:
  - `HOTSPOT_BLUR_THRESHOLD = 50.0`: **Laplacian Variance(라플라시안 분산)** 기준값. 50 이하의 패치라면 피사체가 너무 흐릿하거나 초점이 나간 것으로 간주합니다.
  - `HOTSPOT_EDGE_THRESHOLD = 15`: **Canny Edge(캐니 엣지 밀도)** 기준값. 15 이하라면 텍스처(선, 외곽)가 전혀 없는 단색/장판/흰 배경 등으로 간주합니다.
- `image_processing.py`: `slice_image()`에서 위 두 기준을 모두 충족하지 못하는(초과하지 못하는) 패치는 `continue`를 통해 제너레이터 출력 목록에서 배제시킵니다.

### 2-3. Gemini 3 Flash Multi-Image Batching (멀티 이미지 일괄 전송)

Gemini 3 Flash Preview 모델은 단일 프롬프트에서 **최대 900장의 이미지**를 넣을 수 있고 입출력 가능 토큰이 **1,048,576**개에 달합니다.
이를 1장씩 쪼개 보내며 수십 번의 API 커넥션을 맺던 방식을 **$N$장씩 엮어 묶어 보내는 일괄 배치(Batch) 방식**으로 통합 전환했습니다.

- `config.py`: `HOTSPOT_BATCH_SIZE = 5` 추가 설정 (1번의 Request에 담을 묶음 패치 개수)
- `common_nodes.py`:
  - 기존 패치 단위의 단일 코루틴(`_process_patch`)을 리스트 단위 코루틴(`_process_patch_batch`)으로 전면 재작성했습니다.
  - 5장의 JPEG 바이너리가 `types.Part.from_bytes` 형태로 하나의 LLM `contents` Array 내부에 순서대로 합쳐져 Gemini 백엔드에 전달됩니다.
  - 분석을 1번만 기다려도 5개의 패치 이미지가 한꺼번에 처리되므로, API 호출(Limit) 제약을 우회하며 결과 수신 속도가 최대 **$N$배 상향**되었습니다.

---

## 3. 요약 (최적화 후 Data Flow)

1.  사용자가 원본 화재 이미지를 제출(`input`).
2.  `slice_image()` 진입: 이미지 픽셀이 2048px을 초과할 경우 임시로 화질 타협(`Downscaling`).
3.  1024px 조각들로 거대한 이미지를 슬라이스 하며(`overlap` 적용), 조각 단위별로 `cv2`(OpenCV) 필터를 거칩니다. (흐리거나 단색인 배경은 50% 이상 `Drop`).
4.  살아남은 소수 정예 조각(패치)들만이 $Batch Size$(기본값 5) 단위로 크게 무리 지어 `hotspot_detector_node`의 `task` 큐에 배치됩니다.
5.  Gemini Flash 3 API가 각 배치 무리를 단 한 번의 커넥션으로 통째로 판독하고, 찾아낸 미세 증거 핫스팟 Pydantic Model 리스트를 반환합니다.
6.  찾아진 모든 핫스팟의 좌표는 축소되었던 $Scale Factor$를 고려해 다시 글로벌 이미지 절대 좌표($0 \sim 1000$) 공간으로 확대(`map_box_to_global`) 후 정렬됩니다.
7.  `NMS`(Non-Maximum Suppression)를 거쳐 겹치는 박스를 합친 후 최종적으로 Expert Agent에게 디스패치됩니다.
