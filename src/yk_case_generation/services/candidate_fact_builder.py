"""Build high-signal candidate facts from normalized IR for LLM extraction."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from yk_case_generation.models.document_ir import DocumentIR, Line, Source, Page

_FORM_NOISE_KEYWORDS = (
    "版本号",
    "识别码",
    "官网",
    "地址",
    "电话",
    "本知材料一式三联",
    "请在相应的",
    "知情同意书",
)

# 检测项目/套餐类关键词（与患者症状无关，需过滤掉）
_DETECTION_NOISE_KEYWORDS = (
    "检测项目",
    "送检项目",
    "套餐",
    "全外显子",
    "外显子",
    "携带者",
    "Panel",
    "WES",
    "NGS",
    "测序",
    "核型",
    "染色体",
    "样本类型",
    "采样日期",
    "收样",
    "建库",
    "捕获",
    "上机",
    "深度",
)

_MEDICAL_SIGNAL_KEYWORDS = (
    "临床诊断",
    "病历",
    "主诉",
    "既往史",
    "家族史",
    "检测",
    "检查",
    "染色体",
    "核型",
    "样本",
    "阳性",
    "阴性",
    "未见",
    "否认",
    "无",
    "IVF",
    "ICSI",
)

_PATIENT_SIGNAL_KEYWORDS = (
    "姓名",
    "年龄",
    "性别",
    "联系电话",
    "病历号",
    "病历ID",
)

_SECTION_HINTS = {
    "diagnosis": ("临床诊断", "诊断", "疾病"),
    "medical_history": ("主诉", "现病史", "病史", "IVF", "ICSI", "症状", "表现"),
    "family_history": ("家族史",),
    "tests_and_exams": ("检测", "检查", "核型", "染色体", "样本", "阳性", "阴性"),
    "plan": ("建议", "随访", "复查", "计划", "报告比对"),
    "patient_info": _PATIENT_SIGNAL_KEYWORDS,
}

_ANCHOR_HINTS = {
    "diagnosis": ("临床诊断", "诊断", "病例", "病历", "结论"),
    "chief_complaint": ("主诉", "送检原因", "就诊原因"),
    "medical_history": ("现病史", "病史", "临床表现", "症状"),
    "family_history": ("家族史",),
    "tests_and_exams": ("检查", "检测", "核型", "染色体", "样本", "结果"),
    "plan": ("建议", "随访", "复查", "方案", "治疗"),
}


def build_candidate_facts(document_ir: DocumentIR) -> List[Dict[str, Any]]:
    facts: List[Dict[str, Any]] = []
    dedup_seen: set[str] = set()

    for source in document_ir.sources:
        # LIMS text is high-signal and should keep full recall.
        if source.source_type == "lims_text":
            for page in source.pages:
                for line in page.lines:
                    text = (line.text or "").strip()
                    if not text:
                        continue
                    key = _dedup_key(source, page.page_number, text)
                    if key in dedup_seen:
                        continue
                    dedup_seen.add(key)
                    facts.append(
                        {
                            "source_id": source.source_id,
                            "page": page.page_number,
                            "line_id": line.line_id,
                            "quote": text,
                            "priority": "high",
                            "section_hints": _section_hints(text),
                            "flags": line.flags or {},
                        }
                    )
            continue

        # For OCR sources, anchor-neighborhood candidates are preferred.
        anchor_candidates = _build_anchor_neighborhood_candidates(source)
        for item in anchor_candidates:
            key = _dedup_key_raw(item["source_id"], item["page"], item["quote"])
            if key in dedup_seen:
                continue
            dedup_seen.add(key)
            facts.append(item)

        for page in source.pages:
            for line in page.lines:
                text = (line.text or "").strip()
                if not text:
                    continue
                if not _keep_line(source, line, text):
                    continue

                key = _dedup_key(source, page.page_number, text)
                if key in dedup_seen:
                    continue
                dedup_seen.add(key)

                facts.append(
                    {
                        "source_id": source.source_id,
                        "page": page.page_number,
                        "line_id": line.line_id,
                        "quote": text,
                        "priority": "normal",
                        "section_hints": _section_hints(text),
                        "flags": line.flags or {},
                    }
                )

    return facts


def _keep_line(source: Source, line: Line, text: str) -> bool:
    flags = line.flags or {}
    if flags.get("form_template") and flags.get("checkbox_state") == "unchecked":
        return False
    if flags.get("boilerplate"):
        return False

    # OCR 将空框识别为“口/日/□”等符号时，视为未勾选模板项
    if re.fullmatch(r"[口日曰□■]+", text) and len(text) <= 3:
        return False

    # 纯检测项目/套餐等与表型无关的信息，直接过滤
    if _is_detection_noise(text):
        return False

    if _contains_any(text, _FORM_NOISE_KEYWORDS) and "☑" not in text and "√" not in text:
        return False

    if flags.get("checkbox_state") == "checked":
        return True
    if _contains_any(text, _PATIENT_SIGNAL_KEYWORDS):
        return True
    if _contains_any(text, _MEDICAL_SIGNAL_KEYWORDS):
        return True

    # Keep concise factual lines with clear numeric/diagnostic signal.
    if len(text) <= 40 and re.search(r"[0-9]", text):
        return True
    return False


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(k in text for k in keywords)


def _section_hints(text: str) -> List[str]:
    hints: List[str] = []
    for section, words in _SECTION_HINTS.items():
        if _contains_any(text, words):
            hints.append(section)
    if not hints:
        hints.append("tests_and_exams")
    return hints


def _dedup_key(source: Source, page: int | None, text: str) -> str:
    norm = re.sub(r"\s+", "", text).lower()
    return f"{source.source_id}:{page}:{norm}"


def _dedup_key_raw(source_id: str, page: int | None, text: str) -> str:
    norm = re.sub(r"\s+", "", text).lower()
    return f"{source_id}:{page}:{norm}"


def _build_anchor_neighborhood_candidates(source: Source) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for page in source.pages:
        anchors = _find_page_anchors(page)
        if not anchors:
            continue
        vertical_mode = _is_vertical_page(page)
        for section, anchor_line in anchors:
            neighbors = _find_neighbors(page, anchor_line, vertical_mode)
            for line in neighbors:
                text = (line.text or "").strip()
                if not text:
                    continue
                if _is_detection_noise(text):
                    continue
                if not _keep_line(source, line, text):
                    continue
                hints = _section_hints(text)
                if section not in hints:
                    hints = [section] + hints
                out.append(
                    {
                        "source_id": source.source_id,
                        "page": page.page_number,
                        "line_id": line.line_id,
                        "quote": text,
                        "priority": "high",
                        "section_hints": hints,
                        "flags": line.flags or {},
                    }
                )
    return out


def _find_page_anchors(page: Page) -> List[Tuple[str, Line]]:
    anchors: List[Tuple[str, Line]] = []
    for line in page.lines:
        text = (line.text or "").strip()
        if not text:
            continue
        for section, keys in _ANCHOR_HINTS.items():
            if any(k in text for k in keys):
                anchors.append((section, line))
                break
    return anchors


def _is_vertical_page(page: Page) -> bool:
    # In vertical OCR, most lines have taller bbox than width.
    ratios: List[float] = []
    for line in page.lines:
        if line.bbox and len(line.bbox) == 4:
            w = max(1, line.bbox[2])
            h = max(1, line.bbox[3])
            ratios.append(h / w)
    if not ratios:
        return False
    ratios.sort()
    median = ratios[len(ratios) // 2]
    return median > 1.2


def _is_detection_noise(text: str) -> bool:
    # 如果同时含有诊断/病史关键词，则视为有临床价值，不算噪声。
    if _contains_any(text, _ANCHOR_HINTS["diagnosis"]) or _contains_any(text, _ANCHOR_HINTS.get("medical_history", ())):
        return False
    return _contains_any(text, _DETECTION_NOISE_KEYWORDS)


def _find_neighbors(page: Page, anchor: Line, vertical_mode: bool) -> List[Line]:
    anchor_center = _line_center(anchor)
    if anchor_center is None:
        return []
    ax, ay = anchor_center

    scored: List[Tuple[float, Line]] = []
    for line in page.lines:
        if line.line_id == anchor.line_id:
            continue
        center = _line_center(line)
        if center is None:
            continue
        cx, cy = center
        dx = abs(cx - ax)
        dy = abs(cy - ay)

        if vertical_mode:
            if dx > 130 or dy > 800:
                continue
            score = dx * 2.0 + dy * 0.7
        else:
            if dy > 90 or dx > 900:
                continue
            score = dy * 2.0 + dx * 0.7

        scored.append((score, line))

    scored.sort(key=lambda x: x[0])
    return [line for _, line in scored[:12]]


def _line_center(line: Line) -> Optional[Tuple[float, float]]:
    if not line.bbox or len(line.bbox) != 4:
        return None
    x, y, w, h = line.bbox
    return x + (w / 2.0), y + (h / 2.0)
