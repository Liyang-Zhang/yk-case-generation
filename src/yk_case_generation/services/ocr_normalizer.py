"""Normalize Tencent OCR JSON into IR Page/Line objects."""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import List, Tuple, Dict, Any

from yk_case_generation.models.document_ir import Line, Page

CHECKBOX_CHARS = set("□■☑☐√✓✗✘")


def load_ocr(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data


def extract_text_detections(data: dict) -> Tuple[List[dict], float | None]:
    resp = data.get("Response", data)
    lines = resp.get("TextDetections", [])
    angle = resp.get("Angle") or resp.get("Angel")
    return lines, angle


def polygon_to_bbox(poly: List[Dict[str, int]]) -> List[int] | None:
    if not poly:
        return None
    xs = [p["X"] for p in poly]
    ys = [p["Y"] for p in poly]
    return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]


def has_checkbox(text: str) -> bool:
    return any(ch in CHECKBOX_CHARS for ch in text)


def normalize_parag_no(advanced_info: str | None) -> int | None:
    if not advanced_info:
        return None
    try:
        obj = json.loads(advanced_info)
        parag = obj.get("Parag") or {}
        return parag.get("ParagNo")
    except Exception:
        return None


def detections_to_page(
    detections: List[dict],
    page_number: int | None,
    low_conf_thres: float = 0.6,
) -> Page:
    lines: List[Line] = []
    for idx, det in enumerate(detections, start=1):
        text = det.get("DetectedText", "")
        conf_raw = det.get("Confidence")
        confidence = None
        if conf_raw is not None:
            confidence = float(conf_raw) / 100.0
        polygon = det.get("Polygon") or []
        bbox = polygon_to_bbox(polygon)
        parag_no = normalize_parag_no(det.get("AdvancedInfo"))

        flags = {}
        if confidence is not None and confidence < low_conf_thres:
            flags["low_confidence"] = True
        if has_checkbox(text):
            flags["checkbox_like"] = True

        lines.append(
            Line(
                line_id=idx,
                text=text,
                confidence=confidence,
                polygon=polygon or None,
                bbox=bbox,
                parag_no=parag_no,
                flags=flags,
            )
        )
    return Page(page_number=page_number, lines=lines)
