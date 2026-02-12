"""Case builder for MVP: rule-based extraction + optional LLM mode."""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any, Dict, List

from jsonschema import validate, ValidationError

from yk_case_generation.config import settings
from yk_case_generation.models.document_ir import DocumentIR, Source, Line
from yk_case_generation.models.case_schema import load_schema
from yk_case_generation.services.candidate_fact_builder import build_candidate_facts
from yk_case_generation.services.llm_client import LLMClient

_NEGATION_HINTS = ("否认", "未见", "无明显", "无异常", "未发现", "未提示", "没有", "阴性")
_DIAGNOSIS_HINTS = ("诊断", "临床诊断", "病历", "疾病")
_EXAM_HINTS = ("检查", "检测", "核型", "染色体", "样本")
_HISTORY_HINTS = ("既往史", "病史", "家族史")
# 最终输出中不下发表单选项/检测套餐等无关内容；tests_and_exams 仍可留作内部调试但不会暴露给业务端
_DISALLOW_SECTIONS = {"diagnosis", "tests_and_exams"}
_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


def generate_case(
    document_ir: DocumentIR,
    schema_path: str | None = None,
    mode: str | None = None,
) -> Dict[str, Any]:
    schema = load_schema(schema_path)
    run_mode = (mode or settings.llm_mode).lower()
    if run_mode == "llm":
        case = _generate_with_llm(document_ir, schema)
    elif run_mode == "rule":
        case = _generate_with_rules(document_ir)
    else:
        raise ValueError(f"Unknown case builder mode: {run_mode}")

    _validate_case(case, schema)
    return case


def _generate_with_rules(document_ir: DocumentIR) -> Dict[str, Any]:
    case = _empty_case(document_ir.case_id)
    lines = _iter_meaningful_lines(document_ir.sources)
    for item in lines:
        text = item["line"].text.strip()
        if not _line_allowed_for_fact(item["line"]):
            continue
        lowered = text.lower()
        polarity = _detect_polarity(text, lowered)
        fact = {
            "text": text,
            "polarity": polarity,
            "evidence": [_to_evidence(item["source"], item["page"], item["line"])],
        }

        # Priority bucket routing for MVP
        if _contains_any(text, _DIAGNOSIS_HINTS) and _line_allowed_for_diagnosis(item["line"]):
            case["diagnosis"].append(fact)
        elif _contains_any(text, _EXAM_HINTS):
            case["tests_and_exams"].append(fact)
        elif _contains_any(text, _HISTORY_HINTS):
            case["medical_history"].append(fact)

        # Patient info and chief complaint from lims source only
        if item["source"].source_type == "lims_text":
            if "salesnotes" not in lowered and text:
                case["chief_complaint"].append(fact)
            case["patient_info"].append(fact)

    case["source_summary"] = _build_source_summary(document_ir)
    case["quality"]["warnings"] = _build_quality_warnings(document_ir)
    case["quality"]["missing_critical"] = _build_missing_critical(document_ir)
    return case


def _generate_with_llm(document_ir: DocumentIR, schema: dict[str, Any]) -> Dict[str, Any]:
    if not settings.llm_endpoint or not settings.llm_api_key:
        raise ValueError("LLM mode requested but LLM_ENDPOINT or LLM_API_KEY not set")
    client = LLMClient()

    stage1 = _llm_stage1_select_facts(client, document_ir)
    stage2 = _llm_stage2_build_case(client, document_ir, schema, stage1)
    stage2 = _enforce_content_guardrails(stage2)

    try:
        validate(instance=stage2, schema=schema)
        return stage2
    except ValidationError as exc:
        return _llm_repair_structure(client, schema, stage2, exc.message)


def _empty_case(case_id: str) -> Dict[str, Any]:
    return {
        "case_id": case_id,
        "source_summary": {"lims_sources": 0, "ocr_sources": 0, "total_pages": 0, "total_lines": 0},
        "patient_info": [],
        "chief_complaint": [],
        "medical_history": [],
        "family_history": [],
        "tests_and_exams": [],
        "diagnosis": [],
        "quality": {"warnings": [], "missing_critical": []},
    }


def _iter_meaningful_lines(sources: List[Source]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for src in sources:
        for page in src.pages:
            for line in page.lines:
                text = (line.text or "").strip()
                if not text:
                    continue
                rows.append({"source": src, "page": page.page_number, "line": line})
    return rows


def _to_evidence(source: Source, page: int | None, line: Line) -> Dict[str, Any]:
    return {
        "source_id": source.source_id,
        "page": page,
        "line_id": line.line_id,
        "quote": line.text,
    }


def _contains_any(text: str, hints: tuple[str, ...]) -> bool:
    return any(h in text for h in hints)


def _line_allowed_for_diagnosis(line: Line) -> bool:
    flags = line.flags or {}
    # Core safeguard: never turn unchecked template options into diagnosis
    if flags.get("form_template") and flags.get("checkbox_state") == "unchecked":
        return False
    return True


def _line_allowed_for_fact(line: Line) -> bool:
    flags = line.flags or {}
    # Global safeguard for template checkboxes: unchecked options are not patient facts.
    if flags.get("form_template") and flags.get("checkbox_state") == "unchecked":
        return False
    return True


def _detect_polarity(text: str, lowered: str) -> str:
    if "☑无" in text or "□无" in text:
        return "negated"
    if any(h in lowered for h in _NEGATION_HINTS):
        return "negated"
    return "asserted"


def _build_source_summary(doc: DocumentIR) -> Dict[str, int]:
    lims_sources = 0
    ocr_sources = 0
    total_pages = 0
    total_lines = 0
    for src in doc.sources:
        if src.source_type == "lims_text":
            lims_sources += 1
        if src.source_type == "ocr_attachment":
            ocr_sources += 1
        total_pages += len(src.pages)
        total_lines += sum(len(p.lines) for p in src.pages)
    return {
        "lims_sources": lims_sources,
        "ocr_sources": ocr_sources,
        "total_pages": total_pages,
        "total_lines": total_lines,
    }


def _build_quality_warnings(doc: DocumentIR) -> List[str]:
    warnings: List[str] = []
    low_conf_count = 0
    for src in doc.sources:
        for page in src.pages:
            for line in page.lines:
                if line.flags.get("low_confidence"):
                    low_conf_count += 1
    if low_conf_count:
        warnings.append(f"low_confidence_lines:{low_conf_count}")
    for src in doc.sources:
        if src.error:
            warnings.append(f"source_error:{src.source_id}:{src.error}")
    return warnings


def _build_missing_critical(doc: DocumentIR) -> List[str]:
    missing: List[str] = []
    if not any(src.source_type == "ocr_attachment" for src in doc.sources):
        missing.append("no_ocr_attachment_source")
    return missing


def _validate_case(case: Dict[str, Any], schema: Dict[str, Any]) -> None:
    validate(instance=case, schema=schema)


def _llm_stage1_select_facts(client: LLMClient, document_ir: DocumentIR) -> Dict[str, Any]:
    prompt = _load_prompt("case_stage1_zh.md")
    candidate_facts = build_candidate_facts(document_ir)
    payload = {
        "instructions": prompt,
        "case_id": document_ir.case_id,
        "candidate_facts": candidate_facts,
    }
    return client.generate_json(prompt, json.dumps(payload, ensure_ascii=False), temperature=0.0)


def _llm_stage2_build_case(
    client: LLMClient,
    document_ir: DocumentIR,
    schema: Dict[str, Any],
    stage1: Dict[str, Any],
) -> Dict[str, Any]:
    prompt = _load_prompt("case_stage2_zh.md")
    payload = {
        "instructions": prompt,
        "schema": schema,
        "case_id": document_ir.case_id,
        "source_summary": _build_source_summary(document_ir),
        "selected_facts": stage1.get("selected_facts", []),
        "quality": stage1.get("quality", {"warnings": [], "missing_critical": []}),
    }
    return client.generate_json(prompt, json.dumps(payload, ensure_ascii=False), temperature=0.0)


def _llm_repair_structure(client: LLMClient, schema: Dict[str, Any], case: Dict[str, Any], err: str) -> Dict[str, Any]:
    repair_system = "你是JSON结构修复助手。仅修复结构，不新增事实。只输出JSON。"
    repair_user = json.dumps(
        {
            "schema": schema,
            "validation_error": err,
            "current_case_json": case,
        },
        ensure_ascii=False,
    )
    repaired = client.generate_json(repair_system, repair_user, temperature=0.0)
    return _enforce_content_guardrails(repaired)


def _enforce_content_guardrails(case: Dict[str, Any]) -> Dict[str, Any]:
    for section in _DISALLOW_SECTIONS:
        items = case.get(section, [])
        filtered = []
        for item in items:
            evidences = item.get("evidence", [])
            if any(_is_unchecked_quote(ev.get("quote", "")) for ev in evidences):
                continue
            if _is_detection_noise_item(item):
                continue
            filtered.append(item)
        case[section] = filtered

    # Keep business-facing content Chinese. If a fact is English-heavy, drop it in MVP.
    for section in (
        "patient_info",
        "chief_complaint",
        "medical_history",
        "family_history",
        "tests_and_exams",
        "diagnosis",
    ):
        case[section] = [x for x in case.get(section, []) if not _is_english_heavy(x.get("text", ""))]
    return case


def _is_unchecked_quote(quote: str) -> bool:
    return "□" in quote and not any(ch in quote for ch in ("☑", "√", "✓", "■"))


def _is_detection_noise_item(item: Dict[str, Any]) -> bool:
    text = item.get("text", "") or ""
    # 如果文本中包含检测项目/套餐关键词且无诊断/病史信号，则判为噪声
    noise_hits = any(k in text for k in (
        "检测项目",
        "送检项目",
        "套餐",
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
    ))
    diag_hits = any(k in text for k in ("临床诊断", "诊断", "病史", "主诉"))
    return noise_hits and not diag_hits


def _is_english_heavy(text: str) -> bool:
    if not text:
        return False
    alpha_words = re.findall(r"[A-Za-z]{3,}", text)
    # Allow short abbreviations such as IVF/ICSI; drop sentence-like English output.
    return len(alpha_words) >= 4


def _load_prompt(name: str) -> str:
    path = _PROMPT_DIR / name
    return path.read_text(encoding="utf-8")
