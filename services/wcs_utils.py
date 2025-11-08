from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from astropy.io import fits
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_scales


@dataclass
class SolverMetadata:
    orientation: Optional[float]
    parity: Optional[str]
    objects: list[str]


def parse_solver_stdout(output: str) -> SolverMetadata:
    orientation: Optional[float] = None
    parity: Optional[str] = None
    objects: list[str] = []
    capture_objects = False

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if line.startswith("Field rotation angle:"):
            try:
                segment = line.split("up is", 1)[1]
                orientation = float(segment.split("degrees", 1)[0].strip())
            except (IndexError, ValueError):
                continue
        elif line.startswith("Field parity:"):
            parity = line.split(":", 1)[1].strip()
        elif line.startswith("Your field contains:"):
            capture_objects = True
            continue
        elif capture_objects:
            if not raw_line.startswith("  ") or not line:
                capture_objects = False
                continue
            objects.append(line.lstrip("- "))

    return SolverMetadata(orientation=orientation, parity=parity, objects=objects)


def extract_calibration(new_fits: Path, wcs_fits: Path, orientation: Optional[float], parity: Optional[str]) -> dict:
    """Read the FITS header to compute calibration info."""
    target = new_fits if new_fits.exists() else wcs_fits
    if not target.exists():
        raise FileNotFoundError(target)

    with fits.open(target) as hdul:
        header = hdul[0].header
        imagew = header.get("NAXIS1")
        imageh = header.get("NAXIS2")
        if imagew is None or imageh is None:
            raise ValueError("Missing NAXIS dimensions in FITS header")
        wcs = WCS(header)
        center = wcs.pixel_to_world(imagew / 2, imageh / 2)
        scales = proj_plane_pixel_scales(wcs)  # degrees per pixel
        width_deg = float(scales[0] * imagew)
        height_deg = float(scales[1] * imageh)
        radius = max(width_deg, height_deg) / 2
        pixscale_arcsec = float(scales.mean() * 3600)

    return {
        "ra": float(center.ra.deg),
        "dec": float(center.dec.deg),
        "width_arcsec": width_deg * 3600,
        "height_arcsec": height_deg * 3600,
        "radius": radius,
        "pixscale": pixscale_arcsec,
        "orientation": orientation,
        "parity": parity,
    }
