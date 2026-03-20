# 종합 시스템 관련 파일 목록 (Synthesis System Files)

본 프로젝트의 **3단계: 장면 종합 및 최종 판정 (Wide Mode Synthesis)** 과정과 관련된 주요 파일 리스트입니다.

## 1. 아비터 데이터 추출 (Data Extraction)
- **[debate_data_extractor.py](file:///v:/Projects/P_04_Scope/src/nodes/arbiter_nodes/debate_data_extractor.py)**: 전문가 의견과 **공간적 분포 요약(Spatial Summary)** 정보(Wide Mode)를 추출하여 취합합니다.
- **[arbiter_debate_state.py](file:///v:/Projects/P_04_Scope/src/states/arbiter_debate_state.py)**: 전문가 간 논쟁 및 아비터 판정 상태를 관리하는 독립적인 State 정의입니다.

## 2. 논쟁 및 중재 로직 (Debate & Moderation)
- **[expert_debater_nodes.py](file:///v:/Projects/P_04_Scope/src/nodes/arbiter_nodes/expert_debater_nodes.py)**: 각 전문가를 대변하여 논쟁에 참여하는 에이전트 노드입니다.
- **[debate_moderator_node.py](file:///v:/Projects/P_04_Scope/src/nodes/arbiter_nodes/debate_moderator_node.py)**: 논쟁의 순서와 합의 도달 여부를 제어하는 사회자 노드입니다.
- **[fact_checker_node.py](file:///v:/Projects/P_04_Scope/src/nodes/arbiter_nodes/fact_checker_node.py)**: 전문가의 발언이 시각적 증거와 일치하는지 검증합니다.

## 3. 최종 판정 및 종합 (Judge & Synthesis)
- **[judge_node.py](file:///v:/Projects/P_04_Scope/src/nodes/arbiter_nodes/judge_node.py)**: 공간적 구역 정보를 토대로 **발화 인과관계(Causality)**를 분석하고 최종 결론을 도출합니다.
- **[arbiter_expert_graph.py](file:///v:/Projects/P_04_Scope/src/graphs/arbiter_expert_graph.py)**: 전체 아비터 논쟁 시스템의 워크플로우를 정의하는 서브그래프 빌더입니다.

## 4. 시각화 및 리포트 (Reporting & Viz)
- **[verdict_models.py](file:///v:/Projects/P_04_Scope/src/models/verdict_models.py)**: 아비터의 구조화된 최종 판정 결과(`FinalVerdictResult`) 모델입니다.
- **[visualization_node.py](file:///v:/Projects/P_04_Scope/src/nodes/visualization_node.py)**: 분석 결과를 원본 이미지 위에 주석(Annotation)으로 매핑하여 시각 리포트를 생성합니다.
- **[arbiter_debate_prompts.py](file:///v:/Projects/P_04_Scope/src/prompts/arbiter_debate_prompts.py)**: 공간적 맥락 요약을 포함한 아비터 최종 판정용 시스템 프롬프트입니다.

---

### 종합 시스템 파일 목록 (Summary)
@debate_data_extractor.py
@arbiter_debate_state.py
@expert_debater_nodes.py
@debate_moderator_node.py
@fact_checker_node.py
@judge_node.py
@arbiter_expert_graph.py
@verdict_models.py
@visualization_node.py
@arbiter_debate_prompts.py
