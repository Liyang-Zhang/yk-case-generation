"""Build frontend-facing case response from internal case JSON."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from jsonschema import validate


DEFAULT_RESPONSE_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "case_response_v1.json"

_FRONTEND_SECTIONS = (
    "patient_info",
    "chief_complaint",
    "medical_history",
    "family_history",
    "diagnosis",
    "tests_and_exams",
)


def build_case_response(case: Dict[str, Any], schema_path: str | None = None) -> Dict[str, Any]:
    narrative = _build_narrative(case)
    response = {
        "schema_version": "case_response_v1",
        "case_id": case.get("case_id", ""),
        "status": _compute_status(case),
        "summary": _build_summary(case, narrative),
        "narrative": narrative,
        "sections": {k: _to_front_facts(case.get(k, [])) for k in _FRONTEND_SECTIONS},
        "quality": {
            "warnings": list(case.get("quality", {}).get("warnings", [])),
            "missing_critical": list(case.get("quality", {}).get("missing_critical", [])),
        },
    }
    schema = _load_schema(schema_path)
    validate(instance=response, schema=schema)
    return response


def _to_front_facts(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in items:
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        evidence = list(item.get("evidence", []))
        out.append(
            {
                "text": text,
                "polarity": item.get("polarity", "unknown"),
                "confidence_level": _estimate_confidence(item),
                "evidence": evidence,
            }
        )
    return out


def _estimate_confidence(item: Dict[str, Any]) -> str:
    if item.get("polarity") == "unknown":
        return "low"
    evidence = item.get("evidence", [])
    if any(str(ev.get("source_id", "")).startswith("lims_text_") for ev in evidence):
        return "high"
    if evidence:
        return "medium"
    return "low"


def _compute_status(case: Dict[str, Any]) -> str:
    warnings = case.get("quality", {}).get("warnings", [])
    missing = case.get("quality", {}).get("missing_critical", [])
    has_core = any(case.get(k) for k in ("chief_complaint", "medical_history", "diagnosis"))
    has_any_medical = has_core or bool(case.get("tests_and_exams"))
    if not has_any_medical:
        return "failed"
    if has_core and not (warnings or missing):
        return "ok"
    if warnings or missing or bool(case.get("tests_and_exams")):
        return "partial"
    return "partial"


def _build_summary(case: Dict[str, Any], narrative: str) -> str:
    if narrative and narrative != "未提取到明确病例要点，请结合原始证据复核。":
        if "。" in narrative:
            first = narrative.split("。", 1)[0].strip()
            return first if first else narrative
        return narrative
    return "未提取到明确病例要点，请结合原始证据复核。"


def _build_narrative(case: Dict[str, Any]) -> str:
    parts: List[str] = []

    patient_info = _select_top_texts(case.get("patient_info", []), max_items=2)
    if patient_info:
        parts.append(f"患者信息：{'；'.join(patient_info)}。")

    chief = _select_top_texts(case.get("chief_complaint", []), max_items=1)
    if chief:
        parts.append(f"主诉：{chief[0]}。")

    history = _select_top_texts(case.get("medical_history", []), max_items=3, prefer_clinical=True)
    if history:
        parts.append(f"病史：{'；'.join(history)}。")

    family = _select_top_texts(case.get("family_history", []), max_items=2)
    if family:
        parts.append(f"家族史：{'；'.join(family)}。")

    diagnosis = _select_top_texts(case.get("diagnosis", []), max_items=2)
    if diagnosis:
        parts.append(f"诊断：{'；'.join(diagnosis)}。")

    exams = _select_top_texts(case.get("tests_and_exams", []), max_items=2, prefer_results=True)
    if exams:
        parts.append(f"检查结果：{'；'.join(exams)}。")

    if not parts:
        return "未提取到明确病例要点，请结合原始证据复核。"
    return "".join(parts)


def _select_top_texts(
    items: List[Dict[str, Any]],
    max_items: int = 2,
    prefer_clinical: bool = False,
    prefer_results: bool = False,
) -> List[str]:
    texts: List[str] = []
    seen: set[str] = set()
    scored: List[tuple[int, str]] = []

    for item in items:
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        norm = text.replace(" ", "")
        if norm in seen:
            continue
        seen.add(norm)
        score = 0

        if prefer_clinical:
            if any(k in text for k in ("IVF", "ICSI", "未着床", "症状", "临床表现", "病史", "发育")):
                score += 3
            if any(k in text for k in ("先证者", "配偶", "项目")):
                score -= 2

        if prefer_results:
            if any(k in text for k in ("阳性", "阴性", "指数", "%", "异常", "升高", "降低", "未见")):
                score += 3
            if any(k in text for k in ("检测项目", "套餐", "测序")):
                score -= 3

        if len(text) <= 3:
            score -= 2

        scored.append((score, text))

    scored.sort(key=lambda x: x[0], reverse=True)
    for _, text in scored[:max_items]:
        texts.append(text)
    return texts


def _load_schema(path: str | None = None) -> Dict[str, Any]:
    schema_path = Path(path) if path else DEFAULT_RESPONSE_SCHEMA_PATH
    return json.loads(schema_path.read_text(encoding="utf-8"))
