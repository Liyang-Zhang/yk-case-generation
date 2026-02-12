#!/usr/bin/env python
"""Prepare OCR-ready images for all attachments in devset.

Usage:
  micromamba run -n yk-case-generation python scripts/prep_ocr_inputs.py \
      --attachments data/devset/attachments --out data/devset/ocr_inputs

Processes docx/pdf/jpg/png; skips others. Writes preprocessed JPEGs per page.
"""
import argparse
from pathlib import Path

from yk_case_generation.services.attachment_processing import prepare_images_for_ocr


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--attachments", required=True, help="attachments root directory")
    parser.add_argument("--out", required=True, help="output directory for OCR images")
    args = parser.parse_args()

    att_root = Path(args.attachments)
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    projects = sorted([p for p in att_root.iterdir() if p.is_dir()])
    total_files = 0
    total_imgs = 0
    for proj_dir in projects:
        for att in proj_dir.iterdir():
            total_files += 1
            ext = att.suffix.lower()
            if ext not in {".docx", ".pdf", ".png", ".jpg", ".jpeg"}:
                print(f"[skip] {proj_dir.name}/{att.name} unsupported")
                continue
            try:
                imgs = prepare_images_for_ocr(att)
            except Exception as exc:
                print(f"[WARN] prepare failed {proj_dir.name}/{att.name}: {exc}")
                continue
            for page_no, img_path in imgs:
                target_dir = out_root / proj_dir.name
                target_dir.mkdir(parents=True, exist_ok=True)
                target = target_dir / f"{att.stem}_p{page_no}.jpg"
                target.write_bytes(img_path.read_bytes())
                total_imgs += 1
            print(f"[ok] {proj_dir.name}/{att.name} -> {len(imgs)} pages")

    print(f"done. files processed: {total_files}, images generated: {total_imgs}")


if __name__ == "__main__":
    main()
