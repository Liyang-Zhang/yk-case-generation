"""Extractor stage: gather text from LIMS and attachments into a Document IR."""
from pathlib import Path
from typing import List, Union
import tempfile
import httpx

from yk_case_generation.models.document_ir import DocumentIR, Source, Page, Line
from yk_case_generation.services.docx_parser import parse_docx
from yk_case_generation.services.docx_render import render_docx_to_pdf_and_ocr

AttachmentInput = Union[Path, str]


def extract_sources(case_id: str, lims_texts: List[str], attachments: List[AttachmentInput]) -> DocumentIR:
    """Build DocumentIR from LIMS texts and assorted attachments (local paths or URLs)."""
    sources: List[Source] = []

    # LIMS texts (trusted, confidence=1.0)
    for idx, text in enumerate(lims_texts, start=1):
        line = Line(line_id=0, text=text, confidence=1.0)
        page = Page(page_number=None, lines=[line])
        source = Source(source_id=f"lims_text_{idx}", source_type="lims_text", pages=[page])
        sources.append(source)

    # Attachments
    for attachment in attachments:
        try:
            local_path = _materialize_attachment(attachment)
        except Exception as exc:  # capture download or path errors
            source_id = _source_id_from_input(attachment)
            sources.append(
                Source(
                    source_id=source_id,
                    source_type=_guess_type(Path(source_id)),
                    pages=[],
                    error=f"fetch_failed: {exc}",
                )
            )
            continue

        source_type = _guess_type(local_path)
        try:
            if source_type == "docx":
                # channel A: docx text
                sources.append(parse_docx(local_path))
                # channel B: docx->pdf->ocr
                ocr_source = render_docx_to_pdf_and_ocr(local_path)
                sources.append(ocr_source)
                continue
            else:
                source = Source(
                    source_id=local_path.stem,
                    source_type=source_type,
                    pages=[],
                    error="not_implemented",
                )
        except Exception as exc:  # parsing failures
            source = Source(
                source_id=local_path.stem, source_type=source_type, pages=[], error=f"parse_failed: {exc}"
            )

        sources.append(source)

    return DocumentIR(case_id=case_id, sources=sources)


def _guess_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return "pdf"
    if ext == ".png":
        return "png"
    if ext in {".jpg", ".jpeg"}:
        return "jpg"
    if ext == ".docx":
        return "docx"
    return "unknown"


def _materialize_attachment(attachment: AttachmentInput) -> Path:
    """Return a local Path for the attachment; download if given a URL."""
    if isinstance(attachment, Path):
        if not attachment.exists():
            raise FileNotFoundError(f"{attachment} does not exist")
        return attachment

    # str input
    att_str = str(attachment)
    if att_str.startswith("http://") or att_str.startswith("https://"):
        return _download_to_temp(att_str)

    path = Path(att_str)
    if not path.exists():
        raise FileNotFoundError(f"{att_str} does not exist")
    return path


def _download_to_temp(url: str) -> Path:
    filename = url.split("/")[-1] or "attachment"
    tmp_dir = Path(tempfile.mkdtemp(prefix="ykcg_"))
    target = tmp_dir / filename
    with httpx.stream("GET", url, timeout=30) as resp:
        resp.raise_for_status()
        with open(target, "wb") as f:
            for chunk in resp.iter_bytes():
                f.write(chunk)
    return target


def _source_id_from_input(attachment: AttachmentInput) -> str:
    if isinstance(attachment, Path):
        return attachment.stem
    return Path(str(attachment)).stem or "attachment"
