"""
[DEPRECATED] Expert 서브그래프 엣지 정의

⚠️ 이 파일은 더 이상 사용되지 않습니다.

이유:
- 모든 Expert 그래프가 Map-Reduce 패턴으로 재설계되었습니다.
- Step-based 노드 구조가 존재하지 않습니다.
- 각 Expert 그래프가 자체적으로 엣지를 정의합니다.

현재 아키텍처:
- contact_expert_graph.py: 자체 엣지 정의 (route_loop_manager, route_component_type)
- aging_expert_graph.py: 자체 엣지 정의 (route_loop_manager, route_component_type)
- deform_expert_graph.py: 자체 엣지 정의 (route_loop_manager, route_component_type)
- necking_expert_graph.py: 자체 엣지 정의 (route_loop_manager, route_component_type, route_verdict_debate)
- tracking_expert_graph.py: 자체 엣지 정의 (route_loop_manager, route_component_type)

Legacy 구조 (더 이상 사용 안 함):
- START -> step1 -> step2 -> step3 -> finalize -> END

현재 구조:
- START -> hotspot_manager -> [Loop] -> verdict -> END

백업:
- expert_edges.py.deprecated (87 lines, 3.15 KB)

변경 일시:
- 2026-01-15: Map-Reduce 패턴 전환 완료
"""

# 이 파일은 향후 필요 시 새로운 공통 엣지 함수를 정의하기 위해 유지됩니다.
# 현재는 각 Expert 그래프가 자체적으로 조건부 엣지를 정의합니다.
