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
    
    # Load source image
    img = Image.open(source_path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    width, height = img.size
    
    # Load WCS
    with fits.open(wcs_path) as hdul:
        wcs = WCS(hdul[0].header)
    
    # Create drawing context
    draw = ImageDraw.Draw(img)
    
    cat_dir = settings.catalogs_dir
    
    # Plot bright stars (unless radius > 30.0, matching plotann.py logic)
    if radius <= 30.0:
        try:
            _plot_bright_stars(draw, wcs, width, height, radius, cat_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to plot bright stars for job %s: %s", job_id, exc)
    
    # Plot NGC/IC objects (only if radius < 10.0, matching plotann.py logic)
    if radius < 10.0:
        try:
            _plot_ngc_objects(draw, wcs, width, height, radius, cat_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to plot NGC objects for job %s: %s", job_id, exc)
    
    # Plot Abell clusters (only if radius < 1.0, matching plotann.py logic)
    if radius < 1.0:
        try:
            _plot_abell_clusters(draw, wcs, width, height, radius, cat_dir)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to plot Abell clusters for job %s: %s", job_id, exc)
    
    # Note: HD catalog and Tycho-2 would go here if needed, but they require more complex handling
    # For now, we focus on the most visible annotations: bright stars and NGC objects
    
    # Save annotated image
    img.save(output_path, "JPEG", quality=95)
    logger.info("Generated annotated image using Python for job %s at %s", job_id, output_path)
    return output_path


def _plot_bright_stars(draw: ImageDraw.ImageDraw, wcs: WCS, width: int, height: int, radius: float, cat_dir: Path) -> None:
    """Plot bright stars from brightstars.fits catalog."""
    bright_fn = cat_dir / "brightstars.fits"
    if not bright_fn.exists():
        logger.debug("Bright stars catalog not found: %s", bright_fn)
        return
    
    try:
        with fits.open(bright_fn) as hdul:
            data = hdul[1].data  # Usually HDU 1 contains the table
            # Try both uppercase and lowercase column names
            col_names = [name.upper() for name in data.names] if hasattr(data, 'names') else []
            if "RA" in col_names or "ra" in data.dtype.names:
                ra = data["RA"] if "RA" in data.dtype.names else data["ra"]
            else:
                logger.warning("RA column not found in bright stars catalog")
                return
            
            if "DEC" in col_names or "dec" in data.dtype.names:
                dec = data["DEC"] if "DEC" in data.dtype.names else data["dec"]
            else:
                logger.warning("DEC column not found in bright stars catalog")
                return
            
            # Try various magnitude column names
            mag_cols = ["MAG", "mag", "VMAG", "vmag"]
            mag = None
            for col in mag_cols:
                if col in data.dtype.names:
                    mag = data[col]
                    break
            if mag is None:
                mag = np.ones(len(ra)) * 5.0  # Default magnitude if not present
            
            # Filter stars within field of view
            center = wcs.pixel_to_world(width / 2, height / 2)
            center_ra = center.ra.deg
            center_dec = center.dec.deg
            
            # Convert to pixel coordinates
            for star_ra, star_dec, star_mag in zip(ra, dec, mag):
                try:
                    # Check if star is within reasonable distance
                    ra_diff = abs(star_ra - center_ra)
                    if ra_diff > 180:
                        ra_diff = 360 - ra_diff
                    dec_diff = abs(star_dec - center_dec)
                    
                    # Rough check: within 2x radius
                    if ra_diff**2 + dec_diff**2 > (radius * 2)**2:
                        continue
                    
                    # Convert RA/Dec to pixel coordinates
                    pixel = wcs.world_to_pixel_values(star_ra, star_dec)
                    x, y = float(pixel[0]), float(pixel[1])
                    
                    # Only plot if within image bounds
                    if 0 <= x < width and 0 <= y < height:
                        # Star size based on magnitude (brighter = larger)
                        size = max(1, int(6 - star_mag))
                        # Draw star as circle
                        draw.ellipse([x - size, y - size, x + size, y + size], 
                                    fill=(255, 255, 200), outline=(255, 255, 150))
                except Exception:  # noqa: BLE001
                    continue  # Skip stars that can't be converted
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error reading bright stars catalog: %s", exc)


def _plot_ngc_objects(draw: ImageDraw.ImageDraw, wcs: WCS, width: int, height: int, radius: float, cat_dir: Path) -> None:
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
            ra = data["RA"]
            dec = data["DEC"]
            
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
                        # Draw NGC object as small square
                        size = 3
                        draw.rectangle([x - size, y - size, x + size, y + size],
                                      fill=(100, 200, 255), outline=(50, 150, 255))
                except Exception:  # noqa: BLE001
                    continue
        
        # Plot IC objects (similar to NGC)
        with fits.open(ic_fn) as hdul:
            data = hdul[1].data
            ra = data["RA"]
            dec = data["DEC"]
            
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


def _plot_abell_clusters(draw: ImageDraw.ImageDraw, wcs: WCS, width: int, height: int, radius: float, cat_dir: Path) -> None:
    """Plot Abell galaxy clusters (matching plotann.py logic for radius < 1.0)."""
    abell_fn = cat_dir / "abell-all.fits"
    if not abell_fn.exists():
        logger.debug("Abell catalog not found: %s", abell_fn)
        return
    
    try:
        with fits.open(abell_fn) as hdul:
            data = hdul[1].data
            ra = data["RA"]
            dec = data["DEC"]
            
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
                        # Draw Abell cluster as small circle
                        size = 2
                        draw.ellipse([x - size, y - size, x + size, y + size],
                                    fill=(255, 200, 100), outline=(255, 150, 50))
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
