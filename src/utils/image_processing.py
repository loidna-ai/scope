"""
Image Processing Utilities for Overlap Grid Strategy
"""
import io
import math
from typing import List, Tuple, Dict, Any, Optional
from PIL import Image
import os

def slice_image(
    image_path: str, 
    patch_size: int = 1024, 
    overlap: int = 200,
    min_patch_size: int = 512
) -> List[Dict[str, Any]]:
    """
    Slices an image into overlapping patches.
    
    Args:
        image_path: Path to the source image.
        patch_size: Desired width/height of each patch.
        overlap: Number of pixels to overlap between adjacent patches.
        min_patch_size: Minimum size to consider a valid patch (for edges).
        
    Returns:
        List of dictionaries, each containing:
            - 'image_bytes': Bytes of the patch (JPEG format)
            - 'offset': (x, y) tuple of the top-left corner in the original image
            - 'size': (width, height) tuple of the patch
            - 'index': (row_idx, col_idx) tuple
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")
        
    try:
        img = Image.open(image_path)
        # Convert to RGB if needed (e.g., for RGBA/P images)
        if img.mode != 'RGB':
            img = img.convert('RGB')
            
        w, h = img.size
        patches = []
        
        # Calculate stride (step size)
        stride = patch_size - overlap
        if stride <= 0:
            raise ValueError(f"Overlap ({overlap}) must be smaller than patch_size ({patch_size})")
            
        # Better robust generation:
        def get_starts(total_length, window, stride):
            starts = []
            curr = 0
            while curr + window < total_length:
                starts.append(curr)
                curr += stride
            # Add last patch forced to end at total_length
            starts.append(max(0, total_length - window))
            return sorted(list(set(starts))) # remove duplicates if any

        x_coords = get_starts(w, patch_size, stride)
        y_coords = get_starts(h, patch_size, stride)
        
        for r_idx, y in enumerate(y_coords):
            for c_idx, x in enumerate(x_coords):
                # Crop
                x_end = min(x + patch_size, w)
                y_end = min(y + patch_size, h)
                
                box = (x, y, x_end, y_end)
                patch_img = img.crop(box)
                
                # Verify size - skip if too small (e.g. slivers)
                pw, ph = patch_img.size
                if pw < min_patch_size or ph < min_patch_size:
                    # Only skip if image itself is larger than min_patch_size
                    if w > min_patch_size and h > min_patch_size:
                        continue
                
                # Convert to bytes
                buf = io.BytesIO()
                patch_img.save(buf, format="JPEG", quality=95)
                patch_bytes = buf.getvalue()
                
                patches.append({
                    "image_bytes": patch_bytes,
                    "offset": (x, y),
                    "size": (pw, ph),
                    "index": (r_idx, c_idx)
                })
                
        return patches
        
    except Exception as e:
        print(f"Error slicing image: {e}")
        return []

def map_box_to_global(
    box_2d: Dict[str, int], 
    patch_offset: Tuple[int, int], 
    patch_size: Tuple[int, int],
    original_size: Tuple[int, int]
) -> Dict[str, int]:
    """
    Maps bounding box from Patch Normalized Coordinates (0-1000) to Global Normalized Coordinates (0-1000).
    
    Args:
        box_2d: Dict with ymin, xmin, ymax, xmax (0-1000 relative to patch)
        patch_offset: (x, y) of the top-left corner of the patch in global pixels
        patch_size: (width, height) of the patch in pixels
        original_size: (width, height) of the original global image in pixels
        
    Returns:
        Dict with ymin, xmin, ymax, xmax (0-1000 relative to global image)
    """
    # 1. De-normalize from Patch (0-1000 -> Pixels in Patch)
    py_min = box_2d.get("ymin", 0) / 1000 * patch_size[1]
    px_min = box_2d.get("xmin", 0) / 1000 * patch_size[0]
    py_max = box_2d.get("ymax", 0) / 1000 * patch_size[1]
    px_max = box_2d.get("xmax", 0) / 1000 * patch_size[0]
    
    # 2. Add Offset (Pixels in Patch -> Pixels in Global)
    gx_min = px_min + patch_offset[0]
    gy_min = py_min + patch_offset[1]
    gx_max = px_max + patch_offset[0]
    gy_max = py_max + patch_offset[1]
    
    # 3. Clip to bounds
    W, H = original_size
    gx_min = max(0, min(gx_min, W))
    gy_min = max(0, min(gy_min, H))
    gx_max = max(0, min(gx_max, W))
    gy_max = max(0, min(gy_max, H))
    
    # 4. Re-normalize to Global (Pixels in Global -> 0-1000 Global)
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
    with Image.open(image_path) as img:
        return img.size
