"""Prepare attachments into OCR-ready images."""
from pathlib import Path
from typing import List, Tuple
import tempfile
import shutil

from yk_case_generation.services.docx_render import render_docx_to_pdf
from yk_case_generation.services.pdf_render import pdf_to_images
from yk_case_generation.services.image_preprocess import preprocess_image

ImageInfo = Tuple[int, Path]  # (page_number, image_path)


def prepare_images_for_ocr(path: Path) -> List[ImageInfo]:
    """Convert attachment to preprocessed images ready for OCR."""
    ext = path.suffix.lower()
    raw_images: List[Tuple[int, Path]] = []

    if ext == ".docx":
        pdf_path = render_docx_to_pdf(path, Path(tempfile.mkdtemp(prefix="ykcg_docxpdf_")))
        imgs = pdf_to_images(pdf_path)
        raw_images = list(enumerate(imgs, start=1))
    elif ext == ".pdf":
        imgs = pdf_to_images(path)
        raw_images = list(enumerate(imgs, start=1))
    elif ext in {".png", ".jpg", ".jpeg"}:
        raw_images = [(1, path)]
    else:
        # unsupported format for now
        return []

    processed: List[ImageInfo] = []
    for page_no, img_path in raw_images:
        pre = preprocess_image(img_path)
        processed.append((page_no, pre))
    return processed
