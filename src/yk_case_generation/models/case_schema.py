from typing import Any
import json
from pathlib import Path

DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "case_schema_v1.json"


def load_schema(path: Path | str | None = None) -> dict[str, Any]:
    schema_path = Path(path) if path else DEFAULT_SCHEMA_PATH
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)
