#!/usr/bin/env python
"""Run full pipeline by project number and output frontend case JSON."""
from __future__ import annotations

import argparse
from pathlib import Path

from yk_case_generation.services.pipeline_runner import run_project_pipeline


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-number", required=True)
    parser.add_argument("--out", default="runs", help="run output root")
    parser.add_argument("--mode", default=None, help="case builder mode, e.g. llm|rule")
    parser.add_argument("--skip-ocr", action="store_true", help="skip OCR API call (debug only)")
    args = parser.parse_args()

    result = run_project_pipeline(
        project_number=args.project_number,
        output_root=Path(args.out),
        mode=args.mode,
        skip_ocr=args.skip_ocr,
    )
    print(f"status={result.get('status')} run_dir={Path(args.out) / args.project_number}")


if __name__ == "__main__":
    main()
