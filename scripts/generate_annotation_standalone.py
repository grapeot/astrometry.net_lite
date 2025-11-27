#!/usr/bin/env python3
"""
Standalone script to generate annotated image for a completed job.
This simulates what the worker does when generating annotated images.

Usage:
    python scripts/generate_annotation_standalone.py --job-id 8
    python scripts/generate_annotation_standalone.py --job-id 8 --output custom_output.jpg
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
from astropy.io import fits
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_scales

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)


async def generate_for_job(job_id: int, output_path: Path | None = None, source_path_override: Path | None = None) -> Path:
    """Generate annotated image for a completed job."""
    logger.info("=" * 60)
    logger.info("Generating annotated image for job %s", job_id)
    logger.info("=" * 60)
    
    job_dir = prepare_job_dir(job_id)
    wcs_path = job_dir / "wcs.fits"
    
    # Check if WCS exists
    if not wcs_path.exists():
        logger.error("❌ WCS file not found: %s", wcs_path)
        logger.error("   Job %s may not have completed successfully.", job_id)
        sys.exit(1)
    
    logger.info("✓ WCS file found: %s", wcs_path)
    
    # Find source image - try MongoDB first, then fallback to file search
    source_path = source_path_override
    
    if not source_path:
        # Try to get from MongoDB
        try:
            from services.mongo import create_mongo_client, get_database
            from services import queue as queue_service
            
            client = create_mongo_client()
            db = get_database(client)
            
            # Get job from queue to find stored_path
            from services.queue import _collection
            queue_collection = _collection(db)
            queue_doc = await queue_collection.find_one({"job_id": job_id})
            
            if queue_doc and "payload" in queue_doc:
                stored_path = queue_doc["payload"].get("stored_path")
                if stored_path:
                    source_path = Path(stored_path)
                    if source_path.exists():
                        logger.info("✓ Source image found from MongoDB: %s", source_path)
                    else:
                        logger.warning("⚠ MongoDB stored_path not found: %s", stored_path)
                        source_path = None
            
            # Also try to get from job results
            if not source_path:
                from services import jobs as job_service
                job = await job_service.get_job_by_job_id(db, job_id)
                if job and job.results:
                    original_filename = job.results.get("original_filename")
                    if original_filename:
                        # Try to find in uploads directory
                        uploads_dir = Path("data/uploads")
                        possible_files = list(uploads_dir.glob(f"*{original_filename}"))
                        if possible_files:
                            source_path = possible_files[0]
                            logger.info("✓ Source image found from job results: %s", source_path)
            
            client.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not get source path from MongoDB: %s", exc)
    
    # Fallback: search for source image
    if not source_path or not source_path.exists():
        logger.info("Searching for source image in file system...")
        possible_locations = [
            # Check job directory for source files
            job_dir / "source.jpg",
            job_dir / "source.jpeg",
            job_dir / "source.png",
            job_dir / "source.fits",
        ]
        
        # Check uploads directory (try to find by job_id pattern)
        uploads_dir = Path("data/uploads")
        if uploads_dir.exists():
            possible_locations.extend(uploads_dir.glob(f"*{job_id}*"))
        
        # Also check for any image files in job directory
        for ext in ["jpg", "jpeg", "png", "fits"]:
            for pattern in [f"*.{ext}", f"*source*.{ext}", f"*original*.{ext}"]:
                possible_locations.extend(job_dir.glob(pattern))
        
        for loc in possible_locations:
            if loc.exists() and loc.is_file():
                source_path = loc
                logger.info("✓ Source image found: %s", source_path)
                break
    
    if not source_path or not source_path.exists():
        logger.error("❌ Source image not found for job %s", job_id)
        logger.error("   Searched in: %s", job_dir)
        logger.error("   Please provide source image path manually with --source")
        logger.error("")
        logger.error("   You can find the original filename from MongoDB:")
        logger.error("   python -c \"from services.mongo import *; from services import jobs; import asyncio; asyncio.run(jobs.get_job_by_job_id(get_database(create_mongo_client()), %s))\"", job_id)
        sys.exit(1)
    
    # Calculate radius from WCS
    try:
        with fits.open(wcs_path) as hdul:
            header = hdul[0].header
            wcs = WCS(header)
            imagew = header.get("NAXIS1", 1000)
            imageh = header.get("NAXIS2", 1000)
            scales = proj_plane_pixel_scales(wcs)
            width_deg = float(scales[0] * imagew)
            height_deg = float(scales[1] * imageh)
            radius = max(width_deg, height_deg) / 2
            
            logger.info("✓ Field parameters:")
            logger.info("   Image size: %dx%d pixels", imagew, imageh)
            logger.info("   Field size: %.4f x %.4f degrees", width_deg, height_deg)
            logger.info("   Field radius: %.4f degrees", radius)
            
            center = wcs.pixel_to_world(imagew / 2, imageh / 2)
            logger.info("   Center: RA=%.4f, Dec=%.4f", center.ra.deg, center.dec.deg)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not calculate radius from WCS, using default 1.0: %s", exc)
        radius = 1.0
    
    # Generate annotation
    logger.info("")
    logger.info("Starting annotation generation...")
    logger.info("  Source: %s", source_path)
    logger.info("  WCS: %s", wcs_path)
    logger.info("  Radius: %.4f degrees", radius)
    
    try:
        result_path = await annotator.generate_annotation(
            job_id, source_path, wcs_path, radius
        )
        
        # If custom output path specified, copy there
        if output_path and output_path != result_path:
            import shutil
            shutil.copy2(result_path, output_path)
            result_path = output_path
            logger.info("  Copied to: %s", output_path)
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ SUCCESS!")
        logger.info("=" * 60)
        logger.info("Annotated image generated: %s", result_path)
        logger.info("File size: %.2f MB", result_path.stat().st_size / 1024 / 1024)
        logger.info("")
        logger.info("You can view it at:")
        logger.info("  file://%s", result_path.absolute())
        logger.info("  http://127.0.0.1:8002/annotated_display/%s", job_id)
        logger.info("")
        
        return result_path
        
    except Exception as exc:  # noqa: BLE001
        logger.error("")
        logger.error("=" * 60)
        logger.error("❌ FAILED!")
        logger.error("=" * 60)
        logger.error("Error generating annotated image: %s", exc, exc_info=True)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Generate annotated image for a completed job (standalone)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate for job 8
  python scripts/generate_annotation_standalone.py --job-id 8
  
  # Generate with custom output
  python scripts/generate_annotation_standalone.py --job-id 8 --output /tmp/job8_annotated.jpg
  
  # Generate with custom source image
  python scripts/generate_annotation_standalone.py --job-id 8 --source data/uploads/my_image.jpg
        """
    )
    parser.add_argument("--job-id", type=int, required=True, help="Job ID to generate annotation for")
    parser.add_argument("--output", type=Path, help="Custom output path (optional)")
    parser.add_argument("--source", type=Path, help="Custom source image path (optional)")
    
    args = parser.parse_args()
    
    # If custom source provided, validate it exists
    if args.source:
        if not args.source.exists():
            logger.error("Source image not found: %s", args.source)
            sys.exit(1)
        logger.info("Using custom source image: %s", args.source)
    
    asyncio.run(generate_for_job(args.job_id, args.output, args.source))


if __name__ == "__main__":
    main()

