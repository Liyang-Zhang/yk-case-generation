"""Render PDF pages to images for OCR."""
from pathlib import Path
from typing import List
import tempfile
from pdf2image import convert_from_path


def pdf_to_images(pdf_path: Path, dpi: int = 300, fmt: str = "jpeg") -> List[Path]:
    """Render each page to an image file; returns list of image paths in order."""
    tmpdir = Path(tempfile.mkdtemp(prefix="ykcg_pdfimgs_"))
    pages = convert_from_path(str(pdf_path), dpi=dpi, fmt=fmt)
    img_paths: List[Path] = []
    for idx, img in enumerate(pages, start=1):
        out_path = tmpdir / f"{pdf_path.stem}_p{idx}.{fmt}"
        img.save(out_path, fmt.upper())
        img_paths.append(out_path)
    return img_paths
