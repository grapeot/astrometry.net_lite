"""Rendering functions for celestial objects."""

from __future__ import annotations

import logging
import math
from pathlib import Path

from astropy.wcs import WCS
from PIL import ImageDraw, ImageFont

from services.annotator.catalog import CelestialObject, get_object_color, get_object_type

logger = logging.getLogger(__name__)


def draw_object(draw: ImageDraw.ImageDraw, x: float, y: float, obj: CelestialObject, 
                obj_type: str, width: int, height: int, wcs: WCS, font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
                label_x: float | None = None, label_y: float | None = None) -> None:
    """Draw a celestial object on the image.
    
    Args:
        draw: PIL ImageDraw context
        x, y: Pixel coordinates
        obj: Celestial object to draw
        obj_type: Type of object
        width, height: Image dimensions
        wcs: WCS object for coordinate conversion
        font: Font for text labels
        label_x, label_y: Optional label position (if None, calculated automatically)
    """
    # Calculate dynamic sizing
    min_dimension = min(width, height)
    scale_factor = min_dimension / 1000.0
    # Thickness: 6x the original (was 1 * scale_factor, now 6 * scale_factor)
    base_thickness = max(1, int(4 * scale_factor))
    # Font size: 144x the original
    font_size = max(10, int(48 * scale_factor))
    
    color = get_object_color(obj_type)
    
    # Calculate pixel radius
    from astropy.wcs.utils import proj_plane_pixel_scales
    scales = proj_plane_pixel_scales(wcs)
    avg_scale = (abs(scales[0]) + abs(scales[1])) / 2.0
    
    # Calculate shadow offset for drop shadow effect
    shadow_offset_x = max(2, int(4 * scale_factor))
    shadow_offset_y = max(2, int(4 * scale_factor))
    
    if obj.ang_diameter is not None and obj.ang_diameter > 0:
        # Has radius: draw circle with solid line
        # Convert arcmin to degrees, then to pixels
        radius_deg = obj.ang_diameter / 60.0 / 2.0
        radius_pixels = radius_deg / avg_scale
        
        # Draw drop shadow first (behind the main circle)
        shadow_bbox = [x - radius_pixels + shadow_offset_x, y - radius_pixels + shadow_offset_y,
                      x + radius_pixels + shadow_offset_x, y + radius_pixels + shadow_offset_y]
        shadow_color = (30, 30, 30)  # Dark shadow
        draw.ellipse(shadow_bbox, outline=shadow_color, fill=None, width=base_thickness)
        
        # Draw main circle with solid outline (no fill to avoid covering the image)
        bbox = [x - radius_pixels, y - radius_pixels, x + radius_pixels, y + radius_pixels]
        # Explicitly set fill=None to ensure no fill
        draw.ellipse(bbox, outline=color, fill=None, width=base_thickness)
    else:
        # No radius: draw with dashed line
        # Use a default radius (e.g., 0.1 degrees)
        default_radius_deg = 0.1
        radius_pixels = default_radius_deg / avg_scale
        
        # Draw drop shadow first (behind the dashed circle)
        shadow_color = (30, 30, 30)  # Dark shadow
        num_segments = 24
        dash_length = 360 / num_segments
        # Draw shadow as dashed circle
        for i in range(0, num_segments, 2):
            start_angle = i * dash_length
            end_angle = (i + 1) * dash_length
            num_points = 8
            points = []
            for j in range(num_points):
                angle = math.radians(start_angle + (end_angle - start_angle) * j / (num_points - 1))
                px = x + radius_pixels * math.cos(angle) + shadow_offset_x
                py = y + radius_pixels * math.sin(angle) + shadow_offset_y
                points.append((px, py))
            for k in range(len(points) - 1):
                draw.line([points[k], points[k+1]], fill=shadow_color, width=max(1, base_thickness))
        
        # Draw dashed circle on top
        bbox = [x - radius_pixels, y - radius_pixels, x + radius_pixels, y + radius_pixels]
        for i in range(0, num_segments, 2):
            start_angle = i * dash_length
            end_angle = (i + 1) * dash_length
            num_points = 8
            points = []
            for j in range(num_points):
                angle = math.radians(start_angle + (end_angle - start_angle) * j / (num_points - 1))
                px = x + radius_pixels * math.cos(angle)
                py = y + radius_pixels * math.sin(angle)
                points.append((px, py))
            for k in range(len(points) - 1):
                draw.line([points[k], points[k+1]], fill=color, width=max(1, base_thickness))
    
    # Draw label (use provided position if available, otherwise calculate default)
    try:
        if label_x is None or label_y is None:
            # Position label above the object (default)
            label_offset = radius_pixels + font_size + 5
            label_y = y - label_offset
            # Ensure label is within bounds
            if label_y < 0:
                label_y = y + label_offset
            label_x = x
        
        # Draw text with shadow for readability (larger shadow offset for bigger font)
        text_shadow_offset = max(2, int(3 * scale_factor))
        draw.text((label_x + text_shadow_offset, label_y + text_shadow_offset), obj.name, 
                 fill=(0, 0, 0), font=font)  # Shadow
        draw.text((label_x, label_y), obj.name, fill=color, font=font)
    except Exception:  # noqa: BLE001
        pass  # Skip label if font rendering fails

