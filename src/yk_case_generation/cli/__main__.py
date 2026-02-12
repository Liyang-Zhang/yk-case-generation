from pathlib import Path
import json
import csv
from datetime import datetime, timezone
import typer

from yk_case_generation.services.case_response_builder import build_case_response
from yk_case_generation.services.pipeline_runner import run_project_pipeline

app = typer.Typer(help="YK case generation CLI")


@app.command()
def project_run(
    project_number: str,
    output_dir: Path = Path("runs"),
    mode: str | None = None,
    skip_ocr: bool = False,
):
    """Main command: run full pipeline from project number to frontend JSON."""
    result = run_project_pipeline(
        project_number=project_number,
        output_root=output_dir,
        mode=mode,
        skip_ocr=skip_ocr,
    )
    typer.echo(f"status={result.get('status')} run_dir={output_dir / project_number}")


@app.command("project-run-batch")
def project_run_batch(
    csv_file: Path,
    output_dir: Path = Path("runs"),
    mode: str | None = None,
    skip_ocr: bool = False,
    project_column: str = "projectNumber",
    limit: int | None = None,
    fail_fast: bool = False,
):
    """Batch runner: execute full pipeline for all project IDs in a CSV column."""
    if not csv_file.exists():
        raise typer.BadParameter(f"csv not found: {csv_file}")

    project_ids = _read_project_ids(csv_file, project_column, limit)
    if not project_ids:
        raise typer.BadParameter(f"no project ids found in column '{project_column}'")

    summary = {
        "started_at": _now_iso(),
        "csv_file": str(csv_file),
        "project_column": project_column,
        "mode": mode,
        "skip_ocr": skip_ocr,
        "total": len(project_ids),
        "success": 0,
        "partial": 0,
        "failed": 0,
        "results": [],
    }

    for pid in project_ids:
        result = run_project_pipeline(
            project_number=pid,
            output_root=output_dir,
            mode=mode,
            skip_ocr=skip_ocr,
        )
        status = result.get("status", "failed")
        summary["results"].append(
            {
                "project_number": pid,
                "status": status,
                "run_dir": str(output_dir / pid),
                "error": result.get("error"),
            }
        )
        if status == "success":
            summary["success"] += 1
        elif status == "partial":
            summary["partial"] += 1
        else:
            summary["failed"] += 1
            if fail_fast:
                break
        typer.echo(f"[{status}] {pid}")

    summary["ended_at"] = _now_iso()
    summary_path = output_dir / f"batch_summary_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(
        "done "
        f"total={summary['total']} success={summary['success']} "
        f"partial={summary['partial']} failed={summary['failed']} "
        f"summary={summary_path}"
    )


@app.command()
def inspect_run(
    project_number: str,
    output_dir: Path = Path("runs"),
):
    """Debug helper: print concise run status and failed steps from run_meta."""
    run_meta = output_dir / project_number / "run_meta.json"
    if not run_meta.exists():
        raise typer.BadParameter(f"run meta not found: {run_meta}")
    meta = json.loads(run_meta.read_text(encoding="utf-8"))
    typer.echo(f"project={project_number} status={meta.get('status')}")
    for step in meta.get("steps", []):
        if step.get("status") != "ok":
            typer.echo(
                f"  step={step.get('name')} status={step.get('status')} error={step.get('error')}"
            )


@app.command()
def build_response(
    case_json: Path,
    output: Path | None = None,
):
    """Debug helper: convert one internal case.json to frontend response JSON."""
    if not case_json.exists():
        raise typer.BadParameter(f"case json not found: {case_json}")
    case = json.loads(case_json.read_text(encoding="utf-8"))
    response = build_case_response(case)
    target = output or case_json.with_name(case_json.name.replace("_case.json", "_frontend.json"))
    target.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
    typer.echo(f"written {target}")


def _read_project_ids(csv_file: Path, project_column: str, limit: int | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    with csv_file.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if project_column not in (reader.fieldnames or []):
            raise typer.BadParameter(f"column '{project_column}' not found in {csv_file}")
        for row in reader:
            pid = (row.get(project_column) or "").strip()
            if not pid or pid in seen:
                continue
            seen.add(pid)
            out.append(pid)
            if limit and len(out) >= limit:
                break
    return out


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main():
    app()


if __name__ == "__main__":
    main()
