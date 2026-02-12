"""PDF OCR wrapper via Tencent OCR (per page)."""
from pathlib import Path
from typing import List

from yk_case_generation.models.document_ir import Source, Page, Line
from yk_case_generation.services.ocr_clients.tencent import TencentOCRClient
from yk_case_generation.config import settings


def ocr_pdf(pdf_path: Path) -> Source:
    client = TencentOCRClient(
        secret_id=settings.tencent_secret_id or "",
        secret_key=settings.tencent_secret_key or "",
        region=settings.ocr_region,
    )

    pages: List[Page] = []
    # Placeholder: currently not calling API; return error for visibility
    source = Source(
        source_id=pdf_path.stem,
        source_type="pdf",
        pages=[],
        error="ocr_not_implemented",
    )

    try:
        num_pages = 1  # TODO: derive from PDF metadata
        for page_no in range(1, num_pages + 1):
            # resp = client.ocr_pdf_page(pdf_path, page_no)
            # lines = _convert_response(resp)
            lines: List[Line] = []
            pages.append(Page(page_number=page_no, lines=lines))
        source.pages = pages
        source.error = "ocr_not_implemented"
    except Exception as exc:
        source.error = f"ocr_failed:{exc}"

    return source


# def _convert_response(resp) -> List[Line]:
#     ...
