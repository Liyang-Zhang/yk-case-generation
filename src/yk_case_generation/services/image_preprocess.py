"""Image preprocessing before OCR."""
from pathlib import Path
from typing import Tuple
import tempfile
from PIL import Image, ImageEnhance


def preprocess_image(
    img_path: Path,
    max_dim: int = 2048,
    max_bytes: int = 5_000_000,
    quality: int = 85,
) -> Path:
    """
    - Resize keeping aspect ratio so longer edge <= max_dim.
    - Convert to RGB and apply mild contrast enhancement.
    - Save as JPEG with quality, ensuring size under max_bytes (iteratively reduce quality if needed).
    Returns path to processed image.
    """
    img = Image.open(img_path)
    img = img.convert("RGB")

    w, h = img.size
    scale = min(1.0, max_dim / max(w, h)) if max(w, h) > max_dim else 1.0
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    # Mild contrast boost
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.1)

    out_dir = Path(tempfile.mkdtemp(prefix="ykcg_pre_"))
    out_path = out_dir / (img_path.stem + ".jpg")

    q = quality
    while True:
        img.save(out_path, "JPEG", quality=q, optimize=True)
        if out_path.stat().st_size <= max_bytes or q <= 40:
            break
        q = int(q * 0.8)
    return out_path
