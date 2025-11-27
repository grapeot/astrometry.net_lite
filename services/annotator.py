from __future__ import annotations

import asyncio
import csv
import logging
import math
import subprocess
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from PIL import Image, ImageDraw, ImageFont

from core.config import settings
from services.storage import prepare_job_dir

logger = logging.getLogger(__name__)


class CelestialObject(NamedTuple):
    """Represents a celestial object from the catalog."""
    name: str
    ra: float
    dec: float
    ang_diameter: float | None  # arcmin, None if not available


def _convert_to_ppm(source_path: Path, target_path: Path) -> None:
    """Convert image to PPM format (PNM variant) for plotann.py."""
    img = Image.open(source_path)
    # Convert to RGB if needed
    if img.mode != "RGB":
        img = img.convert("RGB")
    # Save as PPM
    img.save(target_path, "PPM")


def _build_plotann_args(job_dir: Path, wcs_path: Path, pnm_path: Path, output_path: Path, radius: float, scale: float = 1.0) -> list[str]:
    """Build command line arguments for plotann.py."""
    args = [
        "/opt/homebrew/bin/plotann.py",
        "--no-grid",
        "--toy",
        "-10",
        "--scale",
        str(scale),
    ]
    
    cat_dir = settings.catalogs_dir
    abell_fn = cat_dir / "abell-all.fits"
    ngc_fn = cat_dir / "openngc-ngc.fits"
    ngc_names_fn = cat_dir / "openngc-names.fits"
    ic_fn = cat_dir / "openngc-ic.fits"
    bright_fn = cat_dir / "brightstars.fits"
    
    # Add catalogs based on field radius (matching net/views/image.py logic)
    if radius < 1.0:
        if abell_fn.exists():
            args.extend(["--abellcat", str(abell_fn)])
        # Note: HD catalog would go here if available
    
    if radius < 0.25:
        # Tycho-2 would go here if available
        pass
    
    if radius < 10.0:
        if ngc_fn.exists() and ngc_names_fn.exists() and ic_fn.exists():
            args.extend(["--ngccat", str(ngc_fn)])
            args.extend(["--ngcname", str(ngc_names_fn)])
            args.extend(["--iccat", str(ic_fn)])
    else:
        args.append("--no-ngc")
    
    if radius > 30.0:
        args.append("--no-bright")
    elif bright_fn.exists():
        args.extend(["--brightcat", str(bright_fn)])
    
    # Add input/output files: wcs.fits input.pnm output.jpg
    args.extend([str(wcs_path), str(pnm_path), str(output_path)])
    
    return args


def _get_catalog_priority(name: str) -> int:
    """Get priority for catalog object (lower number = higher priority).
    
    Priority order:
    1. M (Messier) - highest
    2. NGC
    3. IC
    4. Barnard (famous dark nebulae like B33 - Horsehead Nebula)
    5. LBN/LDN
    6. VdB/Sharpless/R-BEL/ABELL - lowest
    """
    name_upper = name.upper().strip()
    if name_upper.startswith("M "):
        return 1
    elif name_upper.startswith("NGC "):
        return 2
    elif name_upper.startswith("IC "):
        return 3
    elif name_upper.startswith("BARNARD "):
        return 4  # Barnard objects (like B33 - Horsehead Nebula) are famous
    elif name_upper.startswith("LBN ") or name_upper.startswith("LDN "):
        return 5
    elif any(name_upper.startswith(prefix) for prefix in ["VDB ", "SHARPLESS ", "R-BEL ", "ABELL "]):
        return 6
    else:
        return 7  # Unknown types get lowest priority


def _are_objects_duplicate(obj1: CelestialObject, obj2: CelestialObject, duplicate_threshold_deg: float = 0.1) -> bool:
    """Check if two objects are duplicates based on position and radius overlap.
    
    Args:
        obj1, obj2: Celestial objects to compare
        duplicate_threshold_deg: Maximum angular separation (degrees) to consider duplicate
    
    Returns:
        True if objects are considered duplicates
    """
    # Calculate angular separation
    ra_diff = abs(obj1.ra - obj2.ra)
    if ra_diff > 180:
        ra_diff = 360 - ra_diff
    
    dec_diff = abs(obj1.dec - obj2.dec)
    distance_deg = np.sqrt(ra_diff**2 + dec_diff**2)
    
    # If positions are very close, consider duplicate
    if distance_deg < duplicate_threshold_deg:
        return True
    
    # Check radius overlap (if both have radii)
    # Only consider overlap if the distance is significantly less than the sum of radii
    # This avoids false positives where large objects just barely touch
    if obj1.ang_diameter is not None and obj2.ang_diameter is not None:
        # Convert arcmin to degrees
        radius1_deg = obj1.ang_diameter / 60.0 / 2.0
        radius2_deg = obj2.ang_diameter / 60.0 / 2.0
        
        # If circles overlap significantly, consider duplicate
        # Require that the overlap is substantial - the smaller object must be mostly within the larger one
        # This prevents large objects from being considered duplicates just because they're in the same region
        min_radius = min(radius1_deg, radius2_deg)
        max_radius = max(radius1_deg, radius2_deg)
        
        # Only consider duplicate if the smaller object is mostly contained within the larger one
        # This means: distance + min_radius < max_radius (smaller object fits inside larger)
        # And distance must be small relative to the smaller radius (< 3x smaller radius)
        if (distance_deg + min_radius) < max_radius and distance_deg < min_radius * 3:
            return True
    
    return False


def _deduplicate_objects(objects: list[CelestialObject], duplicate_threshold_deg: float = 0.1) -> list[CelestialObject]:
    """Remove duplicate objects, keeping the one with higher priority.
    
    Priority rules:
    1. Objects with radius > objects without radius
    2. Higher catalog priority (M > NGC > IC > LBN/LDN > VdB/Sharpless/R-BEL)
    """
    if not objects:
        return []
    
    # Sort by priority (lower number = higher priority)
    # First by has_radius (False comes before True when sorted ascending, so we negate)
    # Then by catalog priority
    def sort_key(obj: CelestialObject) -> tuple[int, int]:
        has_radius = 0 if obj.ang_diameter is not None else 1
        priority = _get_catalog_priority(obj.name)
        return (has_radius, priority)
    
    sorted_objects = sorted(objects, key=sort_key)
    
    # Remove duplicates, keeping first occurrence (highest priority)
    deduplicated = []
    for obj in sorted_objects:
        is_duplicate = False
        for kept_obj in deduplicated:
            if _are_objects_duplicate(obj, kept_obj, duplicate_threshold_deg):
                is_duplicate = True
                logger.debug("Removing duplicate: %s (kept: %s)", obj.name, kept_obj.name)
                break
        if not is_duplicate:
            deduplicated.append(obj)
    
    return deduplicated


def _load_catalog_csv(catalog_path: Path) -> list[CelestialObject]:
    """Load celestial objects from catalogs.csv."""
    objects = []
    if not catalog_path.exists():
        logger.warning("Catalog CSV not found: %s", catalog_path)
        return objects
    
    try:
        with open(catalog_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    name = row["name"].strip()
                    ra = float(row["ra"])
                    dec = float(row["dec"])
                    ang_diameter_str = row.get("ang_diameter", "").strip()
                    ang_diameter = None
                    if ang_diameter_str:
                        # Handle formats like "66X60" (extract first number or average)
                        if 'X' in ang_diameter_str or 'x' in ang_diameter_str:
                            # Extract numbers from format like "66X60"
                            import re
                            numbers = re.findall(r'\d+\.?\d*', ang_diameter_str)
                            if numbers:
                                # Use average of the two dimensions
                                ang_diameter = sum(float(n) for n in numbers) / len(numbers)
                        else:
                            # Try to parse as regular float
                            ang_diameter = float(ang_diameter_str)
                    objects.append(CelestialObject(name=name, ra=ra, dec=dec, ang_diameter=ang_diameter))
                except (ValueError, KeyError) as e:
                    logger.debug("Skipping invalid catalog row: %s, error: %s", row, e)
                    continue
        
        logger.info("Loaded %d objects from catalog CSV", len(objects))
        return objects
    except Exception as exc:  # noqa: BLE001
        logger.error("Error loading catalog CSV: %s", exc, exc_info=True)
        return []


def _get_field_corners(wcs: WCS, width: int, height: int) -> tuple[float, float, float, float]:
    """Get RA/Dec bounds of the image field.
    
    Returns:
        (min_ra, max_ra, min_dec, max_dec) in degrees
    """
    # Get corners in pixel coordinates
    corners_pixel = [
        (0, 0),           # Top-left
        (width, 0),       # Top-right
        (width, height),  # Bottom-right
        (0, height),      # Bottom-left
    ]
    
    # Convert to world coordinates
    corners_world = []
    for x, y in corners_pixel:
        try:
            world = wcs.pixel_to_world(x, y)
            corners_world.append((world.ra.deg, world.dec.deg))
        except Exception:  # noqa: BLE001
            continue
    
    if not corners_world:
        # Fallback: use center and estimate
        center = wcs.pixel_to_world(width / 2, height / 2)
        center_ra = center.ra.deg
        center_dec = center.dec.deg
        # Rough estimate (this is a fallback, should not normally happen)
        return (center_ra - 1.0, center_ra + 1.0, center_dec - 1.0, center_dec + 1.0)
    
    ras = [ra for ra, _ in corners_world]
    decs = [dec for _, dec in corners_world]
    
    # Handle RA wrap-around
    min_ra = min(ras)
    max_ra = max(ras)
    if max_ra - min_ra > 180:
        # Field crosses RA=0/360 boundary
        # Find the gap and adjust
        ras_sorted = sorted(ras)
        gaps = [(ras_sorted[i+1] - ras_sorted[i]) % 360 for i in range(len(ras_sorted)-1)]
        max_gap_idx = gaps.index(max(gaps))
        min_ra = ras_sorted[(max_gap_idx + 1) % len(ras_sorted)]
        max_ra = ras_sorted[max_gap_idx]
    
    min_dec = min(decs)
    max_dec = max(decs)
    
    return (min_ra, max_ra, min_dec, max_dec)


def _filter_objects_in_field(objects: list[CelestialObject], min_ra: float, max_ra: float, min_dec: float, max_dec: float) -> list[CelestialObject]:
    """Filter objects that are within the field bounds."""
    filtered = []
    
    for obj in objects:
        # Check if object is within dec bounds
        if not (min_dec <= obj.dec <= max_dec):
            continue
        
        # Check RA (handle wrap-around)
        if min_ra <= max_ra:
            # Normal case: no wrap-around
            if min_ra <= obj.ra <= max_ra:
                filtered.append(obj)
        else:
            # Wrap-around case: field crosses RA=0/360
            if obj.ra >= min_ra or obj.ra <= max_ra:
                filtered.append(obj)
    
    return filtered


def _get_object_type(name: str) -> str:
    """Determine object type from name (galaxy, nebula, cluster, etc.)."""
    name_upper = name.upper().strip()
    if name_upper.startswith("M "):
        # Messier objects - could be galaxy, nebula, or cluster
        return "messier"
    elif name_upper.startswith("NGC ") or name_upper.startswith("IC "):
        return "ngc_ic"
    elif name_upper.startswith("LBN ") or name_upper.startswith("LDN "):
        return "nebula"
    elif name_upper.startswith("VDB ") or name_upper.startswith("SHARPLESS "):
        return "nebula"
    elif name_upper.startswith("ABELL "):
        return "cluster"
    else:
        return "unknown"


def _get_object_color(obj_type: str) -> tuple[int, int, int]:
    """Get color for object type (aesthetic colors, not bright red/green)."""
    colors = {
        "messier": (255, 200, 100),      # Warm gold
        "ngc_ic": (150, 200, 255),       # Soft blue
        "nebula": (200, 150, 255),       # Lavender
        "cluster": (255, 180, 150),      # Peach
        "unknown": (200, 200, 200),      # Light gray
    }
    return colors.get(obj_type, colors["unknown"])


def _draw_object(draw: ImageDraw.ImageDraw, x: float, y: float, obj: CelestialObject, 
                obj_type: str, width: int, height: int, wcs: WCS, font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> None:
    """Draw a celestial object on the image.
    
    Args:
        draw: PIL ImageDraw context
        x, y: Pixel coordinates
        obj: Celestial object to draw
        obj_type: Type of object
        width, height: Image dimensions
        wcs: WCS object for coordinate conversion
        font: Font for text labels
    """
    # Calculate dynamic sizing
    min_dimension = min(width, height)
    scale_factor = min_dimension / 1000.0
    # Thickness: 6x the original (was 1 * scale_factor, now 6 * scale_factor)
    base_thickness = max(1, int(4 * scale_factor))
    # Font size: 144x the original
    font_size = max(10, int(48 * scale_factor))
    
    color = _get_object_color(obj_type)
    
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
    
    # Draw label
    try:
        # Position label above the object
        label_offset = radius_pixels + font_size + 5
        label_y = y - label_offset
        # Ensure label is within bounds
        if label_y < 0:
            label_y = y + label_offset
        
        # Draw text with shadow for readability (larger shadow offset for bigger font)
        text_shadow_offset = max(2, int(3 * scale_factor))
        draw.text((x + text_shadow_offset, label_y + text_shadow_offset), obj.name, 
                 fill=(0, 0, 0), font=font)  # Shadow
        draw.text((x, label_y), obj.name, fill=color, font=font)
    except Exception:  # noqa: BLE001
        pass  # Skip label if font rendering fails


def _generate_annotation_python(job_id: int, source_path: Path, wcs_path: Path, radius: float, scale: float = 1.0, max_objects: int = 20) -> Path:
    """Generate annotated image using catalogs.csv.
    
    Args:
        job_id: Job ID
        source_path: Path to source image
        wcs_path: Path to WCS FITS file
        radius: Field radius in degrees (unused, calculated from image)
        scale: Scale factor (unused)
        max_objects: Maximum number of objects to annotate (default 15)
    """
    logger.info("Generating annotation using catalogs.csv for job %s", job_id)
    
    job_dir = prepare_job_dir(job_id)
    output_path = job_dir / "annotated.jpg"
    
    # Load source image FIRST to get actual dimensions
    img = Image.open(source_path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    width, height = img.size
    logger.info("Source image size: %dx%d pixels", width, height)
    
    # Load WCS and calculate field bounds
    with fits.open(wcs_path) as hdul:
        header = hdul[0].header
        wcs = WCS(header)
        
        # Calculate field bounds
        min_ra, max_ra, min_dec, max_dec = _get_field_corners(wcs, width, height)
        logger.info("Field bounds: RA=[%.4f, %.4f], Dec=[%.4f, %.4f]", min_ra, max_ra, min_dec, max_dec)
    
    # Load catalog
    catalog_path = settings.catalogs_dir / "catalogs.csv"
    all_objects = _load_catalog_csv(catalog_path)
    
    # Filter objects in field
    objects_in_field = _filter_objects_in_field(all_objects, min_ra, max_ra, min_dec, max_dec)
    logger.info("Found %d objects in field (out of %d total)", len(objects_in_field), len(all_objects))
    
    # Deduplicate
    deduplicated = _deduplicate_objects(objects_in_field)
    logger.info("After deduplication: %d objects", len(deduplicated))
    
    # Select top N (already sorted by priority)
    selected = deduplicated[:max_objects]
    logger.info("Selected top %d objects for annotation", len(selected))
    
    # Calculate dynamic sizing
    min_dimension = min(width, height)
    scale_factor = min_dimension / 1000.0
    # Font size: 4x the original
    font_size = max(10, int(24 * scale_factor))
    
    # Create drawing context
    draw = ImageDraw.Draw(img)
    
    # Load font
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
    except Exception:  # noqa: BLE001
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
        except Exception:  # noqa: BLE001
            font = ImageFont.load_default()
            logger.debug("Using default font")
    
    # Draw selected objects
    objects_drawn = 0
    for obj in selected:
        try:
            # Convert RA/Dec to pixel coordinates
            pixel = wcs.world_to_pixel_values(obj.ra, obj.dec)
            x, y = float(pixel[0]), float(pixel[1])
            
            # Only draw if within image bounds
            if 0 <= x < width and 0 <= y < height:
                obj_type = _get_object_type(obj.name)
                _draw_object(draw, x, y, obj, obj_type, width, height, wcs, font)
                objects_drawn += 1
                logger.debug("Drew object: %s at (%.1f, %.1f)", obj.name, x, y)
        except Exception as e:  # noqa: BLE001
            logger.debug("Error drawing object %s: %s", obj.name, e)
            continue
    
    logger.info("Drew %d objects on image", objects_drawn)
    
    # Save annotated image
    img.save(output_path, "JPEG", quality=95)
    logger.info("Generated annotated image for job %s at %s", job_id, output_path)
    return output_path


def _plot_bright_stars(draw: ImageDraw.ImageDraw, wcs: WCS, width: int, height: int, radius: float, cat_dir: Path, base_size: int = 3, outline_width: int = 1) -> None:
    """Plot bright stars from brightstars.fits catalog."""
    bright_fn = cat_dir / "brightstars.fits"
    if not bright_fn.exists():
        logger.debug("Bright stars catalog not found: %s", bright_fn)
        return
    
    try:
        with fits.open(bright_fn) as hdul:
            data = hdul[1].data  # Usually HDU 1 contains the table
            # Try both uppercase and lowercase column names
            if "RA" in data.dtype.names:
                ra = data["RA"]
            elif "ra" in data.dtype.names:
                ra = data["ra"]
            else:
                logger.warning("RA column not found in bright stars catalog. Available columns: %s", data.dtype.names)
                return
            
            if "DEC" in data.dtype.names:
                dec = data["DEC"]
            elif "dec" in data.dtype.names:
                dec = data["dec"]
            else:
                logger.warning("DEC column not found in bright stars catalog. Available columns: %s", data.dtype.names)
                return
            
            # Try various magnitude column names
            mag_cols = ["MAG", "mag", "VMAG", "vmag"]
            mag = None
            for col in mag_cols:
                if col in data.dtype.names:
                    mag = data[col]
                    logger.debug("Using magnitude column: %s", col)
                    break
            if mag is None:
                mag = np.ones(len(ra)) * 5.0  # Default magnitude if not present
                logger.debug("Using default magnitude 5.0")
            
            # Filter stars within field of view
            center = wcs.pixel_to_world(width / 2, height / 2)
            center_ra = center.ra.deg
            center_dec = center.dec.deg
            
            logger.debug("Field center: RA=%.4f, Dec=%.4f, radius=%.4f deg", center_ra, center_dec, radius)
            logger.debug("Image size: %dx%d", width, height)
            
            # Convert to pixel coordinates
            stars_drawn = 0
            stars_checked = 0
            stars_in_field = 0
            stars_in_bounds = 0
            
            for star_ra, star_dec, star_mag in zip(ra, dec, mag):
                stars_checked += 1
                try:
                    # Check if star is within reasonable distance
                    ra_diff = abs(star_ra - center_ra)
                    if ra_diff > 180:
                        ra_diff = 360 - ra_diff
                    dec_diff = abs(star_dec - center_dec)
                    
                    # Rough check: within 2x radius (degrees)
                    distance_sq = ra_diff**2 + dec_diff**2
                    if distance_sq > (radius * 2)**2:
                        continue
                    
                    stars_in_field += 1
                    
                    # Convert RA/Dec to pixel coordinates
                    pixel = wcs.world_to_pixel_values(star_ra, star_dec)
                    x, y = float(pixel[0]), float(pixel[1])
                    
                    # Only plot if within image bounds
                    if 0 <= x < width and 0 <= y < height:
                        stars_in_bounds += 1
                        # Star size based on magnitude (brighter = larger)
                        # Use dynamic sizing based on image dimensions
                        mag_factor = max(0.5, (8 - star_mag) / 4.0)  # Scale by magnitude
                        size = max(base_size, int(base_size * mag_factor * 1.5))
                        outline_w = max(1, outline_width)
                        
                        # Draw star as bright circle with crosshair for visibility
                        draw.ellipse([x - size, y - size, x + size, y + size], 
                                    fill=(255, 255, 0), outline=(255, 0, 0), width=outline_w)
                        # Add crosshair for better visibility
                        cross_size = int(size * 1.5)
                        cross_width = max(1, outline_w)
                        draw.line([x - cross_size, y, x + cross_size, y], fill=(255, 0, 0), width=cross_width)
                        draw.line([x, y - cross_size, x, y + cross_size], fill=(255, 0, 0), width=cross_width)
                        stars_drawn += 1
                        if stars_drawn <= 5:  # Log first few stars
                            logger.debug("Drew star: RA=%.4f Dec=%.4f mag=%.1f -> pixel=(%.1f, %.1f) size=%d", 
                                        star_ra, star_dec, star_mag, x, y, size)
                except Exception as e:  # noqa: BLE001
                    logger.debug("Error converting star RA=%.4f Dec=%.4f: %s", star_ra, star_dec, e)
                    continue  # Skip stars that can't be converted
            
            logger.info("Bright stars: checked %d, in field %d, in bounds %d, drawn %d", 
                       stars_checked, stars_in_field, stars_in_bounds, stars_drawn)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error reading bright stars catalog: %s", exc)


def _plot_ngc_objects(draw: ImageDraw.ImageDraw, wcs: WCS, width: int, height: int, radius: float, cat_dir: Path, base_size: int = 4, outline_width: int = 1) -> None:
    """Plot NGC/IC objects from openngc catalogs (matching plotann.py logic for radius < 10.0)."""
    ngc_fn = cat_dir / "openngc-ngc.fits"
    ic_fn = cat_dir / "openngc-ic.fits"
    ngc_names_fn = cat_dir / "openngc-names.fits"
    
    # Check if all required files exist (matching plotann.py requirement)
    if not (ngc_fn.exists() and ic_fn.exists() and ngc_names_fn.exists()):
        logger.debug("NGC/IC catalogs not all found: ngc=%s, ic=%s, names=%s", 
                    ngc_fn.exists(), ic_fn.exists(), ngc_names_fn.exists())
        return
    
    try:
        center = wcs.pixel_to_world(width / 2, height / 2)
        center_ra = center.ra.deg
        center_dec = center.dec.deg
        
        # Plot NGC objects
        with fits.open(ngc_fn) as hdul:
            data = hdul[1].data
            # Try both uppercase and lowercase
            if "RA" in data.dtype.names:
                ra = data["RA"]
            elif "ra" in data.dtype.names:
                ra = data["ra"]
            else:
                logger.warning("RA column not found in NGC catalog. Available columns: %s", data.dtype.names)
                return
            
            if "DEC" in data.dtype.names:
                dec = data["DEC"]
            elif "dec" in data.dtype.names:
                dec = data["dec"]
            else:
                logger.warning("DEC column not found in NGC catalog. Available columns: %s", data.dtype.names)
                return
            
            ngc_drawn = 0
            ngc_checked = 0
            ngc_in_field = 0
            ngc_in_bounds = 0
            for obj_ra, obj_dec in zip(ra, dec):
                ngc_checked += 1
                try:
                    ra_diff = abs(obj_ra - center_ra)
                    if ra_diff > 180:
                        ra_diff = 360 - ra_diff
                    dec_diff = abs(obj_dec - center_dec)
                    
                    if ra_diff**2 + dec_diff**2 > (radius * 2)**2:
                        continue
                    
                    ngc_in_field += 1
                    
                    pixel = wcs.world_to_pixel_values(obj_ra, obj_dec)
                    x, y = float(pixel[0]), float(pixel[1])
                    
                    if 0 <= x < width and 0 <= y < height:
                        ngc_in_bounds += 1
                        # Draw NGC object as visible square - use dynamic sizing
                        size = base_size + 2
                        outline_w = max(1, outline_width)
                        draw.rectangle([x - size, y - size, x + size, y + size],
                                      fill=(0, 200, 255), outline=(255, 0, 0), width=outline_w)
                        # Add diagonal lines for better visibility
                        line_width = max(1, outline_w)
                        draw.line([x - size, y - size, x + size, y + size], fill=(255, 0, 0), width=line_width)
                        draw.line([x - size, y + size, x + size, y - size], fill=(255, 0, 0), width=line_width)
                        ngc_drawn += 1
                except Exception as e:  # noqa: BLE001
                    logger.debug("Error converting NGC RA=%.4f Dec=%.4f: %s", obj_ra, obj_dec, e)
                    continue
            
            logger.info("NGC objects: checked %d, in field %d, in bounds %d, drawn %d", 
                       ngc_checked, ngc_in_field, ngc_in_bounds, ngc_drawn)
        
        # Plot IC objects (similar to NGC)
        with fits.open(ic_fn) as hdul:
            data = hdul[1].data
            # Try both uppercase and lowercase
            if "RA" in data.dtype.names:
                ra = data["RA"]
            elif "ra" in data.dtype.names:
                ra = data["ra"]
            else:
                logger.warning("RA column not found in IC catalog")
                return
            
            if "DEC" in data.dtype.names:
                dec = data["DEC"]
            elif "dec" in data.dtype.names:
                dec = data["dec"]
            else:
                logger.warning("DEC column not found in IC catalog")
                return
            
            for obj_ra, obj_dec in zip(ra, dec):
                try:
                    ra_diff = abs(obj_ra - center_ra)
                    if ra_diff > 180:
                        ra_diff = 360 - ra_diff
                    dec_diff = abs(obj_dec - center_dec)
                    
                    if ra_diff**2 + dec_diff**2 > (radius * 2)**2:
                        continue
                    
                    pixel = wcs.world_to_pixel_values(obj_ra, obj_dec)
                    x, y = float(pixel[0]), float(pixel[1])
                    
                    if 0 <= x < width and 0 <= y < height:
                        size = 3
                        draw.rectangle([x - size, y - size, x + size, y + size],
                                      fill=(150, 200, 255), outline=(100, 150, 255))
                except Exception:  # noqa: BLE001
                    continue
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error reading NGC/IC catalogs: %s", exc)


def _plot_abell_clusters(draw: ImageDraw.ImageDraw, wcs: WCS, width: int, height: int, radius: float, cat_dir: Path, base_size: int = 2, outline_width: int = 1) -> None:
    """Plot Abell galaxy clusters (matching plotann.py logic for radius < 1.0)."""
    abell_fn = cat_dir / "abell-all.fits"
    if not abell_fn.exists():
        logger.debug("Abell catalog not found: %s", abell_fn)
        return
    
    try:
        with fits.open(abell_fn) as hdul:
            data = hdul[1].data
            # Try both uppercase and lowercase
            if "RA" in data.dtype.names:
                ra = data["RA"]
            elif "ra" in data.dtype.names:
                ra = data["ra"]
            else:
                logger.warning("RA column not found in Abell catalog")
                return
            
            if "DEC" in data.dtype.names:
                dec = data["DEC"]
            elif "dec" in data.dtype.names:
                dec = data["dec"]
            else:
                logger.warning("DEC column not found in Abell catalog")
                return
            
            center = wcs.pixel_to_world(width / 2, height / 2)
            center_ra = center.ra.deg
            center_dec = center.dec.deg
            
            for cluster_ra, cluster_dec in zip(ra, dec):
                try:
                    ra_diff = abs(cluster_ra - center_ra)
                    if ra_diff > 180:
                        ra_diff = 360 - ra_diff
                    dec_diff = abs(cluster_dec - center_dec)
                    
                    if ra_diff**2 + dec_diff**2 > (radius * 2)**2:
                        continue
                    
                    pixel = wcs.world_to_pixel_values(cluster_ra, cluster_dec)
                    x, y = float(pixel[0]), float(pixel[1])
                    
                    if 0 <= x < width and 0 <= y < height:
                        # Draw Abell cluster as circle - use dynamic sizing
                        size = max(2, int(base_size * 0.8))
                        outline_w = max(1, outline_width)
                        draw.ellipse([x - size, y - size, x + size, y + size],
                                    fill=(255, 200, 100), outline=(255, 150, 50), width=outline_w)
                except Exception:  # noqa: BLE001
                    continue
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error reading Abell catalog: %s", exc)


async def generate_annotation(job_id: int, source_path: Path, wcs_path: Path, radius: float, scale: float = 1.0, max_objects: int = 20) -> Path:
    """Generate annotated image using catalogs.csv.
    
    Args:
        job_id: Job ID
        source_path: Path to source image
        wcs_path: Path to WCS FITS file
        radius: Field radius in degrees (unused, calculated from image)
        scale: Scale factor (unused)
        max_objects: Maximum number of objects to annotate (default 15)
    """
    logger.info("Starting annotation generation for job %s", job_id)
    logger.info("Parameters - source: %s, wcs: %s, radius: %s, scale: %s, max_objects: %d", 
               source_path, wcs_path, radius, scale, max_objects)
    
    job_dir = prepare_job_dir(job_id)
    
    logger.info("Job directory: %s", job_dir)
    logger.info("Checking source file: %s exists: %s", source_path, source_path.exists())
    logger.info("Checking WCS file: %s exists: %s", wcs_path, wcs_path.exists())
    
    # Use Python implementation with catalogs.csv
    try:
        return _generate_annotation_python(job_id, source_path, wcs_path, radius, scale, max_objects)
    except Exception as exc:  # noqa: BLE001
        logger.error("Error generating annotation with Python for job %s: %s", job_id, exc, exc_info=True)
        return generate_placeholder_annotation(job_id, source_path)


def generate_placeholder_annotation(job_id: int, source_path: Path) -> Path:
    """Generate a placeholder annotation image."""
    job_dir = prepare_job_dir(job_id)
    target = job_dir / "annotated.png"

    img = Image.new("RGB", (640, 360), color=(10, 10, 30))
    draw = ImageDraw.Draw(img)
    text = [
        f"Job #{job_id}",
        f"Source: {source_path.name}",
        f"Generated: {datetime.utcnow().isoformat()}Z",
        "(Placeholder annotation)",
    ]
    font = ImageFont.load_default()
    y = 40
    for line in text:
        draw.text((40, y), line, fill=(200, 200, 200), font=font)
        y += 30
    draw.rectangle([(20, 20), (620, 340)], outline=(50, 180, 255), width=3)
    img.save(target)
    return target
