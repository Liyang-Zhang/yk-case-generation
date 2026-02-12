#!/usr/bin/env python
"""Run Tencent GeneralAccurateOCR on preprocessed images.

Usage:
  micromamba run -n yk-case-generation python scripts/run_ocr_inputs.py \
      --images data/devset/ocr_inputs --out data/devset/ocr_results

Requires env vars: TENCENT_SECRET_ID, TENCENT_SECRET_KEY (and optional TENCENT_REGION).
"""
import argparse
from pathlib import Path

from yk_case_generation.services.ocr_runner import run_ocr_on_images


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", required=True, help="directory containing OCR-ready images")
    parser.add_argument("--out", required=True, help="output directory for OCR JSON")
    parser.add_argument("--limit", type=int, default=None, help="limit number of images (for testing)")
    args = parser.parse_args()

    img_root = Path(args.images)
    out_root = Path(args.out)
    imgs = sorted([p for p in img_root.rglob("*.jpg")])
    if args.limit:
        imgs = imgs[: args.limit]
    run_ocr_on_images(imgs, out_root)


if __name__ == "__main__":
    main()
