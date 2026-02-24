
import sys
import os
from pathlib import Path

# 프로젝트 루트 경로 설정
project_root = Path.cwd().parent if Path.cwd().name == "notebook" else Path.cwd()
sys.path.insert(0, str(project_root))

print("=== Expert Graph Compilation Check ===")

try:
    from src.graphs.aging_expert_graph import build_aging_expert_graph
    print("✅ Aging Expert Graph Import Successful")
    build_aging_expert_graph()
    print("✅ Aging Expert Graph Build Successful")
except Exception as e:
    print(f"❌ Aging Expert Error: {e}")

try:
    from src.graphs.contact_expert_graph import build_contact_expert_graph
    print("✅ Contact Expert Graph Import Successful")
    build_contact_expert_graph()
    print("✅ Contact Expert Graph Build Successful")
except Exception as e:
    print(f"❌ Contact Expert Error: {e}")

try:
    from src.graphs.deform_expert_graph import build_deform_expert_graph
    print("✅ Deform Expert Graph Import Successful")
    build_deform_expert_graph()
    print("✅ Deform Expert Graph Build Successful")
except Exception as e:
    print(f"❌ Deform Expert Error: {e}")

try:
    from src.graphs.necking_expert_graph import build_necking_expert_graph
    # Verify conditional logical
    # from src.graphs.necking_expert_graph import route_component_type
    print("✅ Necking Expert Graph Import Successful")
    build_necking_expert_graph()
    print("✅ Necking Expert Graph Build Successful")
except Exception as e:
    print(f"❌ Necking Expert Error: {e}")

try:
    from src.graphs.tracking_expert_graph import build_tracking_expert_graph
    print("✅ Tracking Expert Graph Import Successful")
    build_tracking_expert_graph()
    print("✅ Tracking Expert Graph Build Successful")
except Exception as e:
    print(f"❌ Tracking Expert Error: {e}")

try:
    from src.graphs.arbiter_expert_graph import build_arbiter_expert_graph
    print("✅ Arbiter Expert Graph Import Successful")
    build_arbiter_expert_graph()
    print("✅ Arbiter Expert Graph Build Successful")
except Exception as e:
    print(f"❌ Arbiter Expert Error: {e}")

print("=== Check Complete ===")
