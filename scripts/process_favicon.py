#!/usr/bin/env python3
"""Process favicon: crop outer 20% and resize to standard sizes."""

from pathlib import Path
from PIL import Image

PROJECT_ROOT = Path(__file__).parent.parent
FAVICON_SOURCE = PROJECT_ROOT / "favicon.png"
FAVICON_OUTPUT = PROJECT_ROOT / "frontend" / "public" / "favicon.png"
FAVICON_ICO = PROJECT_ROOT / "frontend" / "public" / "favicon.ico"

def process_favicon():
    """Crop outer 20% and resize favicon."""
    if not FAVICON_SOURCE.exists():
        print(f"Error: {FAVICON_SOURCE} not found")
        return
    
    # Open image
    img = Image.open(FAVICON_SOURCE)
    original_width, original_height = img.size
    print(f"Original size: {original_width}x{original_height}")
    
    # Crop outer 20% (keep center 80%)
    # Remove 10% from each side
    crop_x = int(original_width * 0.1)
    crop_y = int(original_height * 0.1)
    crop_width = int(original_width * 0.8)
    crop_height = int(original_height * 0.8)
    
    cropped = img.crop((crop_x, crop_y, crop_x + crop_width, crop_y + crop_height))
    print(f"Cropped size: {crop_width}x{crop_height}")
    
    # Resize to standard favicon sizes
    # Create multiple sizes for different use cases
    sizes = [
        (32, 32),   # Standard favicon
        (64, 64),   # High DPI
        (128, 128), # Apple touch icon
        (256, 256), # Large icon
    ]
    
    # Ensure output directory exists
    FAVICON_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    
    # Save PNG favicon (use 256x256 as main size)
    favicon_256 = cropped.resize((256, 256), Image.Resampling.LANCZOS)
    favicon_256.save(FAVICON_OUTPUT, "PNG", optimize=True)
    print(f"Saved PNG favicon: {FAVICON_OUTPUT}")
    
    # Save ICO file with multiple sizes
    ico_images = []
    for size in sizes:
        resized = cropped.resize(size, Image.Resampling.LANCZOS)
        ico_images.append(resized)
    
    # Save as ICO with multiple sizes
    ico_images[0].save(
        FAVICON_ICO,
        format="ICO",
        sizes=[(s[0], s[1]) for s in sizes],
        append_images=ico_images[1:] if len(ico_images) > 1 else None
    )
    print(f"Saved ICO favicon: {FAVICON_ICO}")
    
    # Print file sizes
    print("\nFile sizes:")
    print(f"  PNG: {FAVICON_OUTPUT.stat().st_size / 1024:.1f} KB")
    print(f"  ICO: {FAVICON_ICO.stat().st_size / 1024:.1f} KB")

if __name__ == "__main__":
    process_favicon()

