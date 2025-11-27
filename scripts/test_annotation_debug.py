#!/usr/bin/env python3
"""
调试 annotated image 生成，检查为什么没有绘制标注
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import logging
from astropy.io import fits
from astropy.wcs import WCS
import numpy as np
from PIL import Image, ImageDraw

from core.config import settings

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def debug_annotation():
    job_id = 8
    job_dir = Path(f"data/jobs/{job_id}")
    wcs_path = job_dir / "wcs.fits"
    source_path = Path("data/uploads/abbe7ae6590f44e0b128847342c2f238_Orion_Nebula_-_Hubble_2006_mosaic_18000.jpg")
    
    if not source_path.exists():
        # Try to find source
        import glob
        sources = list(Path("data/uploads").glob(f"*job*{job_id}*")) + list(Path("data/uploads").glob("*Orion*"))
        if sources:
            source_path = sources[0]
            print(f"Using source: {source_path}")
        else:
            print("Source not found!")
            return
    
    print(f"Source: {source_path}")
    print(f"WCS: {wcs_path}")
    print(f"WCS exists: {wcs_path.exists()}")
    
    # Load image
    img = Image.open(source_path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    width, height = img.size
    print(f"Image size: {width}x{height}")
    
    # Load WCS
    with fits.open(wcs_path) as hdul:
        wcs = WCS(hdul[0].header)
    
    center = wcs.pixel_to_world(width / 2, height / 2)
    center_ra = center.ra.deg
    center_dec = center.dec.deg
    print(f"Image center: RA={center_ra:.4f}, Dec={center_dec:.4f}")
    
    # Calculate radius
    from astropy.wcs.utils import proj_plane_pixel_scales
    scales = proj_plane_pixel_scales(wcs)
    radius = max(float(scales[0] * width), float(scales[1] * height)) / 2
    print(f"Field radius: {radius:.4f} degrees")
    
    # Check catalogs
    cat_dir = settings.catalogs_dir
    bright_fn = cat_dir / "brightstars.fits"
    ngc_fn = cat_dir / "openngc-ngc.fits"
    
    print(f"\nCatalog files:")
    print(f"  brightstars.fits: {bright_fn.exists()} ({bright_fn})")
    print(f"  openngc-ngc.fits: {ngc_fn.exists()} ({ngc_fn})")
    
    # Test bright stars
    if bright_fn.exists():
        print(f"\n=== Testing Bright Stars ===")
        with fits.open(bright_fn) as hdul:
            data = hdul[1].data
            print(f"  Total stars: {len(data)}")
            print(f"  Columns: {data.dtype.names}")
            
            ra_col = None
            dec_col = None
            for col in ["RA", "ra", "DEC", "dec"]:
                if col in data.dtype.names:
                    if col.upper() == "RA":
                        ra_col = col
                    elif col.upper() == "DEC":
                        dec_col = col
            
            if ra_col and dec_col:
                ra = data[ra_col]
                dec = data[dec_col]
                print(f"  Using columns: RA={ra_col}, Dec={dec_col}")
                
                # Count stars in field
                count = 0
                in_field = []
                for i, (star_ra, star_dec) in enumerate(zip(ra[:1000], dec[:1000])):  # Check first 1000
                    ra_diff = abs(star_ra - center_ra)
                    if ra_diff > 180:
                        ra_diff = 360 - ra_diff
                    dec_diff = abs(star_dec - center_dec)
                    
                    if ra_diff**2 + dec_diff**2 <= (radius * 2)**2:
                        count += 1
                        try:
                            pixel = wcs.world_to_pixel_values(star_ra, star_dec)
                            x, y = float(pixel[0]), float(pixel[1])
                            if 0 <= x < width and 0 <= y < height:
                                in_field.append((x, y, star_ra, star_dec))
                        except Exception:
                            pass
                
                print(f"  Stars in field (first 1000 checked): {count}")
                print(f"  Stars within image bounds: {len(in_field)}")
                if in_field:
                    print(f"  First few stars:")
                    for x, y, ra, dec in in_field[:5]:
                        print(f"    RA={ra:.4f}, Dec={dec:.4f} -> pixel=({x:.1f}, {y:.1f})")
            else:
                print(f"  ERROR: Could not find RA/Dec columns!")
    
    # Test NGC objects
    if ngc_fn.exists() and radius < 10.0:
        print(f"\n=== Testing NGC Objects ===")
        with fits.open(ngc_fn) as hdul:
            data = hdul[1].data
            print(f"  Total NGC objects: {len(data)}")
            print(f"  Columns: {data.dtype.names}")
            
            if ("RA" in data.dtype.names or "ra" in data.dtype.names) and ("DEC" in data.dtype.names or "dec" in data.dtype.names):
                if "RA" in data.dtype.names:
                    ra = data["RA"]
                else:
                    ra = data["ra"]
                if "DEC" in data.dtype.names:
                    dec = data["DEC"]
                else:
                    dec = data["dec"]
                ra = data["RA"]
                dec = data["DEC"]
                
                count = 0
                in_field = []
                for obj_ra, obj_dec in zip(ra, dec):
                    ra_diff = abs(obj_ra - center_ra)
                    if ra_diff > 180:
                        ra_diff = 360 - ra_diff
                    dec_diff = abs(obj_dec - center_dec)
                    
                    if ra_diff**2 + dec_diff**2 <= (radius * 2)**2:
                        count += 1
                        try:
                            pixel = wcs.world_to_pixel_values(obj_ra, obj_dec)
                            x, y = float(pixel[0]), float(pixel[1])
                            if 0 <= x < width and 0 <= y < height:
                                in_field.append((x, y))
                        except Exception:
                            pass
                
                print(f"  NGC objects in field: {count}")
                print(f"  NGC objects within image bounds: {len(in_field)}")
            else:
                print(f"  ERROR: Could not find RA/Dec columns!")
    
    # Now try to actually draw
    print(f"\n=== Drawing Test ===")
    draw = ImageDraw.Draw(img)
    
    if bright_fn.exists() and ra_col and dec_col:
        with fits.open(bright_fn) as hdul:
            data = hdul[1].data
            ra = data[ra_col]
            dec = data[dec_col]
            if "vmag" in data.dtype.names:
                mag = data["vmag"]
            elif "VMAG" in data.dtype.names:
                mag = data["VMAG"]
            else:
                mag = np.ones(len(ra)) * 5.0
            
            drawn = 0
            for star_ra, star_dec, star_mag in zip(ra, dec, mag):
                try:
                    ra_diff = abs(star_ra - center_ra)
                    if ra_diff > 180:
                        ra_diff = 360 - ra_diff
                    dec_diff = abs(star_dec - center_dec)
                    
                    if ra_diff**2 + dec_diff**2 > (radius * 2)**2:
                        continue
                    
                    pixel = wcs.world_to_pixel_values(star_ra, star_dec)
                    x, y = float(pixel[0]), float(pixel[1])
                    
                    if 0 <= x < width and 0 <= y < height:
                        size = max(1, int(6 - star_mag))
                        draw.ellipse([x - size, y - size, x + size, y + size], 
                                    fill=(255, 255, 200), outline=(255, 255, 150))
                        drawn += 1
                        if drawn >= 100:  # Limit to first 100 for testing
                            break
                except Exception as e:
                    continue
            
            print(f"  Drew {drawn} stars")
    
    # Save test image
    output = job_dir / "annotated_test.jpg"
    img.save(output, "JPEG", quality=95)
    print(f"\nTest image saved to: {output}")
    print(f"File size: {output.stat().st_size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    asyncio.run(debug_annotation())

