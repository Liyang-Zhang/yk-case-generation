#!/usr/bin/env python
"""
Build frontend response JSON from internal case JSON files.

Usage:
  micromamba run -n yk-case-generation python scripts/build_case_response.py \
      --case outputs/cases_llm \
      --out outputs/cases_frontend
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from yk_case_generation.services.case_response_builder import build_case_response


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True, help="case json file or directory")
    parser.add_argument("--out", required=True, help="output directory for frontend json")
    args = parser.parse_args()

    case_path = Path(args.case)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    files = [case_path] if case_path.is_file() else sorted(case_path.glob("*_case.json"))
    for f in files:
        case = json.loads(f.read_text(encoding="utf-8"))
        resp = build_case_response(case)
        out_file = out_dir / f.name.replace("_case.json", "_frontend.json")
        out_file.write_text(json.dumps(resp, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[ok] {f.name} -> {out_file}")


if __name__ == "__main__":
    main()
