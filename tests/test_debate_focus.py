"""
Analyst-Critic 개선 기능 단위 테스트
특정 부위 집중 재분석 검증
"""
import sys
sys.path.append('C:/Users/loidn/Documents/Projects/P_04_Scope')

from src.nodes.necking_nodes import extract_critiqued_hotspots

def test_extract_critiqued_hotspots():
    """Critic 지적 Hotspot 추출 테스트"""
    
    # Mock 데이터: 5개 Hotspot
    all_results = [
        {"hotspot_info": {"id": 2, "damage_type": "Exposed Conductor"}},
        {"hotspot_info": {"id": 3, "damage_type": "Conductor Deformation"}},
        {"hotspot_info": {"id": 4, "damage_type": "Insulation Melting"}},
        {"hotspot_info": {"id": 6, "damage_type": "Localized Melting"}},
        {"hotspot_info": {"id": 8, "damage_type": "Carbonization"}},
    ]
    
    print("=" * 60)
    print("테스트 1: Critic이 Hotspot #3, #6만 언급")
    print("=" * 60)
    critique_1 = """
    {
      "objection_type": "대안 가설 미검토",
      "critical_question": "Hotspot #3과 Hotspot #6에서 외부 화재 패턴이 관찰되는데, 
                           Hotspot #2만 반단선이라고 단정할 수 있는가?",
      "alternative_interpretation": "Spot #2도 화재 유도 아크일 가능성"
    }
    """
    
    focused = extract_critiqued_hotspots(critique_1, all_results)
    print(f"📌 추출된 Hotspot IDs: {[r['hotspot_info']['id'] for r in focused]}")
    print(f"✅ 예상: [2, 3, 6] | 실제: {sorted([r['hotspot_info']['id'] for r in focused])}")
    assert sorted([r['hotspot_info']['id'] for r in focused]) == [2, 3, 6], "Test 1 Failed!"
    print("✅ Test 1 Passed!\n")
    
    print("=" * 60)
    print("테스트 2: Critic이 Hotspot #2만 집중 지적")
    print("=" * 60)
    critique_2 = """
    {
      "objection_type": "증거 과대해석",
      "critical_question": "Hotspot #2의 세장화와 미세 망울을 '발화 원인'으로 단정한 근거는?",
      "alternative_interpretation": "#2는 2차적 인장 파단일 가능성"
    }
    """
    
    focused = extract_critiqued_hotspots(critique_2, all_results)
    print(f"📌 추출된 Hotspot IDs: {[r['hotspot_info']['id'] for r in focused]}")
    print(f"✅ 예상: [2] | 실제: {[r['hotspot_info']['id'] for r in focused]}")
    assert [r['hotspot_info']['id'] for r in focused] == [2], "Test 2 Failed!"
    print("✅ Test 2 Passed!\n")
    
    print("=" * 60)
    print("테스트 3: Critic이 특정 Hotspot을 언급하지 않음")
    print("=" * 60)
    critique_3 = """
    {
      "objection_type": "프로파일 누락 간과",
      "critical_question": "전체적으로 슬리빙이 불명확한데 High 판정한 근거는?",
      "alternative_interpretation": "보수적 판정 필요"
    }
    """
    
    focused = extract_critiqued_hotspots(critique_3, all_results)
    print(f"📌 추출된 Hotspot IDs: {[r['hotspot_info']['id'] for r in focused]}")
    print(f"✅ 예상: 전체 5개 반환 (언급 없음) | 실제: {len(focused)}개")
    assert len(focused) == 5, "Test 3 Failed!"
    print("✅ Test 3 Passed!\n")
    
    print("=" * 60)
    print("테스트 4: 다양한 표기법 (Spot, hotspot, #숫자)")
    print("=" * 60)
    critique_4 = """
    Spot 2의 판정과 spot #6의 판정이 모순됩니다.
    또한 hotspot 3도 재검토가 필요합니다.
    """
    
    focused = extract_critiqued_hotspots(critique_4, all_results)
    print(f"📌 추출된 Hotspot IDs: {sorted([r['hotspot_info']['id'] for r in focused])}")
    print(f"✅ 예상: [2, 3, 6] | 실제: {sorted([r['hotspot_info']['id'] for r in focused])}")
    assert sorted([r['hotspot_info']['id'] for r in focused]) == [2, 3, 6], "Test 4 Failed!"
    print("✅ Test 4 Passed!\n")
    
    print("🎉 모든 테스트 통과!")
    print("=" * 60)

if __name__ == "__main__":
    test_extract_critiqued_hotspots()
