#!/usr/bin/env python
"""
Build normalized IR for projects using OCR results + LIMS raw fields.

Usage:
  micromamba run -n yk-case-generation python scripts/ocr_to_ir.py \
      --project YKZW_IFGS_M_251010_30GN_0001 \
      --raw-dir data/devset/raw \
      --ocr-results data/devset/ocr_results \
      --ocr-inputs data/devset/ocr_inputs \
      --out outputs

If --project is omitted, process all projects found in raw-dir.
"""
import argparse
from pathlib import Path
import json

from yk_case_generation.services.ir_builder import build_ir_for_project
from yk_case_generation.services.storage import save_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", help="project number; if omitted, process all in raw-dir")
    parser.add_argument("--raw-dir", required=True, help="dir with raw project json")
    parser.add_argument("--ocr-results", required=True, help="dir with OCR result json files")
    parser.add_argument("--ocr-inputs", required=True, help="dir with OCR input images (for project inference)")
    parser.add_argument("--out", required=True, help="output directory for normalized_ir.json")
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    ocr_results = Path(args.ocr_results)
    ocr_inputs = Path(args.ocr_inputs)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    projects = []
    if args.project:
        projects = [args.project]
    else:
        projects = [p.stem for p in raw_dir.glob("*.json")]

    for pid in projects:
        raw_path = raw_dir / f"{pid}.json"
        if not raw_path.exists():
            print(f"[WARN] raw json missing for {pid}")
            continue
        doc_ir = build_ir_for_project(
            case_id=pid,
            raw_json=raw_path,
            ocr_results_dir=ocr_results,
            ocr_inputs_dir=ocr_inputs,
        )
        out_path = out_dir / f"{pid}_normalized_ir.json"
        save_json(doc_ir.model_dump(), out_path)
        print(f"[ok] {pid} -> {out_path}")


if __name__ == "__main__":
    main()
