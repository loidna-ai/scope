"""
Image Processing Utilities for Overlap Grid Strategy
"""
import io
import os
from typing import List, Tuple, Dict, Any, Optional, Iterator

from PIL import Image
import numpy as np

from src.utils.logging_config import setup_logger
from src.utils.image_utils import load_image_safe

logger = setup_logger(__name__)

import cv2

def resize_image_if_needed(img_bytes: bytes, max_dim: int, quality: int) -> bytes:
    """이미지가 max_dim 초과 시 리사이즈 후 bytes 반환. 작을 경우 통과."""
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = img.size
    if max(w, h) <= max_dim:
        return img_bytes
    scale = max_dim / max(w, h)
    new_w, new_h = int(w * scale), int(h * scale)
    img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img_resized.save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()

def slice_image(
    image_path: str, 
    patch_size: int = 1024, 
    overlap: int = 200,
    min_patch_size: int = 512,
    max_dimension: int = 2048,
    blur_threshold: float = 50.0,
    edge_threshold: int = 15
) -> Iterator[Dict[str, Any]]:
    """
    Slices an image into overlapping patches with Dynamic Downscaling & Background Filtering.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")
        
    try:
        # load_image_safe returns BGR numpy array
        img_array = load_image_safe(image_path)
        if img_array is None:
            raise ValueError(f"Failed to load image: {image_path}")
            
        h, w = img_array.shape[:2]
        
        # 1. Dynamic Downscaling (이미지가 너무 크면 축소)
        scale_factor = 1.0
        if max(w, h) > max_dimension:
            scale_factor = max_dimension / float(max(w, h))
            new_w = int(w * scale_factor)
            new_h = int(h * scale_factor)
            logger.info(f"Oversized image detected ({w}x{h}). Scaling down to {new_w}x{new_h} (Factor {scale_factor:.2f})")
            img_array = cv2.resize(img_array, (new_w, new_h), interpolation=cv2.INTER_AREA)
            w, h = new_w, new_h
            
        # Convert BGR to RGB for PIL compatibility
        img_rgb = img_array[:, :, ::-1]
        img = Image.fromarray(img_rgb)
        
        # Calculate stride (step size)
        stride = patch_size - overlap
        if stride <= 0:
            raise ValueError(f"Overlap ({overlap}) must be smaller than patch_size ({patch_size})")
            
        def get_starts(total_length, window, stride):
            starts = []
            curr = 0
            while curr + window < total_length:
                starts.append(curr)
                curr += stride
            starts.append(max(0, total_length - window))
            return sorted(list(set(starts)))

        x_coords = get_starts(w, patch_size, stride)
        y_coords = get_starts(h, patch_size, stride)
        
        filtered_out_count = 0
        yielded_count = 0
        # 모든 패치가 필터링될 경우 폴백용: (laplacian_var + edge_density) 최고 패치 보관
        best_rejected: Optional[Tuple[Dict[str, Any], float, float]] = None

        for r_idx, y in enumerate(y_coords):
            for c_idx, x in enumerate(x_coords):
                x_end = min(x + patch_size, w)
                y_end = min(y + patch_size, h)
                
                # Check patch size
                pw, ph = x_end - x, y_end - y
                if pw < min_patch_size or ph < min_patch_size:
                    # Only skip if image itself is larger than min_patch_size
                    if w > min_patch_size and h > min_patch_size:
                        continue
                        
                # Extract patch as numpy BGR array for CV2 analysis
                patch_bgr = img_array[y:y_end, x:x_end]
                
                # 2. OpenCV Background Filtering (Blur & Edge density)
                gray = cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2GRAY)
                
                # Blur check (Laplacian variance)
                laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
                
                # Edge check (Canny edge average density)
                edges = cv2.Canny(gray, 50, 150)
                edge_density = np.mean(edges)
                
                if laplacian_var < blur_threshold or edge_density < edge_threshold:
                    filtered_out_count += 1
                    logger.debug(f"Slice ({c_idx},{r_idx}) filtered out | Variance: {laplacian_var:.1f}, Edge: {edge_density:.1f}")
                    # 폴백용: 필터링된 패치 중 최고 점수 보관 (모두 필터링 시 사용)
                    box = (x, y, x_end, y_end)
                    patch_img = img.crop(box)
                    buf = io.BytesIO()
                    patch_img.save(buf, format="JPEG", quality=95)
                    patch_bytes = buf.getvalue()
                    rejected_data = {
                        "image_bytes": patch_bytes,
                        "offset": (x, y),
                        "original_offset": (int(x / scale_factor), int(y / scale_factor)),
                        "size": (pw, ph),
                        "original_size": (int(pw / scale_factor), int(ph / scale_factor)),
                        "index": (r_idx, c_idx),
                        "scale_factor": scale_factor,
                        "debug_metrics": {"variance": round(laplacian_var, 1), "edge": round(edge_density, 1)}
                    }
                    score = laplacian_var + edge_density
                    if best_rejected is None or score > best_rejected[1] + best_rejected[2]:
                        best_rejected = (rejected_data, laplacian_var, edge_density)
                    continue
                
                # Pass filtering: Crop PIL image for JPEG bytes
                box = (x, y, x_end, y_end)
                patch_img = img.crop(box)
                
                # Convert to bytes
                buf = io.BytesIO()
                patch_img.save(buf, format="JPEG", quality=95)
                patch_bytes = buf.getvalue()
                
                yielded_count += 1
                yield {
                    "image_bytes": patch_bytes,
                    "offset": (x, y),       # Offset in the RESIZED image
                    "original_offset": (int(x / scale_factor), int(y / scale_factor)), # Absolute pixel offset in ORIGINAL image
                    "size": (pw, ph),
                    "original_size": (int(pw / scale_factor), int(ph / scale_factor)), # Patch size in ORIGINAL pixels
                    "index": (r_idx, c_idx),
                    "scale_factor": scale_factor,
                    "debug_metrics": {"variance": round(laplacian_var, 1), "edge": round(edge_density, 1)}
                }
        
        # 폴백: 모든 패치가 필터링되어 0개가 되면, 최고 점수 패치 1개를 강제 전달 (파이프라인 중단 방지)
        if yielded_count == 0 and best_rejected is not None:
            logger.warning(
                f"All {filtered_out_count} patch(es) filtered out. Fallback: passing best rejected patch "
                f"(variance={best_rejected[1]:.1f}, edge={best_rejected[2]:.1f}) to avoid pipeline failure."
            )
            yield best_rejected[0]
                
        logger.info(f"Slicing complete: Filtered out {filtered_out_count} blank/blurry background patches using CV2 thresholds.")
        
    except Exception as e:
        logger.error("Error slicing image: %s", e, exc_info=True)
        # Generator must yield nothing on error or handle it gracefully
        return

def map_box_to_global(
    box_2d: Dict[str, int], 
    original_offset: Tuple[int, int], 
    original_patch_size: Tuple[int, int],
    original_full_size: Tuple[int, int]
) -> Dict[str, int]:
    """
    Maps bounding box from Patch Local Normalized Coordinates (0-1000) to Global Normalized Coordinates (0-1000).
    Uses absolute original pixels to avoid compounding scale errors.
    
    Args:
        box_2d: Dict with ymin, xmin, ymax, xmax (0-1000 relative to patch)
        original_offset: (x, y) absolute pixels in ORIGINAL image
        original_patch_size: (width, height) absolute pixels of the patch in ORIGINAL image
        original_full_size: (width, height) absolute pixels of the ORIGINAL full image
        
    Returns:
        Dict with ymin, xmin, ymax, xmax (0-1000 relative to original global image)
    """
    # 1. Transform from Patch Normalized (0-1000) -> Global Pixels
    # gy = (norm_y / 1000 * patch_h) + offset_y
    gy_min = (box_2d.get("ymin", 0) / 1000.0 * original_patch_size[1]) + original_offset[1]
    gx_min = (box_2d.get("xmin", 0) / 1000.0 * original_patch_size[0]) + original_offset[0]
    gy_max = (box_2d.get("ymax", 0) / 1000.0 * original_patch_size[1]) + original_offset[1]
    gx_max = (box_2d.get("xmax", 0) / 1000.0 * original_patch_size[0]) + original_offset[0]
    
    # 2. Clip to original full image bounds
    W, H = original_full_size
    gy_min = max(0, min(gy_min, H))
    gx_min = max(0, min(gx_min, W))
    gy_max = max(0, min(gy_max, H))
    gx_max = max(0, min(gx_max, W))
    
    # 3. Final normalization (Global Pixels -> 0-1000 Global)
    if W == 0 or H == 0:
        return {"ymin": 0, "xmin": 0, "ymax": 0, "xmax": 0}
    
    return {
        "ymin": int(gy_min / H * 1000),
        "xmin": int(gx_min / W * 1000),
        "ymax": int(gy_max / H * 1000),
        "xmax": int(gx_max / W * 1000)
    }

def get_image_size(image_path: str) -> Tuple[int, int]:
    """Returns (width, height) of the image."""
    img_array = load_image_safe(image_path)
    if img_array is not None:
        # OpenCV shape is (height, width, channels)
        h, w = img_array.shape[:2]
        return (w, h)
    
    # Fallback to PIL if safe load fails (though rarely reached)
    with Image.open(image_path) as img:
        return img.size

def slice_multiple_images(
    image_paths: List[str],
    patch_size: int,
    overlap: int,
    max_dimension: int,
    blur_threshold: float,
    edge_threshold: int
) -> List[Dict[str, Any]]:
    """모든 이미지에 대해 패치를 생성하고 소스 경로를 태깅합니다."""
    all_patches = []
    for img_path in image_paths:
        logger.info(f"Image Slicing: Processing {img_path}...")
        patch_generator = slice_image(
            img_path, 
            patch_size=patch_size, 
            overlap=overlap,
            max_dimension=max_dimension,
            blur_threshold=blur_threshold,
            edge_threshold=edge_threshold
        )
        for patch in patch_generator:
            patch['source_image_path'] = img_path
            all_patches.append(patch)
    return all_patches

def map_hotspots_to_global(
    batch_results: List[Any],
    image_sizes: Dict[str, Tuple[int, int]]
) -> List[Dict[str, Any]]:
    """탐지된 패치 기반 Hotspot 좌표를 전역 이미지 좌표로 매핑합니다."""
    raw_hotspots = []
    
    for patches_chunk, patch_hotspots in batch_results:
        if not patch_hotspots:
            continue
            
        for h in patch_hotspots:
            # Pydantic 모델인 경우 dict로 변환 (HotspotDetectionResult의 개별 항목)
            if hasattr(h, "model_dump"):
                h_dict = h.model_dump(mode='json')
            else:
                h_dict = h.copy()
            
            img_idx = h_dict.get('image_index', 1) - 1
            if img_idx < 0: img_idx = 0
            elif img_idx >= len(patches_chunk): img_idx = len(patches_chunk) - 1
                
            target_patch = patches_chunk[img_idx]
            src_path = target_patch['source_image_path']
            original_size = image_sizes[src_path]
            
            # Use fixed absolute offsets in original image pixels
            original_offset = target_patch['original_offset']
            original_patch_size = target_patch['original_size']
            
            global_box = map_box_to_global(
                h_dict['box_2d'], 
                original_offset, 
                original_patch_size, 
                original_size
            )
            
            h_dict['box_2d'] = global_box
            h_dict['source_image_path'] = src_path
            
            raw_hotspots.append(h_dict)
            
    return raw_hotspots

def perform_batch_nms(
    raw_hotspots: List[Dict[str, Any]],
    iou_threshold: float
) -> List[Dict[str, Any]]:
    """이미지별로 그룹화하여 NMS 중복 제거를 수행합니다."""
    from collections import defaultdict
    from src.utils.nms import perform_nms
    
    final_raw_hotspots = []
    global_hotspot_id = 1
    
    grouped_raw = defaultdict(list)
    for h in raw_hotspots:
        grouped_raw[h['source_image_path']].append(h)
        
    for src_path, path_hotspots in grouped_raw.items():
        nms_hotspots = perform_nms(path_hotspots, iou_threshold=iou_threshold)
        for h in nms_hotspots:
            h['id'] = global_hotspot_id
            h.pop('_origin_patch', None)
            final_raw_hotspots.append(h)
            global_hotspot_id += 1
            
    return final_raw_hotspots
