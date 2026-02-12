"""Render DOCX to PDF and OCR it to enrich checkbox/layout signals."""
from pathlib import Path
import tempfile
import subprocess

from yk_case_generation.models.document_ir import Source
from yk_case_generation.services.pdf_ocr import ocr_pdf


def render_docx_to_pdf_and_ocr(path: Path) -> Source:
    tmpdir = Path(tempfile.mkdtemp(prefix="ykcg_docx_"))
    pdf_path = render_docx_to_pdf(path, tmpdir)

    ocr_source = ocr_pdf(pdf_path)
    # differentiate source id to avoid collision with text channel
    ocr_source.source_id = path.stem + "_docx_pdfocr"
    return ocr_source


def render_docx_to_pdf(docx_path: Path, out_dir: Path | None = None) -> Path:
    out_dir = out_dir or docx_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / (docx_path.stem + ".pdf")

    cmd = [
        "libreoffice",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(out_dir),
        str(docx_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return pdf_path
