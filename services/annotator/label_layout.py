"""Label layout and position optimization."""

from __future__ import annotations

import logging
from PIL import ImageFont

logger = logging.getLogger(__name__)


def get_text_bbox(text: str, x: float, y: float, font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> tuple[float, float, float, float]:
    """Get bounding box for text.
    
    Returns:
        (left, top, right, bottom) bounding box
    """
    try:
        bbox = font.getbbox(text)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        # Account for text anchor (typically top-left)
        left = x
        top = y
        right = x + text_width
        bottom = y + text_height
        return (left, top, right, bottom)
    except Exception:  # noqa: BLE001
        # Fallback: estimate based on text length
        text_width = len(text) * font.size if hasattr(font, 'size') else len(text) * 10
        text_height = font.size if hasattr(font, 'size') else 12
        return (x, y, x + text_width, y + text_height)


def bboxes_overlap(bbox1: tuple[float, float, float, float], bbox2: tuple[float, float, float, float], padding: float = 5.0) -> bool:
    """Check if two bounding boxes overlap.
    
    Args:
        bbox1, bbox2: (left, top, right, bottom) bounding boxes
        padding: Additional padding around boxes
    
    Returns:
        True if boxes overlap
    """
    left1, top1, right1, bottom1 = bbox1
    left2, top2, right2, bottom2 = bbox2
    
    # Add padding
    left1 -= padding
    top1 -= padding
    right1 += padding
    bottom1 += padding
    
    left2 -= padding
    top2 -= padding
    right2 += padding
    bottom2 += padding
    
    # Check overlap
    return not (right1 < left2 or left1 > right2 or bottom1 < top2 or top1 > bottom2)


def adjust_label_position(label_x: float, label_y: float, text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
                          existing_labels: list[tuple[float, float, float, float]], 
                          object_x: float, object_y: float, radius_pixels: float,
                          width: int, height: int, font_size: int) -> tuple[float, float]:
    """Adjust label position to avoid overlap with existing labels (greedy algorithm).
    
    Args:
        label_x, label_y: Initial label position
        text: Label text
        font: Font for text
        existing_labels: List of existing label bounding boxes
        object_x, object_y: Object position
        radius_pixels: Object radius in pixels
        width, height: Image dimensions
        font_size: Font size in pixels
    
    Returns:
        (adjusted_x, adjusted_y) label position
    """
    # Try different positions: above, below, left, right, and diagonals
    offsets = [
        (0, -radius_pixels - font_size - 10),  # Above (original)
        (0, radius_pixels + font_size + 10),   # Below
        (-radius_pixels - len(text) * font_size / 2 - 10, 0),  # Left
        (radius_pixels + len(text) * font_size / 2 + 10, 0),  # Right
        (-radius_pixels - len(text) * font_size / 2 - 10, -radius_pixels - font_size - 10),  # Top-left
        (radius_pixels + len(text) * font_size / 2 + 10, -radius_pixels - font_size - 10),  # Top-right
        (-radius_pixels - len(text) * font_size / 2 - 10, radius_pixels + font_size + 10),  # Bottom-left
        (radius_pixels + len(text) * font_size / 2 + 10, radius_pixels + font_size + 10),  # Bottom-right
    ]
    
    # Try each position
    for offset_x, offset_y in offsets:
        test_x = object_x + offset_x
        test_y = object_y + offset_y
        
        # Calculate text bounding box for this position
        test_bbox = get_text_bbox(text, test_x, test_y, font)
        left, top, right, bottom = test_bbox
        
        # Ensure entire bounding box is within bounds (with small margin)
        margin = 5
        if left < margin or right > width - margin or top < margin or bottom > height - margin:
            continue
        
        # Check overlap with existing labels
        overlaps = False
        for existing_bbox in existing_labels:
            if bboxes_overlap(test_bbox, existing_bbox):
                overlaps = True
                break
        
        if not overlaps:
            return (test_x, test_y)
    
    # If all positions overlap or are out of bounds, try to adjust original position to fit
    # Clamp the label position to ensure it's within bounds
    original_bbox = get_text_bbox(text, label_x, label_y, font)
    orig_left, orig_top, orig_right, orig_bottom = original_bbox
    
    # Adjust if out of bounds
    adjusted_x = label_x
    adjusted_y = label_y
    
    if orig_left < 0:
        adjusted_x = label_x - orig_left + 5  # Shift right
    elif orig_right > width:
        adjusted_x = label_x - (orig_right - width) - 5  # Shift left
    
    if orig_top < 0:
        adjusted_y = label_y - orig_top + 5  # Shift down
    elif orig_bottom > height:
        adjusted_y = label_y - (orig_bottom - height) - 5  # Shift up
    
    # Final check: ensure adjusted position's bbox is within bounds
    final_bbox = get_text_bbox(text, adjusted_x, adjusted_y, font)
    final_left, final_top, final_right, final_bottom = final_bbox
    
    if final_left >= 0 and final_right <= width and final_top >= 0 and final_bottom <= height:
        return (adjusted_x, adjusted_y)
    
    # Last resort: return original position (may be partially out of bounds)
    return (label_x, label_y)

