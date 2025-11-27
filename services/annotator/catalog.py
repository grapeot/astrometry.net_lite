"""Catalog management for celestial objects."""

from __future__ import annotations

import csv
import logging
import re
from pathlib import Path
from typing import NamedTuple

import numpy as np
from astropy.wcs import WCS

logger = logging.getLogger(__name__)


class CelestialObject(NamedTuple):
    """Represents a celestial object from the catalog."""
    name: str
    ra: float
    dec: float
    ang_diameter: float | None  # arcmin, None if not available


def get_catalog_priority(name: str) -> int:
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


def are_objects_duplicate(obj1: CelestialObject, obj2: CelestialObject, duplicate_threshold_deg: float = 0.1) -> bool:
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


def deduplicate_objects(objects: list[CelestialObject], duplicate_threshold_deg: float = 0.1) -> list[CelestialObject]:
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
        priority = get_catalog_priority(obj.name)
        return (has_radius, priority)
    
    sorted_objects = sorted(objects, key=sort_key)
    
    # Remove duplicates, keeping first occurrence (highest priority)
    deduplicated = []
    for obj in sorted_objects:
        is_duplicate = False
        for kept_obj in deduplicated:
            if are_objects_duplicate(obj, kept_obj, duplicate_threshold_deg):
                is_duplicate = True
                logger.debug("Removing duplicate: %s (kept: %s)", obj.name, kept_obj.name)
                break
        if not is_duplicate:
            deduplicated.append(obj)
    
    return deduplicated


def load_catalog_csv(catalog_path: Path) -> list[CelestialObject]:
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


def get_field_corners(wcs: WCS, width: int, height: int) -> tuple[float, float, float, float]:
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


def filter_objects_in_field(objects: list[CelestialObject], min_ra: float, max_ra: float, min_dec: float, max_dec: float) -> list[CelestialObject]:
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


def get_object_type(name: str) -> str:
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


def get_object_color(obj_type: str) -> tuple[int, int, int]:
    """Get color for object type (aesthetic colors, not bright red/green)."""
    colors = {
        "messier": (255, 200, 100),      # Warm gold
        "ngc_ic": (150, 200, 255),       # Soft blue
        "nebula": (200, 150, 255),       # Lavender
        "cluster": (255, 180, 150),      # Peach
        "unknown": (200, 200, 200),      # Light gray
    }
    return colors.get(obj_type, colors["unknown"])

