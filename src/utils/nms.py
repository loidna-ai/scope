"""
Non-Maximum Suppression (NMS) Utilities
"""
from typing import List, Dict, Any

def calculate_iou(box1: Dict[str, int], box2: Dict[str, int]) -> float:
    """
    Calculates Intersection over Union (IoU) between two bounding boxes.
    Boxes are in {ymin, xmin, ymax, xmax} format (0-1000 normalized).
    """
    # Determine intersection rectangle
    x_left = max(box1["xmin"], box2["xmin"])
    y_top = max(box1["ymin"], box2["ymin"])
    x_right = min(box1["xmax"], box2["xmax"])
    y_bottom = min(box1["ymax"], box2["ymax"])
    
    if x_right < x_left or y_bottom < y_top:
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

def non_max_suppression(
    hotspots: List[Dict[str, Any]], 
    iou_threshold: float = 0.5
) -> List[Dict[str, Any]]:
    """
    Performs NMS on a list of hotspots.
    Prioritizes hotspots with higher severity_score.
    When suppressing overlapping hotspots, merges visual_evidence
    from the suppressed hotspot into the kept one.
    
    Args:
        hotspots: List of hotspot dictionaries. Must have 'box_2d' and 'severity_score'.
        iou_threshold: Overlap threshold to suppress boxes (0.0 - 1.0).
        
    Returns:
        List of selected hotspots after suppression.
    """
    if not hotspots:
        return []
        
    # Sort by severity_score descending
    sorted_hotspots = sorted(
        hotspots, 
        key=lambda h: h.get("severity_score", 0), 
        reverse=True
    )
    
    keep = []
    
    while sorted_hotspots:
        # Pick highest scoring hotspot
        current = sorted_hotspots.pop(0)
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
                other_evidence = other.get("visual_evidence", "")
                current_evidence = current.get("visual_evidence", "")
                if other_evidence and other_evidence not in current_evidence:
                    current["visual_evidence"] = f"{current_evidence} | {other_evidence}"
                
        sorted_hotspots = remaining
        
    return keep
