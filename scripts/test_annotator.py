#!/usr/bin/env python3
"""
测试 annotated image 生成功能
可以直接测试已完成的 job，或者使用测试图片
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services import annotator
from services.storage import prepare_job_dir

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)


async def test_existing_job(job_id: int) -> None:
    """测试一个已完成的 job 的 annotated image 生成"""
    logger.info("Testing annotated image generation for job %s", job_id)
    
    job_dir = prepare_job_dir(job_id)
    wcs_path = job_dir / "wcs.fits"
    source_path = job_dir.parent / "uploads" / f"job_{job_id}.jpg"
    
    # Try to find source image in various locations
    if not source_path.exists():
        # Check if there's a source image in job directory
        for ext in [".jpg", ".jpeg", ".png", ".fits"]:
            potential = job_dir / f"source{ext}"
            if potential.exists():
                source_path = potential
                break
        else:
            logger.error("Could not find source image for job %s", job_id)
            logger.info("Please provide source image path manually")
            return
    
    if not wcs_path.exists():
        logger.error("WCS file not found for job %s: %s", job_id, wcs_path)
        return
    
    logger.info("Using source image: %s", source_path)
    logger.info("Using WCS file: %s", wcs_path)
    
    # Get radius from calibration (default to 1.0)
    radius = 1.0
    try:
        from astropy.io import fits
        from astropy.wcs import WCS
        from astropy.wcs.utils import proj_plane_pixel_scales
        
        with fits.open(wcs_path) as hdul:
            header = hdul[0].header
            wcs = WCS(header)
            imagew = header.get("NAXIS1", 1000)
            imageh = header.get("NAXIS2", 1000)
            scales = proj_plane_pixel_scales(wcs)
            width_deg = float(scales[0] * imagew)
            height_deg = float(scales[1] * imageh)
            radius = max(width_deg, height_deg) / 2
            logger.info("Calculated radius: %.4f degrees", radius)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not calculate radius, using default 1.0: %s", exc)
    
    # Generate annotation
    try:
        output_path = await annotator.generate_annotation(
            job_id, source_path, wcs_path, radius
        )
        logger.info("✅ Successfully generated annotated image: %s", output_path)
        logger.info("   File size: %s bytes", output_path.stat().st_size if output_path.exists() else "N/A")
        logger.info("   You can view it at: http://127.0.0.1:8002/annotated_display/%s", job_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("❌ Failed to generate annotated image: %s", exc, exc_info=True)


async def test_with_files(source_path: Path, wcs_path: Path, radius: float = 1.0) -> None:
    """使用指定的文件测试 annotated image 生成"""
    logger.info("Testing annotated image generation with files")
    logger.info("  Source: %s", source_path)
    logger.info("  WCS: %s", wcs_path)
    logger.info("  Radius: %s degrees", radius)
    
    if not source_path.exists():
        logger.error("Source image not found: %s", source_path)
        return
    
    if not wcs_path.exists():
        logger.error("WCS file not found: %s", wcs_path)
        return
    
    # Use a test job ID
    test_job_id = 99999
    
    try:
        output_path = await annotator.generate_annotation(
            test_job_id, source_path, wcs_path, radius
        )
        logger.info("✅ Successfully generated annotated image: %s", output_path)
        logger.info("   File size: %s bytes", output_path.stat().st_size if output_path.exists() else "N/A")
    except Exception as exc:  # noqa: BLE001
        logger.error("❌ Failed to generate annotated image: %s", exc, exc_info=True)


def main():
    parser = argparse.ArgumentParser(description="Test annotated image generation")
    parser.add_argument("--job-id", type=int, help="Test with an existing job ID")
    parser.add_argument("--source", type=Path, help="Source image path")
    parser.add_argument("--wcs", type=Path, help="WCS FITS file path")
    parser.add_argument("--radius", type=float, default=1.0, help="Field radius in degrees")
    
    args = parser.parse_args()
    
    if args.job_id:
        asyncio.run(test_existing_job(args.job_id))
    elif args.source and args.wcs:
        asyncio.run(test_with_files(args.source, args.wcs, args.radius))
    else:
        parser.print_help()
        print("\nExamples:")
        print("  # Test with existing job 6:")
        print("  python scripts/test_annotator.py --job-id 6")
        print("\n  # Test with custom files:")
        print("  python scripts/test_annotator.py --source test.jpg --wcs data/jobs/6/wcs.fits --radius 0.5")


if __name__ == "__main__":
    main()

