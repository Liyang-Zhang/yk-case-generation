"""Simple filesystem storage helpers."""
from pathlib import Path
import json
from yk_case_generation.models.document_ir import DocumentIR


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def save_json(data: dict, path: Path) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_document_ir(document_ir: DocumentIR, base_dir: Path) -> Path:
    target = base_dir / f"{document_ir.case_id}_document_ir.json"
    save_json(document_ir.dict(), target)
    return target
