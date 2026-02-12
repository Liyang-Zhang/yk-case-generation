"\"\"\"Run OCR on preprocessed images and persist responses.\"\"\""
from __future__ import annotations
import json
from pathlib import Path
from typing import Iterable
from tenacity import retry, stop_after_attempt, wait_fixed

from yk_case_generation.services.ocr_clients.tencent import TencentOCRClient


@retry(stop=stop_after_attempt(3), wait=wait_fixed(1))
def _ocr_once(client: TencentOCRClient, img_path: Path) -> dict:
    data = img_path.read_bytes()
    return client.general_accurate_image(data)


def run_ocr_on_images(img_paths: Iterable[Path], out_dir: Path) -> None:
    client = TencentOCRClient()
    out_dir.mkdir(parents=True, exist_ok=True)
    for img_path in img_paths:
        try:
            resp = _ocr_once(client, img_path)
            target = out_dir / (img_path.stem + ".json")
            target.write_text(json.dumps(resp, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[ok] {img_path}")
        except Exception as exc:
            print(f"[WARN] ocr failed {img_path}: {exc}")
