
import os
import sys
import logging
import asyncio
from pathlib import Path
import json

# 프로젝트 루트를 패스에 추가하여 src 모듈 임포트 가능하게 설정
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.utils import get_genai_client
from src.utils.api_concurrency import batch_process_hotspots
from src.prompts.common_prompts import get_micro_evidence_prompt
from src.models.hotspot_models import HotspotDetectionResult
from src.utils.expert_config import get_safety_settings
import config

# --- Setup Logging ---
debug_folder = Path(__file__).parent
log_file = debug_folder / "test_stage3.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

async def run_stage3_test():
    logger.info("=== Stage 3 Debugging Test Started ===")
    
    # 1. 클라이언트 및 설정 준비
    try:
        client = get_genai_client()
    except Exception as e:
        logger.error(f"Failed to get GenAI client: {e}")
        return

    model_name = os.environ.get("GEMINI_MODEL_NAME", config.GEMINI_MODEL_NAME)
    prompt = get_micro_evidence_prompt(config.HOTSPOT_PATCH_SIZE)
    
    json_schema = HotspotDetectionResult.model_json_schema()
    # Pydantic schema update to ensure 'hotspots' is required
    req = json_schema.setdefault("required", [])
    if "hotspots" not in req: req.append("hotspots")
    
    api_config = {
        "response_mime_type": "application/json",
        "response_json_schema": json_schema,
        "safety_settings": get_safety_settings(),
    }

    logger.info(f"Model: {model_name}")
    logger.info(f"Batch Size (Config): {config.HOTSPOT_BATCH_SIZE}")

    # 2. 테스트용 패치 준비 (Stage 2 결과물 재사용)
    # Poor_Contact_001.jpg (1개 패치) 와 IMG_1634.JPG (6개 패치 중 일부)를 섞어서 배치 구성
    data_dir = Path("data")
    patch_source_folder = Path("debug_step2/patches")
    
    # 만약 debug_step2가 없다면 직접 생성 (간략화)
    if not patch_source_folder.exists():
        logger.error("Stage 2 patches not found. Please run Stage 2 first.")
        return

    patches_chunk = []
    # 패치 3장 선택 (다양한 내용이 포함되도록)
    patch_files = sorted(list(patch_source_folder.glob("*.jpg")))[:3]
    if not patch_files:
        logger.error("No patches found in debug_step2/patches.")
        return

    for idx, p_path in enumerate(patch_files):
        with open(p_path, "rb") as f:
            patches_chunk.append({
                'image_bytes': f.read(),
                'source_image_path': str(p_path),
                'index': (0, idx)
            })
    
    logger.info(f"Test Batch size for this specific call: {len(patches_chunk)} patches")
    for i, p in enumerate(patch_files):
        logger.info(f"  Patch {i+1}: {p.name}")

    # 3. API 호출
    # batch_process_hotspots는 List[List[Dict]]를 받습니다.
    patch_batches = [patches_chunk]
    
    try:
        logger.info("Calling batch_process_hotspots...")
        start_time = asyncio.get_event_loop().time()
        results = await batch_process_hotspots(
            client=client,
            patch_batches=patch_batches,
            model_name=model_name,
            prompt=prompt,
            api_config=api_config
        )
        duration = asyncio.get_event_loop().time() - start_time
        logger.info(f"API Call Duration: {duration:.2f}s")
        
        # 4. 결과 분석
        if not results:
            logger.error("API returned no results.")
            return

        batch_info, hotspots = results[0]
        logger.info(f"API Result - Response contains {len(hotspots)} hotspots.")
        
        # 결과물 저장
        result_file = debug_folder / "api_response_raw.json"
        with open(result_file, "w", encoding="utf-8") as f:
            # result[0][1]은 [Hotspot, ...] 객체 리스트이므로 dict로 변환
            serializable_hotspots = [h.model_dump() if hasattr(h, "model_dump") else h for h in hotspots]
            json.dump(serializable_hotspots, f, indent=2, ensure_ascii=False)
        
        # 상세 검증
        for i, h in enumerate(hotspots):
            h_dict = h.model_dump() if hasattr(h, "model_dump") else h
            img_idx = h_dict.get('image_index', 1)
            severity = h_dict.get('severity_score', 0)
            box = h_dict.get('box_2d', {})
            evidence = h_dict.get('visual_evidence', "")
            
            logger.info(f"Hotspot {i+1}:")
            logger.info(f"  - Image Index: {img_idx} (Correct for this patch?)")
            logger.info(f"  - Severity: {severity}")
            logger.info(f"  - Box: {box}")
            logger.info(f"  - Evidence: {evidence}")
            
            # 인덱스 범위 체크
            if img_idx < 1 or img_idx > len(patches_chunk):
                logger.error(f"  [ERROR] image_index {img_idx} is out of range [1, {len(patches_chunk)}]")
            else:
                patch_name = patch_files[img_idx-1].name
                logger.info(f"  - Associated with patch: {patch_name}")

        # 요약 리포트 작성
        summary_file = debug_folder / "summary.txt"
        with open(summary_file, "w", encoding="utf-8") as f:
            f.write("=== Stage 3 API Response Debug Summary ===\n")
            f.write(f"Model: {model_name}\n")
            f.write(f"Input Patches: {len(patches_chunk)}\n")
            f.write(f"Hotspots Detected: {len(hotspots)}\n")
            f.write(f"Response saved to: {result_file.name}\n\n")
            f.write("Detections:\n")
            for i, h in enumerate(hotspots):
                h_dict = h.model_dump() if hasattr(h, "model_dump") else h
                f.write(f"  #{i+1} [ImgIdx:{h_dict.get('image_index')}] Sev:{h_dict.get('severity_score')} - {h_dict.get('visual_evidence')[:50]}...\n")

    except Exception as e:
        logger.error(f"Error during API call or processing: {e}", exc_info=True)

    logger.info("=== Stage 3 Debugging Test Completed ===")

if __name__ == "__main__":
    asyncio.run(run_stage3_test())
