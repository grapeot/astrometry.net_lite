from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from services.storage import prepare_job_dir


def generate_placeholder_annotation(job_id: int, source_path: Path) -> Path:
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
