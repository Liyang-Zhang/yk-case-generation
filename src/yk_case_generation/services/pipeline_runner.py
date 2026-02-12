"""End-to-end project pipeline runner for MVP toolization."""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from yk_case_generation.services.attachment_processing import prepare_images_for_ocr
from yk_case_generation.services.case_builder import generate_case
from yk_case_generation.services.case_response_builder import build_case_response
from yk_case_generation.services.ir_builder import build_ir_for_project
from yk_case_generation.services.lims_api import fetch_project_info, project_payload_to_inputs
from yk_case_generation.services.ocr_runner import run_ocr_on_images
from yk_case_generation.services.storage import save_json

DOWNLOAD_PREFIX = "https://newlims-api.yikongenomics.cn/system/config/download/fileDownload?configPath=&fileNames="
SUPPORTED_ATTACH_EXT = {".docx", ".pdf", ".png", ".jpg", ".jpeg"}


@dataclass
class StepResult:
    name: str
    status: str
    started_at: str
    ended_at: str
    duration_s: float
    error: str | None = None


def run_project_pipeline(
    project_number: str,
    output_root: Path,
    mode: str | None = None,
    skip_ocr: bool = False,
) -> dict[str, Any]:
    run_dir = output_root / project_number
    raw_dir = run_dir / "raw"
    attachments_dir = run_dir / "attachments"
    ocr_inputs_root = run_dir / "ocr_inputs"
    ocr_project_inputs = ocr_inputs_root / project_number
    ocr_results_dir = run_dir / "ocr_results"
    cases_dir = run_dir / "cases"
    frontend_dir = run_dir / "frontend"

    for path in (raw_dir, attachments_dir, ocr_project_inputs, ocr_results_dir, cases_dir, frontend_dir):
        path.mkdir(parents=True, exist_ok=True)

    meta: dict[str, Any] = {
        "project_number": project_number,
        "status": "running",
        "started_at": _now_iso(),
        "ended_at": None,
        "steps": [],
        "stats": {
            "attachments_downloaded": 0,
            "attachments_total": 0,
            "ocr_images_total": 0,
            "ocr_json_total": 0,
        },
        "artifacts": {},
    }

    raw_path = raw_dir / f"{project_number}.json"
    normalized_ir_path = run_dir / f"{project_number}_normalized_ir.json"
    case_path = cases_dir / f"{project_number}_case.json"
    frontend_path = frontend_dir / f"{project_number}_frontend.json"
    run_meta_path = run_dir / "run_meta.json"

    partial = False
    fatal_error = None

    try:
        step, data = _run_step_with_result("fetch_project", lambda: fetch_project_info(project_number))
        meta["steps"].append(step.__dict__)
        if step.status != "ok":
            raise RuntimeError(step.error or "fetch_project_failed")

        save_json(data, raw_path)
        meta["artifacts"]["raw_json"] = str(raw_path)

        lims_texts, attachment_urls = project_payload_to_inputs(data)
        meta["stats"]["attachments_total"] = len(attachment_urls)

        step, downloaded = _run_step_with_result(
            "download_attachments",
            lambda: _download_attachments(attachment_urls, attachments_dir),
        )
        meta["steps"].append(step.__dict__)
        if step.status != "ok":
            partial = True
            downloaded = []
        meta["stats"]["attachments_downloaded"] = len(downloaded)

        all_files = _expand_archives(downloaded)
        supported = [p for p in all_files if p.suffix.lower() in SUPPORTED_ATTACH_EXT]

        step, prepared_images = _run_step_with_result(
            "prepare_ocr_inputs",
            lambda: _prepare_ocr_inputs(project_number, supported, ocr_project_inputs),
        )
        meta["steps"].append(step.__dict__)
        if step.status != "ok":
            partial = True
            prepared_images = []
        meta["stats"]["ocr_images_total"] = len(prepared_images)

        if skip_ocr:
            meta["steps"].append(
                StepResult(
                    name="run_ocr",
                    status="skipped",
                    started_at=_now_iso(),
                    ended_at=_now_iso(),
                    duration_s=0.0,
                    error=None,
                ).__dict__
            )
        else:
            step = _run_step("run_ocr", lambda: run_ocr_on_images(prepared_images, ocr_results_dir))
            meta["steps"].append(step.__dict__)
            if step.status != "ok":
                partial = True

        meta["stats"]["ocr_json_total"] = len(list(ocr_results_dir.glob("*.json")))

        step, doc_ir = _run_step_with_result(
            "build_ir",
            lambda: build_ir_for_project(
                case_id=project_number,
                raw_json=raw_path,
                ocr_results_dir=ocr_results_dir,
                ocr_inputs_dir=ocr_inputs_root,
            ),
        )
        meta["steps"].append(step.__dict__)
        if step.status != "ok":
            raise RuntimeError(step.error or "build_ir_failed")
        save_json(doc_ir.model_dump(), normalized_ir_path)
        meta["artifacts"]["normalized_ir"] = str(normalized_ir_path)

        step, case = _run_step_with_result("build_case", lambda: generate_case(doc_ir, mode=mode))
        meta["steps"].append(step.__dict__)
        if step.status != "ok":
            raise RuntimeError(step.error or "build_case_failed")
        save_json(case, case_path)
        meta["artifacts"]["case_json"] = str(case_path)

        step, frontend = _run_step_with_result("build_frontend_response", lambda: build_case_response(case))
        meta["steps"].append(step.__dict__)
        if step.status != "ok":
            raise RuntimeError(step.error or "build_frontend_response_failed")
        save_json(frontend, frontend_path)
        meta["artifacts"]["frontend_json"] = str(frontend_path)

        meta["status"] = "partial" if partial else "success"
    except Exception as exc:
        fatal_error = str(exc)
        meta["status"] = "failed"
    finally:
        meta["ended_at"] = _now_iso()
        if fatal_error:
            meta["error"] = fatal_error
        save_json(meta, run_meta_path)

    return meta


def _run_step(name: str, fn) -> StepResult:
    started = time.time()
    started_at = _now_iso()
    try:
        fn()
        status = "ok"
        error = None
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        error = str(exc)
    ended_at = _now_iso()
    return StepResult(
        name=name,
        status=status,
        started_at=started_at,
        ended_at=ended_at,
        duration_s=round(time.time() - started, 3),
        error=error,
    )


def _run_step_with_result(name: str, fn):
    started = time.time()
    started_at = _now_iso()
    try:
        result = fn()
        status = "ok"
        error = None
    except Exception as exc:  # noqa: BLE001
        result = None
        status = "failed"
        error = str(exc)
    ended_at = _now_iso()
    step = StepResult(
        name=name,
        status=status,
        started_at=started_at,
        ended_at=ended_at,
        duration_s=round(time.time() - started, 3),
        error=error,
    )
    return step, result


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _download_attachments(urls: list[str], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    for idx, raw_url in enumerate(urls, start=1):
        url = raw_url
        if not url.lower().startswith(("http://", "https://")):
            url = DOWNLOAD_PREFIX + url
        name = _safe_filename(url)
        target = out_dir / name
        if target.exists():
            target = target.with_name(f"{target.stem}_{idx}{target.suffix}")
        with httpx.stream("GET", url, timeout=60) as resp:
            resp.raise_for_status()
            with target.open("wb") as fh:
                for chunk in resp.iter_bytes():
                    fh.write(chunk)
        downloaded.append(target)
    return downloaded


def _safe_filename(url: str) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    names = qs.get("fileNames") or qs.get("filename") or []
    if names:
        return Path(names[0]).name
    path_name = Path(parsed.path).name
    return path_name if path_name and path_name != "fileDownload" else "attachment"


def _expand_archives(files: list[Path]) -> list[Path]:
    out = list(files)
    for f in files:
        suffix = f.suffix.lower()
        extract_dir = f.parent / f"{f.stem}_extracted"
        if suffix in {".zip", ".tar", ".gz", ".tgz", ".bz2"}:
            extract_dir.mkdir(parents=True, exist_ok=True)
            try:
                shutil.unpack_archive(str(f), str(extract_dir))
                out.extend([p for p in extract_dir.rglob("*") if p.is_file()])
            except Exception:
                continue
        elif suffix == ".rar":
            extract_dir.mkdir(parents=True, exist_ok=True)
            try:
                subprocess.run(
                    ["unrar", "x", "-o+", str(f), str(extract_dir)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                out.extend([p for p in extract_dir.rglob("*") if p.is_file()])
            except Exception:
                continue
        elif suffix == ".7z":
            extract_dir.mkdir(parents=True, exist_ok=True)
            try:
                subprocess.run(
                    ["7z", "x", f"-o{extract_dir}", str(f)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                out.extend([p for p in extract_dir.rglob("*") if p.is_file()])
            except Exception:
                continue
    return out


def _prepare_ocr_inputs(project_id: str, attachments: list[Path], out_project_dir: Path) -> list[Path]:
    out_project_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for att in attachments:
        imgs = prepare_images_for_ocr(att)
        for page_no, img in imgs:
            target = out_project_dir / f"{att.stem}_p{page_no}.jpg"
            target.write_bytes(img.read_bytes())
            outputs.append(target)
    return outputs
