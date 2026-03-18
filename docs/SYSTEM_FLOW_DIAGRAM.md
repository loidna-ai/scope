# Fire CSI AI Agent — 시스템 흐름 블록도

## 전체 파이프라인 (Contact & Necking 전문가 기반)

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                           Fire CSI AI Agent Pipeline                                     │
│                    (Multi-Agent Cross-Validation Architecture)                            │
└─────────────────────────────────────────────────────────────────────────────────────────┘

                                    ┌─────────────┐
                                    │   INPUT     │
                                    │  (Image)    │
                                    └──────┬──────┘
                                           │
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│  PHASE 1: 공통 전처리 (Common Preprocessing)                                              │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│    ┌─────────────────────────┐         ┌─────────────────────────┐                       │
│    │  Hotspot Detector       │────────▶│  Preprocessor           │                       │
│    │  (Overlap Grid + NMS)   │         │  Crop │ Classify │ Enhance│                       │
│    └─────────────────────────┘         └────────────┬────────────┘                       │
│                                                     │                                    │
│                                                     │ preprocessed_hotspots               │
└─────────────────────────────────────────────────────┼────────────────────────────────────┘
                                                      │
                                                      ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│  PHASE 2: 전문가 병렬 분석 (Expert Parallel Analysis) — Map-Reduce Pattern                │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│    ┌─────────────────────────────────────┐    ┌─────────────────────────────────────┐   │
│    │  Contact Expert Subgraph             │    │  Necking Expert Subgraph             │   │
│    │  (접촉불량 전문가)                    │    │  (반단선 전문가)                      │   │
│    ├─────────────────────────────────────┤    ├─────────────────────────────────────┤   │
│    │  distribute_work (Fan-Out)           │    │  distribute_work (Fan-Out)           │   │
│    │         │                            │    │         │                            │   │
│    │         ▼                            │    │         ▼                            │   │
│    │  ┌──────────────┐                    │    │  ┌──────────────┐                    │   │
│    │  │ Worker × N   │  (ROI 분석)        │    │  │ Worker × N   │  (ROI 분석)        │   │
│    │  └──────┬───────┘                    │    │  └──────┬───────┘                    │   │
│    │         │                            │    │         │                            │   │
│    │         ▼                            │    │         ▼                            │   │
│    │  ┌──────────────┐                    │    │  ┌──────────────┐                    │   │
│    │  │ Supervisor   │  (Reduce)           │    │  │ Supervisor   │  (Reduce)           │   │
│    │  └──────┬───────┘                    │    │  └──────┬───────┘                    │   │
│    │         │                            │    │         │                            │   │
│    │         ▼                            │    │         ▼                            │   │
│    │  ┌──────────────────────────────┐   │    │  ┌──────────────────────────────┐   │   │
│    │  │ Analyst-Critic Debate Loop   │   │    │  │ Analyst-Critic Debate Loop   │   │   │
│    │  │  Analyst ◀──────▶ Critic     │   │    │  │  Analyst ◀──────▶ Critic     │   │   │
│    │  │  (가설 수립)    (교차검증)    │   │    │  │  (가설 수립)    (교차검증)    │   │   │
│    │  └──────────────┬───────────────┘   │    │  └──────────────┬───────────────┘   │   │
│    │                 │                   │    │                 │                   │   │
│    │                 ▼                   │    │                 ▼                   │   │
│    │  ┌──────────────┐                   │    │  ┌──────────────┐                    │   │
│    │  │ Finalize     │                   │    │  │ Finalize     │                    │   │
│    │  └──────┬───────┘                   │    │  └──────┬───────┘                    │   │
│    └─────────┼──────────────────────────┘    └─────────┼──────────────────────────┘   │
│              │                                           │                               │
│              │ expert_reports, expert_confidence_scores   │                               │
│              │ expert_evidence, expert_analysis_results  │                               │
└──────────────┼───────────────────────────────────────────┼───────────────────────────────┘
               │                                           │
               └───────────────────┬───────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│  PHASE 3: Arbiter 최종 판정 (Cross-Expert Consensus)                                      │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│    │ debate_init  │───▶│  Debater     │───▶│ Fact Checker │───▶│  Moderator   │          │
│    │ (합의 체크)   │    │ (Contact/    │    │ (증거 검증)   │    │ (토론 진행)   │          │
│    └──────────────┘    │  Necking)    │    └──────────────┘    └──────┬───────┘          │
│                        └──────────────┘         │                     │                   │
│                                ▲                │                     │                   │
│                                └────────────────┴─────────────────────┘                   │
│                                         (불일치 시 반복)                                    │
│                                                │                                           │
│                                                ▼                                           │
│                                        ┌──────────────┐                                    │
│                                        │    Judge     │                                    │
│                                        │ (최종 판정)  │                                    │
│                                        └──────┬───────┘                                    │
└───────────────────────────────────────────────┼───────────────────────────────────────────┘
                                                │
                                                ▼
                                        ┌──────────────┐
                                        │   OUTPUT     │
                                        │ final_verdict│
                                        └──────────────┘
```

---

## Mermaid 버전 (온라인 렌더링용)

```mermaid
flowchart TB
    subgraph INPUT[" "]
        A[Input Image]
    end

    subgraph PHASE1["Phase 1: Common Preprocessing"]
        B[Hotspot Detector<br/>Overlap Grid + NMS]
        C[Preprocessor<br/>Crop | Classify | Enhance]
    end

    subgraph PHASE2["Phase 2: Expert Parallel Analysis"]
        subgraph CONTACT["Contact Expert"]
            C1[distribute_work]
            C2[Worker × N]
            C3[Supervisor]
            C4[Analyst ↔ Critic]
            C5[Finalize]
        end
        subgraph NECKING["Necking Expert"]
            N1[distribute_work]
            N2[Worker × N]
            N3[Supervisor]
            N4[Analyst ↔ Critic]
            N5[Finalize]
        end
    end

    subgraph PHASE3["Phase 3: Arbiter"]
        D[debate_init]
        E[Debater]
        F[Fact Checker]
        G[Moderator]
        H[Judge]
    end

    subgraph OUTPUT[" "]
        I[final_verdict]
    end

    A --> B --> C
    C --> C1
    C --> N1
    C1 --> C2 --> C3 --> C4 --> C5
    N1 --> N2 --> N3 --> N4 --> N5
    C5 --> D
    N5 --> D
    D --> E --> F --> G
    G -->|불일치| E
    G -->|합의| H
    H --> I
```

---

## 주요 구성요소 정의

| 구성요소 | 설명 |
|----------|------|
| **Hotspot Detector** | 이미지 패치 분할 및 병렬 탐지, NMS 기반 중복 제거 |
| **Preprocessor** | ROI 크롭, 컴포넌트 분류, 해상도 향상 (1회 공통 처리) |
| **Worker** | 개별 Hotspot 단위 정밀 분석 (Map 연산) |
| **Supervisor** | Worker 결과 취합 및 초기 가설 도출 (Reduce) |
| **Analyst** | 증거 기반 가설 수립 |
| **Critic** | 가설의 맹점·과대해석 검증 (교차검증) |
| **Finalize** | Debate 결과를 반영한 최종 전문가 결론 확정 |
| **Debater** | 전문가별 의견 제시 및 반박 |
| **Fact Checker** | 주장-증거 일관성 검증 |
| **Moderator** | 토론 순서 및 흐름 제어 |
| **Judge** | 최종 화재 원인 판정 |
