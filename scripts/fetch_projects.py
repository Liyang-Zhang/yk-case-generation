#!/usr/bin/env python
"""Fetch project info and attachments for a list of project numbers.

Usage:
  micromamba run -n yk-case-generation python scripts/fetch_projects.py \
      --csv data/samples/dev_projects.csv --out data/devset

Outputs:
  out/raw/<project>.json            raw API data (five fields)
  out/attachments/<project>/...     downloaded attachment files
"""
import argparse
import json
from pathlib import Path
import shutil
import httpx
import pandas as pd
from urllib.parse import urlparse, parse_qs
import shutil
import subprocess
import sys

BASE_URL = "https://newlims-api.yikongenomics.cn/RD/getProjectInfo"
DOWNLOAD_PREFIX = "https://newlims-api.yikongenomics.cn/system/config/download/fileDownload?configPath=&fileNames="


def fetch_project_info(project_number: str) -> dict:
    params = {"projectNumber": project_number}
    resp = httpx.get(BASE_URL, params=params, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") != 1:
        raise RuntimeError(f"bad code: {payload}")
    return payload.get("data", {})


def safe_filename(url: str) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    file_names = qs.get("fileNames") or qs.get("filename") or []
    if file_names:
        return Path(file_names[0]).name
    # fall back to path name
    path_name = Path(parsed.path).name
    if path_name and path_name != "fileDownload":
        return path_name
    return "attachment"


def download(url: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, timeout=60) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    return dest


def split_attachments(val) -> list[str]:
    if not val:
        return []
    return [p.strip() for p in str(val).replace(";", ",").split(",") if p.strip()]


def maybe_extract(file_path: Path, project_number: str):
    suffix = file_path.suffix.lower()
    if suffix in {".zip", ".tar", ".gz", ".tgz", ".bz2"}:
        target_dir = file_path.parent / (file_path.stem + "_extracted")
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.unpack_archive(str(file_path), str(target_dir))
            print(f"[info] extracted {file_path.name} -> {target_dir}")
        except Exception as exc:
            print(f"[WARN] extract failed {project_number} {file_path.name}: {exc}")
    elif suffix == ".rar":
        target_dir = file_path.parent / (file_path.stem + "_extracted")
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["unrar", "x", "-o+", str(file_path), str(target_dir)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"[info] extracted (rar) {file_path.name} -> {target_dir}")
        except FileNotFoundError:
            print(f"[WARN] unrar not found; kept {file_path.name}")
        except subprocess.CalledProcessError as exc:
            print(f"[WARN] extract rar failed {project_number} {file_path.name}: {exc}")
    elif suffix == ".7z":
        target_dir = file_path.parent / (file_path.stem + "_extracted")
        target_dir.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["7z", "x", f"-o{target_dir}", str(file_path)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"[info] extracted (7z) {file_path.name} -> {target_dir}")
        except FileNotFoundError:
            print(f"[WARN] 7z not found; kept {file_path.name}")
        except subprocess.CalledProcessError as exc:
            print(f"[WARN] extract 7z failed {project_number} {file_path.name}: {exc}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, help="CSV with projectNumber column")
    parser.add_argument("--out", required=True, help="output directory")
    args = parser.parse_args()

    out_dir = Path(args.out)
    raw_dir = out_dir / "raw"
    att_dir = out_dir / "attachments"
    raw_dir.mkdir(parents=True, exist_ok=True)
    att_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.csv)
    for project_number in df["projectNumber"]:
        try:
            data = fetch_project_info(project_number)
        except Exception as exc:
            print(f"[WARN] fetch failed {project_number}: {exc}")
            continue

        # save raw json
        raw_path = raw_dir / f"{project_number}.json"
        raw_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        # attachments
        attachment_fields = ["inspectionOrderAttachment", "diagnosticReportAttachments"]
        urls = []
        for field in attachment_fields:
            urls.extend(split_attachments(data.get(field)))
        for idx, url in enumerate(urls, 1):
            try:
                if not url.lower().startswith("http://") and not url.lower().startswith("https://"):
                    url = DOWNLOAD_PREFIX + url
                fname = safe_filename(url)
                dest = att_dir / project_number / fname
                # avoid overwrite if duplicate name
                if dest.exists():
                    dest = dest.with_name(f"{dest.stem}_{idx}{dest.suffix}")
                saved = download(url, dest)
                maybe_extract(saved, project_number)
            except Exception as exc:
                print(f"[WARN] download failed {project_number} {url}: {exc}")
                continue

        print(f"ok {project_number}")


if __name__ == "__main__":
    main()
