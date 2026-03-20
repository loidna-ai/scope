# 분석 시스템 관련 파일 목록 (Analysis System Files)

본 프로젝트의 **2단계: 전문가별 증거 추출 및 전처리 (Deep Mode Analysis)** 과정과 관련된 주요 파일 리스트입니다.

## 1. 전처리 및 ROI 제어 (Preprocessing)
- **[preprocessor_node.py](file:///v:/Projects/P_04_Scope/src/nodes/preprocessor_node.py)**: 핫스팟별 다중 뷰 Crop, 고화질 향상(SR), 부품 자동 분류를 병렬로 통합 수행하는 핵심 노드입니다.
- **[expert_worker_utils.py](file:///v:/Projects/P_04_Scope/src/nodes/expert_worker_utils.py)**: 개별 전문가가 사용하는 ROI 처리 도구 및 구성 물질 분류 로직을 포함합니다.
- **[enhancement.py](file:///v:/Projects/P_04_Scope/src/nodes/enhancement.py)**: 저해상도 핫스팟을 Super-Resolution 기법으로 복원하는 모듈입니다.

## 2. 전문가 노드 및 로직 (Expert Nodes)
- **[contact_nodes.py](file:///v:/Projects/P_04_Scope/src/nodes/contact_nodes.py)**: 접촉 불량 전문가(Contact Expert)의 정밀 분석 로직과 Gemini Vision API 연동을 담당합니다.
- **[contact_expert_graph.py](file:///v:/Projects/P_04_Scope/src/graphs/contact_expert_graph.py)**: 전문가 내부의 '분석-검증-판정(Analyst-Critic-Verdict)' 루프를 구축하는 서브그래프 파일입니다.

## 3. 데이터 모델 및 스키마 (Models)
- **[evidence_models.py](file:///v:/Projects/P_04_Scope/src/models/evidence_models.py)**: 법과학적 증거(`EvidenceItem`)와 전문가 최종 리포트(`ExpertReport`) 구조를 정의합니다.
- **[contact_models.py](file:///v:/Projects/P_04_Scope/src/models/contact_models.py)**: 전문가 도메인에 특화된 시각적 특징 추출 모델들을 담고 있습니다.

## 4. 프롬프트 및 유틸 (Prompts & Utils)
- **[contact_expert_prompts.py](file:///v:/Projects/P_04_Scope/src/prompts/contact_expert_prompts.py)**: 다각도 분석 및 **사각지대 부정(Negative Proof)** 원칙이 포함된 전문가용 시스템 프롬프트입니다.
- **[expert_image_utils.py](file:///v:/Projects/P_04_Scope/src/utils/expert_image_utils.py)**: 전문가 분석에 최적화된 원본/ROI 이미지 로딩 유틸리티입니다.

---

### 분석 시스템 파일 목록 (Summary)
@preprocessor_node.py
@expert_worker_utils.py
@enhancement.py
@contact_nodes.py
@contact_expert_graph.py
@evidence_models.py
@contact_models.py
@contact_expert_prompts.py
@expert_image_utils.py
