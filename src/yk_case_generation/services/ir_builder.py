"""Build normalized IR from OCR results and LIMS texts."""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional

from yk_case_generation.models.document_ir import DocumentIR, Source, Page, Line
from yk_case_generation.services.ocr_normalizer import load_ocr, extract_text_detections, detections_to_page

CHECKED_CHARS = set("☑✓√■")
UNCHECKED_CHARS = set("□☐")
FORM_TEMPLATE_KEYWORDS = (
    "请在相应的",
    "知情同意书",
    "送检单",
    "检测项目",
    "样本类型",
    "受检者确认",
    "医师确认",
    "受检者陈述",
    "医师陈述",
)


def build_ir(document_ir: DocumentIR) -> DocumentIR:
    """Compatibility wrapper for legacy CLI path."""
    return document_ir

def _normalize_text_hash(text: str) -> str:
    norm = re.sub(r"\s+", "", text)
    norm = re.sub(r"[，。,:;；、.!？!?（）()\\[\\]{}<>《》\"'`~·-]", "", norm)
    return norm.lower()


def build_ir_for_project(
    case_id: str,
    raw_json: Path,
    ocr_results_dir: Path,
    ocr_inputs_dir: Path,
    low_conf_thres: float = 0.6,
    boilerplate_repeat: int = 3,
) -> DocumentIR:
    sources: List[Source] = []

    # LIMS texts
    raw = json.loads(raw_json.read_text(encoding="utf-8"))
    lims_texts = [
        raw.get("salesNotes", ""),
        raw.get("otherInfo", ""),
        raw.get("communicationInformation", ""),
    ]
    for idx, text in enumerate(lims_texts, start=1):
        line = Line(line_id=1, text=text, confidence=1.0)
        page = Page(page_number=None, lines=[line])
        sources.append(Source(source_id=f"lims_text_{idx}", source_type="lims_text", pages=[page]))

    # OCR Sources
    # map from source_id to list of pages
    source_pages: Dict[str, List[Page]] = {}

    for ocr_file in ocr_results_dir.glob("*.json"):
        stem = ocr_file.stem  # e.g., 张程杰20241214162857896_p1
        if "_p" not in stem:
            continue
        attach_stem, page_str = stem.rsplit("_p", 1)
        try:
            page_no = int(page_str)
        except ValueError:
            page_no = None

        # find project by matching image path in ocr_inputs_dir
        img_matches = list(ocr_inputs_dir.glob(f"**/{stem}.jpg"))
        if not img_matches:
            continue
        project_id = img_matches[0].parent.name
        if project_id != case_id:
            continue

        ocr_data = load_ocr(ocr_file)
        detections, _ = extract_text_detections(ocr_data)
        page = detections_to_page(detections, page_no, low_conf_thres)

        source_id = f"{project_id}/{attach_stem}"
        source_pages.setdefault(source_id, []).append(page)

    # add sources
    for sid, pages in source_pages.items():
        pages_sorted = sorted(pages, key=lambda p: (p.page_number or 0))
        sources.append(
            Source(
                source_id=sid,
                source_type="ocr_attachment",
                pages=pages_sorted,
                error=None,
            )
        )

    doc = DocumentIR(case_id=case_id, sources=sources)
    _annotate_template_and_checkbox(doc)
    _mark_boilerplate(doc, boilerplate_repeat)
    return doc


def _mark_boilerplate(doc: DocumentIR, repeat_thres: int):
    counts: Dict[str, int] = {}
    line_refs: List[Tuple[str, Line]] = []
    for src in doc.sources:
        for page in src.pages:
            for line in page.lines:
                h = _normalize_text_hash(line.text)
                if not h:
                    continue
                counts[h] = counts.get(h, 0) + 1
                line_refs.append((h, line))
    for h, line in line_refs:
        if counts.get(h, 0) >= repeat_thres:
            line.flags["boilerplate"] = True


def _annotate_template_and_checkbox(doc: DocumentIR):
    for src in doc.sources:
        if src.source_type != "ocr_attachment":
            continue
        for page in src.pages:
            _annotate_page(page)


def _annotate_page(page: Page):
    if not page.lines:
        return

    checkbox_like_count = 0
    symbol_only_lines: List[Line] = []
    text_lines: List[Line] = []

    for line in page.lines:
        text = (line.text or "").strip()
        state = _extract_checkbox_state(text)
        if state:
            line.flags["checkbox_option"] = True
            line.flags["checkbox_state"] = state
            checkbox_like_count += 1
            if _is_symbol_only(text):
                symbol_only_lines.append(line)
            else:
                text_lines.append(line)
        else:
            text_lines.append(line)

    # If OCR split symbol and label into separate lines, attach state to nearest text line.
    for symbol_line in symbol_only_lines:
        target = _nearest_text_line(symbol_line, text_lines)
        if target:
            target.flags["checkbox_option"] = True
            target.flags["checkbox_state"] = symbol_line.flags.get("checkbox_state", "unknown")
            target.flags["checkbox_linked_from_line_id"] = symbol_line.line_id

    is_form_page = checkbox_like_count >= 4
    for line in page.lines:
        text = (line.text or "").strip()
        if _contains_form_template_keyword(text) or is_form_page:
            line.flags["form_template"] = True


def _extract_checkbox_state(text: str) -> Optional[str]:
    if not text:
        return None
    if any(ch in text for ch in CHECKED_CHARS):
        return "checked"
    if any(ch in text for ch in UNCHECKED_CHARS):
        return "unchecked"
    return None


def _contains_form_template_keyword(text: str) -> bool:
    return any(k in text for k in FORM_TEMPLATE_KEYWORDS)


def _is_symbol_only(text: str) -> bool:
    stripped = re.sub(r"\s+", "", text)
    return bool(stripped) and all(ch in CHECKED_CHARS.union(UNCHECKED_CHARS) for ch in stripped)


def _line_center(line: Line) -> Optional[Tuple[float, float]]:
    if not line.bbox or len(line.bbox) != 4:
        return None
    x, y, w, h = line.bbox
    return (x + (w / 2.0), y + (h / 2.0))


def _nearest_text_line(source_line: Line, candidates: List[Line]) -> Optional[Line]:
    source_center = _line_center(source_line)
    if not source_center:
        return None
    sx, sy = source_center
    nearest: Optional[Line] = None
    best_dist = float("inf")
    for candidate in candidates:
        c_center = _line_center(candidate)
        if not c_center:
            continue
        cx, cy = c_center
        # weighted distance: prioritize same-row proximity
        dist = abs(cy - sy) * 1.2 + abs(cx - sx)
        if dist < best_dist:
            best_dist = dist
            nearest = candidate
    return nearest
