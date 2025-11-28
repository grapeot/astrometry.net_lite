"""Annotation service for generating annotated astronomical images."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from astropy.io import fits
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_scales
from PIL import Image, ImageDraw, ImageFont

from core.config import settings
from services.annotator import catalog, label_layout, renderer
from services.storage import prepare_job_dir

# Re-export CelestialObject for backward compatibility
from services.annotator.catalog import CelestialObject

logger = logging.getLogger(__name__)

# Export public API
__all__ = ["generate_annotation", "generate_placeholder_annotation", "CelestialObject"]


def _generate_annotation_python(job_id: int, source_path: Path, wcs_path: Path, radius: float, scale: float = 1.0, max_objects: int = 20) -> Path:
    """Generate annotated image using catalogs.csv.
    
    Args:
        job_id: Job ID
        source_path: Path to source image
        wcs_path: Path to WCS FITS file
        radius: Field radius in degrees (unused, calculated from image)
        scale: Scale factor (unused)
        max_objects: Maximum number of objects to annotate (default 20)
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
        min_ra, max_ra, min_dec, max_dec = catalog.get_field_corners(wcs, width, height)
        logger.info("Field bounds: RA=[%.4f, %.4f], Dec=[%.4f, %.4f]", min_ra, max_ra, min_dec, max_dec)
    
    # Load catalog
    catalog_path = settings.catalogs_dir / "catalogs.csv"
    all_objects = catalog.load_catalog_csv(catalog_path)
    
    # Filter objects in field
    objects_in_field = catalog.filter_objects_in_field(all_objects, min_ra, max_ra, min_dec, max_dec)
    logger.info("Found %d objects in field (out of %d total)", len(objects_in_field), len(all_objects))
    
    # Deduplicate
    deduplicated = catalog.deduplicate_objects(objects_in_field)
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
    
    # First pass: calculate all object positions and initial label positions
    object_positions = []
    for obj in selected:
        try:
            # Convert RA/Dec to pixel coordinates
            pixel = wcs.world_to_pixel_values(obj.ra, obj.dec)
            x, y = float(pixel[0]), float(pixel[1])
            
            # Only process if within image bounds
            if 0 <= x < width and 0 <= y < height:
                # Calculate radius for label positioning
                scales = proj_plane_pixel_scales(wcs)
                avg_scale = (abs(scales[0]) + abs(scales[1])) / 2.0
                
                if obj.ang_diameter is not None and obj.ang_diameter > 0:
                    radius_deg = obj.ang_diameter / 60.0 / 2.0
                    radius_pixels = radius_deg / avg_scale
                else:
                    default_radius_deg = 0.1
                    radius_pixels = default_radius_deg / avg_scale
                
                # Initial label position (above object)
                label_offset = radius_pixels + font_size + 5
                label_y = y - label_offset
                if label_y < 0:
                    label_y = y + label_offset
                label_x = x
                
                object_positions.append((obj, x, y, radius_pixels, label_x, label_y))
        except Exception as e:  # noqa: BLE001
            logger.debug("Error processing object %s: %s", obj.name, e)
            continue
    
    # Second pass: adjust label positions to avoid overlap (greedy algorithm)
    adjusted_labels = []
    existing_label_bboxes = []
    
    for obj, x, y, radius_pixels, initial_label_x, initial_label_y in object_positions:
        # Adjust label position
        adjusted_x, adjusted_y = label_layout.adjust_label_position(
            initial_label_x, initial_label_y, obj.name, font,
            existing_label_bboxes, x, y, radius_pixels, width, height, font_size
        )
        
        # Calculate bounding box for adjusted label
        label_bbox = label_layout.get_text_bbox(obj.name, adjusted_x, adjusted_y, font)
        existing_label_bboxes.append(label_bbox)
        
        adjusted_labels.append((obj, x, y, adjusted_x, adjusted_y))
    
    # Third pass: draw objects with adjusted label positions
    # Sort by priority (reverse order: highest priority last, so it renders on top)
    adjusted_labels_sorted = sorted(
        adjusted_labels,
        key=lambda item: catalog.get_catalog_priority(item[0].name),
        reverse=False  # Lower priority number = higher priority, so we want lowest numbers last
    )
    # Reverse to draw highest priority last (on top)
    adjusted_labels_sorted.reverse()
    
    objects_drawn = 0
    for obj, x, y, label_x, label_y in adjusted_labels_sorted:
        try:
            obj_type = catalog.get_object_type(obj.name)
            renderer.draw_object(draw, x, y, obj, obj_type, width, height, wcs, font, label_x, label_y)
            objects_drawn += 1
            logger.debug("Drew object: %s (priority %d) at (%.1f, %.1f) with label at (%.1f, %.1f)", 
                        obj.name, catalog.get_catalog_priority(obj.name), x, y, label_x, label_y)
        except Exception as e:  # noqa: BLE001
            logger.debug("Error drawing object %s: %s", obj.name, e)
            continue
    
    logger.info("Drew %d objects on image", objects_drawn)

    # Save annotated image
    img.save(output_path, "JPEG", quality=95)
    logger.info("Generated annotated image for job %s at %s (file size: %d bytes)", job_id, output_path, output_path.stat().st_size)
    return output_path


async def generate_annotation(job_id: int, source_path: Path, wcs_path: Path, radius: float, scale: float = 1.0, max_objects: int = 20) -> Path:
    """Generate annotated image using catalogs.csv.
    
    Args:
        job_id: Job ID
        source_path: Path to source image
        wcs_path: Path to WCS FITS file
        radius: Field radius in degrees (unused, calculated from image)
        scale: Scale factor (unused)
        max_objects: Maximum number of objects to annotate (default 20)
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
        f"Generated: {datetime.now(UTC).isoformat()}Z",
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

