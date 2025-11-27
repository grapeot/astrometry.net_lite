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


# Legacy functions (deprecated, kept for backward compatibility)
def plot_bright_stars(draw: ImageDraw.ImageDraw, wcs: WCS, width: int, height: int, radius: float, cat_dir: Path, base_size: int = 3, outline_width: int = 1) -> None:
    """Plot bright stars from brightstars.fits catalog (legacy, deprecated)."""
    logger.warning("plot_bright_stars is deprecated and may not be used in current implementation")
    # Implementation kept for backward compatibility
    bright_fn = cat_dir / "brightstars.fits"
    if not bright_fn.exists():
        logger.debug("Bright stars catalog not found: %s", bright_fn)
        return
    
    try:
        from astropy.io import fits
        import numpy as np
        
        with fits.open(bright_fn) as hdul:
            data = hdul[1].data
            if "RA" in data.dtype.names:
                ra = data["RA"]
            elif "ra" in data.dtype.names:
                ra = data["ra"]
            else:
                logger.warning("RA column not found in bright stars catalog")
                return
            
            if "DEC" in data.dtype.names:
                dec = data["DEC"]
            elif "dec" in data.dtype.names:
                dec = data["dec"]
            else:
                logger.warning("DEC column not found in bright stars catalog")
                return
            
            mag_cols = ["MAG", "mag", "VMAG", "vmag"]
            mag = None
            for col in mag_cols:
                if col in data.dtype.names:
                    mag = data[col]
                    break
            if mag is None:
                mag = np.ones(len(ra)) * 5.0
            
            center = wcs.pixel_to_world(width / 2, height / 2)
            center_ra = center.ra.deg
            center_dec = center.dec.deg
            
            for star_ra, star_dec, star_mag in zip(ra, dec, mag):
                try:
                    ra_diff = abs(star_ra - center_ra)
                    if ra_diff > 180:
                        ra_diff = 360 - ra_diff
                    dec_diff = abs(star_dec - center_dec)
                    distance_sq = ra_diff**2 + dec_diff**2
                    if distance_sq > (radius * 2)**2:
                        continue
                    
                    pixel = wcs.world_to_pixel_values(star_ra, star_dec)
                    x, y = float(pixel[0]), float(pixel[1])
                    
                    if 0 <= x < width and 0 <= y < height:
                        mag_factor = max(0.5, (8 - star_mag) / 4.0)
                        size = max(base_size, int(base_size * mag_factor * 1.5))
                        outline_w = max(1, outline_width)
                        draw.ellipse([x - size, y - size, x + size, y + size], 
                                    fill=(255, 255, 0), outline=(255, 0, 0), width=outline_w)
                        cross_size = int(size * 1.5)
                        draw.line([x - cross_size, y, x + cross_size, y], fill=(255, 0, 0), width=outline_w)
                        draw.line([x, y - cross_size, x, y + cross_size], fill=(255, 0, 0), width=outline_w)
                except Exception:  # noqa: BLE001
                    continue
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error reading bright stars catalog: %s", exc)


def plot_ngc_objects(draw: ImageDraw.ImageDraw, wcs: WCS, width: int, height: int, radius: float, cat_dir: Path, base_size: int = 4, outline_width: int = 1) -> None:
    """Plot NGC/IC objects from openngc catalogs (legacy, deprecated)."""
    logger.warning("plot_ngc_objects is deprecated and may not be used in current implementation")
    # Implementation kept for backward compatibility but simplified
    pass


def plot_abell_clusters(draw: ImageDraw.ImageDraw, wcs: WCS, width: int, height: int, radius: float, cat_dir: Path, base_size: int = 2, outline_width: int = 1) -> None:
    """Plot Abell galaxy clusters (legacy, deprecated)."""
    logger.warning("plot_abell_clusters is deprecated and may not be used in current implementation")
    # Implementation kept for backward compatibility but simplified
    pass

