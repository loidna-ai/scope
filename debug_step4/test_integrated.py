
import os
import sys
import logging
import asyncio
from pathlib import Path
import cv2
import json
import shutil

# 프로젝트 루트를 패스에 추가하여 src 모듈 임포트 가능하게 설정
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.utils.io_utils import create_payload_from_image, process_payload_images
from src.utils.image_processing import slice_image, map_hotspots_to_global
from src.utils import get_genai_client
from src.utils.api_concurrency import batch_process_hotspots
from src.prompts.common_prompts import get_micro_evidence_prompt
from src.models.hotspot_models import HotspotDetectionResult
from src.utils.expert_config import get_safety_settings
import config

# --- Setup Logging ---
debug_folder = Path(__file__).parent
debug_folder.mkdir(exist_ok=True)
patch_folder = debug_folder / "patches"
patch_folder.mkdir(exist_ok=True)

log_file = debug_folder / "integrated_test.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

async def run_integrated_test(image_name: str):
    logger.info(f"=== Integrated Detection Test Started: {image_name} ===")
    
    # 1. Image Paths
    data_dir = Path("data")
    image_path = data_dir / image_name
    if not image_path.exists():
        logger.error(f"Image not found: {image_path}")
        return

    # 2. Stage 2: Slicing
    logger.info("--- Stage 2: Slicing ---")
    img_array = cv2.imread(str(image_path))
    h_orig, w_orig = img_array.shape[:2]
    
    patch_size = config.HOTSPOT_PATCH_SIZE
    overlap = config.HOTSPOT_OVERLAP
    max_dim = config.HOTSPOT_MAX_IMAGE_DIMENSION
    
    # Slicing logic (mimicking common_nodes.py)
    # Clear old patches
    for f in patch_folder.glob("*.jpg"): f.unlink()
    
    patches_chunk = []
    patch_generator = slice_image(
        str(image_path), 
        patch_size=patch_size, 
        overlap=overlap,
        max_dimension=max_dim,
        blur_threshold=config.HOTSPOT_BLUR_THRESHOLD,
        edge_threshold=config.HOTSPOT_EDGE_THRESHOLD
    )
    
    for patch in patch_generator:
        patch['source_image_path'] = str(image_path)
        patches_chunk.append(patch)
    
    logger.info(f"Generated {len(patches_chunk)} patches.")
    if not patches_chunk:
        logger.warning("No patches generated (all filtered).")
        return

    # 3. Stage 3: API Call
    logger.info("--- Stage 3: Gemini API ---")
    client = get_genai_client()
    model_name = os.environ.get("GEMINI_MODEL_NAME", config.GEMINI_MODEL_NAME)
    prompt = get_micro_evidence_prompt(patch_size)
    
    api_config = {
        "response_mime_type": "application/json",
        "response_json_schema": HotspotDetectionResult.model_json_schema(),
        "safety_settings": get_safety_settings(),
    }
    
    # Batch size control
    batch_size = config.HOTSPOT_BATCH_SIZE
    patch_batches = [patches_chunk[i:i + batch_size] for i in range(0, len(patches_chunk), batch_size)]
    
    logger.info(f"Calling API for {len(patch_batches)} batches...")
    batch_results = await batch_process_hotspots(
        client=client,
        patch_batches=patch_batches,
        model_name=model_name,
        prompt=prompt,
        api_config=api_config
    )
    
    # 4. Stage 4: Mapping
    logger.info("--- Stage 4: Mapping & Visualization ---")
    image_sizes = {str(image_path): (w_orig, h_orig)}
    global_hotspots = map_hotspots_to_global(batch_results, image_sizes)
    
    logger.info(f"Detected {len(global_hotspots)} global hotspots.")
    
    # Visualization
    img_viz = cv2.imread(str(image_path))
    for i, h in enumerate(global_hotspots):
        box = h['box_2d']
        ymin = int(box['ymin'] * h_orig / 1000)
        xmin = int(box['xmin'] * w_orig / 1000)
        ymax = int(box['ymax'] * h_orig / 1000)
        xmax = int(box['xmax'] * w_orig / 1000)
        
        cv2.rectangle(img_viz, (xmin, ymin), (xmax, ymax), (0, 255, 0), 3)
        cv2.putText(img_viz, f"#{i+1} {h['visual_evidence'][:20]}...", (xmin, ymin - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        
        logger.info(f"Hotspot #{i+1}: LocalIdx:{h.get('image_index')} Box:{box}")

    output_path = debug_folder / f"mapping_result_{image_path.stem}.jpg"
    cv2.imwrite(str(output_path), img_viz)
    logger.info(f"Result visualization saved to: {output_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("image", help="Image name in data/ directory")
    args = parser.parse_args()
    
    asyncio.run(run_integrated_test(args.image))
