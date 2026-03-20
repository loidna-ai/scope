"""
Non-Maximum Suppression (NMS) Utilities
"""
import logging
from typing import List, Dict, Any, Optional, TypedDict, Union, Tuple, Sequence

logger = logging.getLogger(__name__)

RequiredBox = TypedDict("RequiredBox", {
    "xmin": Union[int, float],
    "ymin": Union[int, float],
    "xmax": Union[int, float],
    "ymax": Union[int, float]
})

Hotspot = Dict[str, Any]

def _is_valid_box(box: Optional[Dict[str, Any]]) -> bool:
    """Check if box_2d exists and has all required keys with valid structure."""
    if not box or not isinstance(box, dict):
        return False
    required_keys = ("xmin", "ymin", "xmax", "ymax")
    for key in required_keys:
        if key not in box:
            return False
    return box["xmin"] < box["xmax"] and box["ymin"] < box["ymax"]


def calculate_iou(box1: RequiredBox, box2: RequiredBox) -> float:
    """
    Calculates Intersection over Union (IoU) between two bounding boxes.
    Boxes are in {ymin, xmin, ymax, xmax} format (0-1000 normalized).
    Returns 0.0 if either box is invalid or missing.
    """
    if not _is_valid_box(box1) or not _is_valid_box(box2):
        return 0.0

    # Determine intersection rectangle
    x_left = max(box1["xmin"], box2["xmin"])
    y_top = max(box1["ymin"], box2["ymin"])
    x_right = min(box1["xmax"], box2["xmax"])
    y_bottom = min(box1["ymax"], box2["ymax"])
    
    if x_right <= x_left or y_bottom <= y_top:
        return 0.0
        
    intersection_area = (x_right - x_left) * (y_bottom - y_top)
    
    # Calculate box areas
    area1 = (box1["xmax"] - box1["xmin"]) * (box1["ymax"] - box1["ymin"])
    area2 = (box2["xmax"] - box2["xmin"]) * (box2["ymax"] - box2["ymin"])
    
    # Union area
    union_area = area1 + area2 - intersection_area
    
    if union_area <= 0:
        return 0.0
        
    return intersection_area / union_area

def perform_nms(
    hotspots: Sequence[Hotspot], 
    iou_threshold: float = 0.5
) -> List[Hotspot]:
    """
    Performs NMS on a single set of hotspots (intended for a single image or coordinate space).
    Prioritizes hotspots with higher severity_score.
    Immutability: Returns a new list containing copies of selected hotspots.
    
    Args:
        hotspots: Sequence of hotspot dictionaries. Must have 'box_2d' and 'severity_score'.
        iou_threshold: Overlap threshold to suppress boxes (0.0 - 1.0).
        
    Returns:
        List of selected hotspots after suppression.
    """
    if not hotspots:
        return []

    # Filter out hotspots with missing or invalid box_2d
    valid_hotspots = []
    for h in hotspots:
        box = h.get("box_2d")
        if not _is_valid_box(box):
            logger.warning(
                "NMS: Skipping hotspot with missing or invalid box_2d (id=%s)",
                h.get("id", "?"),
            )
            continue
        valid_hotspots.append({**h}) # Deep copy not needed if we only mutate simple fields, but shallow copy at least

    # Sort by severity_score descending
    sorted_hotspots = sorted(
        valid_hotspots,
        key=lambda h: h.get("severity_score", 0),
        reverse=True
    )
    
    keep = []
    
    while sorted_hotspots:
        # Pick highest scoring hotspot
        current = sorted_hotspots.pop(0)
        # Ensure we don't mutate original: we already shallow copied above
        keep.append(current)
        
        # Compare with remaining
        remaining = []
        for other in sorted_hotspots:
            # Check overlap
            iou = calculate_iou(current.get("box_2d"), other.get("box_2d"))
            
            if iou < iou_threshold:
                # Keep it if overlap is small
                remaining.append(other)
            else:
                # Suppress: merge visual_evidence from lower-score hotspot
                # Immutable approach: Create a new version of current if we merge evidence
                other_evidence = other.get("visual_evidence", "")
                current_evidence = current.get("visual_evidence", "")
                if other_evidence and other_evidence not in current_evidence:
                    # Update 'current' in 'keep' (since it's a reference to the same dictionary)
                    # To be 100% immutable relative to input, we already copied 'h' into 'valid_hotspots'
                    current["visual_evidence"] = f"{current_evidence} | {other_evidence}"
                
        sorted_hotspots = remaining
        
    return keep

def batch_nms(
    batch_hotspots: Sequence[Hotspot],
    iou_threshold: float = 0.5,
    group_key: str = "image_id"
) -> List[Hotspot]:
    """
    Groups hotspots by group_key (e.g., 'image_id') and performs NMS for each group.
    
    Args:
        batch_hotspots: List of hotspots from one or more images.
        iou_threshold: IoU threshold for NMS.
        group_key: Key in the hotspot dict to group by (e.g., image_id).
        
    Returns:
        Flat list of consolidated hotspots after batch-wise NMS.
    """
    if not batch_hotspots:
        return []

    # Grouping
    grouped_hotspots: Dict[Union[str, int, None], List[Hotspot]] = {}
    for h in batch_hotspots:
        val = h.get(group_key)
        if val not in grouped_hotspots:
            grouped_hotspots[val] = []
        grouped_hotspots[val].append(h)

    # Perform NMS per group
    results = []
    for group_val, hotspots in grouped_hotspots.items():
        results.extend(perform_nms(hotspots, iou_threshold))
        
    return results
