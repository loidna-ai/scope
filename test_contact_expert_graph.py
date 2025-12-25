"""
Contact Expert Graph 테스트 스크립트
정리 후 정상 작동 여부 확인
"""
import sys
import json
import base64
from pathlib import Path
from src.graphs.contact_expert_graph import contact_expert_wrapper_node

def create_test_payload(image_path: str):
    """테스트용 payload 생성"""
    with open(image_path, "rb") as f:
        image_data = f.read()
    
    image_base64 = base64.b64encode(image_data).decode('utf-8')
    
    payload = [{
        "inline_data": {
            "mime_type": "image/png" if image_path.lower().endswith('.png') else "image/jpeg",
            "data": image_base64
        }
    }]
    
    return payload

def main():
    if len(sys.argv) < 2:
        print("사용법: python test_contact_expert_graph.py <이미지_경로>")
        sys.exit(1)
    
    image_path = sys.argv[1]
    
    if not Path(image_path).exists():
        print(f"❌ 이미지 파일을 찾을 수 없습니다: {image_path}")
        sys.exit(1)
    
    print("=" * 60)
    print("Contact Expert Graph 테스트")
    print("=" * 60)
    print(f"\n테스트 이미지: {image_path}")
    
    # Payload 생성
    print("\n[1] Payload 생성 중...")
    try:
        payload = create_test_payload(image_path)
        print(f"  ✅ Payload 생성 완료 (이미지 크기: {Path(image_path).stat().st_size} bytes)")
    except Exception as e:
        print(f"  ❌ Payload 생성 실패: {e}")
        sys.exit(1)
    
    # InvestigationState 초기화
    print("\n[2] InvestigationState 초기화 중...")
    try:
        state = {
            "payload": payload,
            "expert_reports": [],
            "expert_analysis_results": {},
            "expert_confidence_scores": {},
            "expert_evidence": {},
            "errors": []
        }
        print("  ✅ InvestigationState 초기화 완료")
    except Exception as e:
        print(f"  ❌ 초기화 실패: {e}")
        sys.exit(1)
    
    # Contact Expert Graph 실행
    print("\n[3] Contact Expert Graph 실행 중...")
    print("  (이 작업은 몇 분이 걸릴 수 있습니다...)")
    try:
        result = contact_expert_wrapper_node(state)
        print("  ✅ Contact Expert Graph 실행 완료")
    except Exception as e:
        print(f"  ❌ 실행 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # 결과 출력
    print("\n" + "=" * 60)
    print("📊 테스트 결과")
    print("=" * 60)
    
    # 에러 확인
    if result.get("errors"):
        print("\n❌ 에러 발생:")
        for error in result["errors"]:
            print(f"  - {error}")
    
    # 리포트 출력
    if result.get("expert_reports"):
        print("\n📄 전문가 리포트:")
        for i, report in enumerate(result["expert_reports"], 1):
            print(f"\n[리포트 {i}]")
            print("-" * 60)
            print(report[:500] + "..." if len(report) > 500 else report)
            print("-" * 60)
    
    # 신뢰도 점수 출력
    if result.get("expert_confidence_scores"):
        print("\n📊 신뢰도 점수:")
        for expert, score in result["expert_confidence_scores"].items():
            print(f"  - {expert}: {score}%")
    
    # 증거 출력
    if result.get("expert_evidence"):
        print("\n🔍 증거:")
        for expert, evidence_list in result["expert_evidence"].items():
            print(f"\n  [{expert} 전문가]")
            for ev in evidence_list:
                step_name = ev.get("step", "Unknown")
                detail = ev.get("detail", "")[:100]
                print(f"    - {step_name}: {detail}...")
    
    # Step 결과 출력
    if result.get("expert_analysis_results"):
        print("\n📋 단계별 분석 결과:")
        for expert, steps in result["expert_analysis_results"].items():
            print(f"\n  [{expert} 전문가]")
            for step_key, step_result in steps.items():
                if isinstance(step_result, dict):
                    confidence = step_result.get("confidence", "N/A")
                    print(f"    - {step_key}: 신뢰도 {confidence}%")
    
    # Agent 추론 과정 확인
    if result.get("agent_reasoning_history"):
        print(f"\n💭 Agent 추론 과정: {len(result['agent_reasoning_history'])}개 메시지")
    
    # JSON 파일로 저장
    output_file = "test_contact_expert_result.json"
    print(f"\n💾 결과를 저장합니다: {output_file}")
    try:
        # JSON 직렬화 가능한 형태로 변환
        json_result = {
            "expert_reports": result.get("expert_reports", []),
            "expert_confidence_scores": result.get("expert_confidence_scores", {}),
            "expert_evidence": result.get("expert_evidence", {}),
            "expert_analysis_results": result.get("expert_analysis_results", {}),
            "agent_reasoning_history": result.get("agent_reasoning_history", []),
            "errors": result.get("errors", [])
        }
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(json_result, f, ensure_ascii=False, indent=2)
        
        print(f"  ✅ 저장 완료: {output_file}")
    except Exception as e:
        print(f"  ⚠️ 저장 실패: {e}")
    
    print("\n" + "=" * 60)
    print("✅ 테스트 완료")
    print("=" * 60)

if __name__ == "__main__":
    main()

