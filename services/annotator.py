from __future__ import annotations

import asyncio
import logging
import subprocess
from datetime import datetime
from pathlib import Path

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


async def generate_annotation(job_id: int, source_path: Path, wcs_path: Path, radius: float, scale: float = 1.0) -> Path:
    """Generate annotated image using plotann.py."""
    job_dir = prepare_job_dir(job_id)
    pnm_path = job_dir / "source.ppm"
    output_path = job_dir / "annotated.jpg"
    
    # Convert source image to PPM
    _convert_to_ppm(source_path, pnm_path)
    
    # Build plotann.py command
    args = _build_plotann_args(job_dir, wcs_path, pnm_path, output_path, radius, scale)
    
    logger.info("Running plotann.py for job %s: %s", job_id, " ".join(args))
    
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            logger.warning("plotann.py failed for job %s: %s", job_id, stderr.decode())
            # Fallback to placeholder
            return generate_placeholder_annotation(job_id, source_path)
        
        if output_path.exists():
            logger.info("Generated annotated image for job %s", job_id)
            return output_path
        else:
            logger.warning("plotann.py completed but output file not found for job %s", job_id)
            return generate_placeholder_annotation(job_id, source_path)
    except Exception as exc:  # noqa: BLE001
        logger.error("Error running plotann.py for job %s: %s", job_id, exc)
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
