
import os
import sys
import asyncio
import logging
from pathlib import Path
import json
import cv2

# 프로젝트 루트를 패스에 추가
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.utils import get_genai_client
from src.utils.image_processing import (
    get_image_size, 
    slice_multiple_images, 
    map_hotspots_to_global
)
from src.prompts.common_prompts import get_micro_evidence_prompt
from src.models.hotspot_models import HotspotDetectionResult
from src.utils.expert_config import get_safety_settings
from src.utils.api_concurrency import batch_process_hotspots
import config

# --- Setup Logging ---
debug_folder = Path(__file__).parent
log_file = debug_folder / "test_actual_workflow.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

async def test_workflow_up_to_step4(image_name: str):
    logger.info(f"=== Actual Project Workflow Test (Up to Step 4): {image_name} ===")
    
    # 0. 초기 설정 (Hotspot Detector Node 내부 로직 재현)
    client = get_genai_client()
    image_paths = [str(Path("data") / image_name)]
    if not os.path.exists(image_paths[0]):
        logger.error(f"Image not found: {image_paths[0]}")
        return

    # [1단계는 입력 처리이므로 생략하고 2단계부터 진행]
    
    # 2. Image Slicing (Step 2)
    logger.info("[Step 2] Image Slicing...")
    all_patches = slice_multiple_images(
        image_paths,
        patch_size=config.HOTSPOT_PATCH_SIZE,
        overlap=config.HOTSPOT_OVERLAP,
        max_dimension=config.HOTSPOT_MAX_IMAGE_DIMENSION,
        blur_threshold=config.HOTSPOT_BLUR_THRESHOLD,
        edge_threshold=config.HOTSPOT_EDGE_THRESHOLD
    )
    logger.info(f"Generated {len(all_patches)} patches.")

    # 3. Parallel API Execution (Step 3)
    logger.info("[Step 3] Parallel API Execution...")
    batch_size = config.HOTSPOT_BATCH_SIZE
    patch_batches = [all_patches[i:i + batch_size] for i in range(0, len(all_patches), batch_size)]
    
    model_name = os.environ.get("GEMINI_MODEL_NAME", config.GEMINI_MODEL_NAME)
    prompt = get_micro_evidence_prompt(config.HOTSPOT_PATCH_SIZE)
    
    json_schema = HotspotDetectionResult.model_json_schema()
    api_config = {
        "response_mime_type": "application/json",
        "response_json_schema": json_schema,
        "safety_settings": get_safety_settings(),
    }

    batch_results = await batch_process_hotspots(
        client=client,
        patch_batches=patch_batches,
        model_name=model_name,
        prompt=prompt,
        api_config=api_config
    )

    # 4. Aggregation & Coordinate Mapping (Step 4)
    logger.info("[Step 4] Aggregation & Coordinate Mapping...")
    image_sizes = {path: get_image_size(path) for path in image_paths}
    raw_hotspots = map_hotspots_to_global(batch_results, image_sizes)
    
    # --- 결과 시각화 (검증용) ---
    logger.info(f"Detected {len(raw_hotspots)} hotspots before NMS.")
    img_viz = cv2.imread(image_paths[0])
    h_orig, w_orig = img_viz.shape[:2]
    
    for i, h in enumerate(raw_hotspots):
        box = h['box_2d']
        ymin, xmin, ymax, xmax = box['ymin'], box['xmin'], box['ymax'], box['xmax']
        
        # 0-1000 -> Pixels
        ry1, rx1 = int(ymin * h_orig / 1000), int(xmin * w_orig / 1000)
        ry2, rx2 = int(ymax * h_orig / 1000), int(xmax * w_orig / 1000)
        
        cv2.rectangle(img_viz, (rx1, ry1), (rx2, ry2), (0, 0, 255), 5) # NMS 전이므로 빨간색
        cv2.putText(img_viz, f"Raw#{i+1}", (rx1, ry1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        
        logger.info(f"Raw Hotspot #{i+1}: ImageIndex={h.get('image_index')}, GlobalBox={box}")

    output_path = debug_folder / f"actual_workflow_step4_{Path(image_name).stem}.jpg"
    cv2.imwrite(str(output_path), img_viz)
    logger.info(f"Step 4 visualization saved to: {output_path}")
    
    logger.info("=== Actual Project Workflow Test (Up to Step 4) Completed ===")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        img = "IMG_1634.JPG"
    else:
        img = sys.argv[1]
    asyncio.run(test_workflow_up_to_step4(img))
