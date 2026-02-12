#!/usr/bin/env python
"""
Generate case.json from normalized_ir.json files.

Usage:
  micromamba run -n yk-case-generation python scripts/build_case_from_ir.py \
      --ir outputs \
      --out outputs/cases

Optional:
  --mode rule|llm
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from yk_case_generation.models.document_ir import DocumentIR
from yk_case_generation.services.case_builder import generate_case


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ir", required=True, help="normalized IR file or directory")
    parser.add_argument("--out", required=True, help="output directory for case.json")
    parser.add_argument("--mode", default=None, help="case builder mode: rule or llm (default from env, default=llm)")
    args = parser.parse_args()

    ir_path = Path(args.ir)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = [ir_path] if ir_path.is_file() else sorted(ir_path.glob("*_normalized_ir.json"))
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        document_ir = DocumentIR.model_validate(data)
        case = generate_case(document_ir, mode=args.mode)
        out_file = out_dir / f"{document_ir.case_id}_case.json"
        out_file.write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[ok] {f.name} -> {out_file}")


if __name__ == "__main__":
    main()
