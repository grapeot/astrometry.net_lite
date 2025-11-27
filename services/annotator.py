from __future__ import annotations

import asyncio
import logging
import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from PIL import Image, ImageDraw, ImageFont

from core.config import settings
from services.storage import prepare_job_dir

logger = logging.getLogger(__name__)


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


def _generate_annotation_python(job_id: int, source_path: Path, wcs_path: Path, radius: float, scale: float = 1.0) -> Path:
    """Generate annotated image using Python (astropy + PIL) instead of plotann.py.
    
    Follows the same catalog selection logic as plotann.py:
    - radius < 1.0: Abell clusters, HD catalog
    - radius < 0.25: Tycho-2 catalog
    - radius < 10.0: NGC/IC objects
    - radius <= 30.0: Bright stars (radius > 30.0 skips bright stars)
    """
    logger.info("Generating annotation using Python implementation for job %s", job_id)
    
    job_dir = prepare_job_dir(job_id)
    output_path = job_dir / "annotated.jpg"
    
    # Load source image FIRST to get actual dimensions
    img = Image.open(source_path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    width, height = img.size
    logger.info("Source image size: %dx%d pixels", width, height)
    
    # Calculate scaling factors based on image size
    # Base everything on the smaller dimension to ensure visibility
    min_dimension = min(width, height)
    scale_factor = min_dimension / 1000.0  # Normalize to 1000px base
    
    # Dynamic sizing based on image dimensions
    star_base_size = max(2, int(3 * scale_factor))
    star_outline_width = max(1, int(2 * scale_factor))
    ngc_base_size = max(3, int(4 * scale_factor))
    ngc_outline_width = max(1, int(2 * scale_factor))
    font_size = max(10, int(12 * scale_factor))
    
    logger.info("Annotation scaling: base_size=%.1f, star_size=%d, ngc_size=%d, font_size=%d",
               scale_factor, star_base_size, ngc_base_size, font_size)
    
    # Load WCS and recalculate radius from actual image dimensions
    with fits.open(wcs_path) as hdul:
        header = hdul[0].header
        wcs = WCS(header)
        
        # Recalculate radius from actual image dimensions (more accurate than passed parameter)
        from astropy.wcs.utils import proj_plane_pixel_scales
        scales = proj_plane_pixel_scales(wcs)
        width_deg = float(scales[0] * width)
        height_deg = float(scales[1] * height)
        calculated_radius = max(width_deg, height_deg) / 2
        
        logger.info("Field parameters: width=%.4f deg, height=%.4f deg, radius=%.4f deg (passed: %.4f)", 
                   width_deg, height_deg, calculated_radius, radius)
        
        # Use calculated radius instead of passed parameter (more accurate)
        radius = calculated_radius
    
    # Create drawing context
    draw = ImageDraw.Draw(img)
    
    # Try to load a font (fallback to default if not available)
    try:
        # Try to use a larger font if available
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
    except Exception:  # noqa: BLE001
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
        except Exception:  # noqa: BLE001
            # Fallback to default font (will be small, but better than nothing)
            font = ImageFont.load_default()
            logger.debug("Using default font (size may not scale properly)")
    
    cat_dir = settings.catalogs_dir
    
    # Plot bright stars (unless radius > 30.0, matching plotann.py logic)
    if radius <= 30.0:
        try:
            _plot_bright_stars(draw, wcs, width, height, radius, cat_dir, star_base_size, star_outline_width)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to plot bright stars for job %s: %s", job_id, exc)
    
    # Plot NGC/IC objects (only if radius < 10.0, matching plotann.py logic)
    if radius < 10.0:
        try:
            _plot_ngc_objects(draw, wcs, width, height, radius, cat_dir, ngc_base_size, ngc_outline_width)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to plot NGC objects for job %s: %s", job_id, exc)
    
    # Plot Abell clusters (only if radius < 1.0, matching plotann.py logic)
    if radius < 1.0:
        try:
            _plot_abell_clusters(draw, wcs, width, height, radius, cat_dir, star_base_size, star_outline_width)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to plot Abell clusters for job %s: %s", job_id, exc)
    
    # Note: HD catalog and Tycho-2 would go here if needed, but they require more complex handling
    # For now, we focus on the most visible annotations: bright stars and NGC objects
    
    # Save annotated image
    img.save(output_path, "JPEG", quality=95)
    logger.info("Generated annotated image using Python for job %s at %s", job_id, output_path)
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


async def generate_annotation(job_id: int, source_path: Path, wcs_path: Path, radius: float, scale: float = 1.0) -> Path:
    """Generate annotated image, trying plotann.py first, then falling back to Python implementation."""
    logger.info("Starting annotation generation for job %s", job_id)
    logger.info("Parameters - source: %s, wcs: %s, radius: %s, scale: %s", source_path, wcs_path, radius, scale)
    
    job_dir = prepare_job_dir(job_id)
    pnm_path = job_dir / "source.ppm"
    output_path = job_dir / "annotated.jpg"
    
    logger.info("Job directory: %s", job_dir)
    logger.info("Checking source file: %s exists: %s", source_path, source_path.exists())
    logger.info("Checking WCS file: %s exists: %s", wcs_path, wcs_path.exists())
    
    # Try plotann.py first
    try:
        # Convert source image to PPM
        logger.info("Converting source image to PPM format")
        _convert_to_ppm(source_path, pnm_path)
        logger.info("PPM file created at %s, exists: %s", pnm_path, pnm_path.exists())
        
        # Build plotann.py command
        args = _build_plotann_args(job_dir, wcs_path, pnm_path, output_path, radius, scale)
        
        logger.info("Running plotann.py for job %s: %s", job_id, " ".join(args))
        logger.info("Input files - WCS: %s, PPM: %s, Output: %s", wcs_path, pnm_path, output_path)
        logger.info("Checking file existence - WCS exists: %s, PPM exists: %s", wcs_path.exists(), pnm_path.exists())
        
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        
        stdout_text = stdout.decode("utf-8", errors="ignore")
        stderr_text = stderr.decode("utf-8", errors="ignore")
        
        logger.info("plotann.py for job %s finished with return code: %s", job_id, proc.returncode)
        if stdout_text:
            logger.info("plotann.py stdout for job %s: %s", job_id, stdout_text[:500])
        if stderr_text:
            logger.info("plotann.py stderr for job %s: %s", job_id, stderr_text[:500])
        
        if proc.returncode == 0 and output_path.exists():
            logger.info("Generated annotated image using plotann.py for job %s at %s", job_id, output_path)
            return output_path
        else:
            logger.warning("plotann.py failed or output not found for job %s, trying Python implementation", job_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error running plotann.py for job %s: %s, trying Python implementation", job_id, exc)
    
    # Fallback to Python implementation
    try:
        return _generate_annotation_python(job_id, source_path, wcs_path, radius, scale)
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
