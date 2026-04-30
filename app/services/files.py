"""File I/O helpers — saving uploads, writing JSON results."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from fastapi import UploadFile

try:
    import orjson as _jsonlib
    _USE_ORJSON = True
except ImportError:
    import json as _jsonlib  # type: ignore
    _USE_ORJSON = False


async def save_upload(file: UploadFile, destination: Path) -> None:
    with destination.open("wb") as buf:
        shutil.copyfileobj(file.file, buf)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    if _USE_ORJSON:
        path.write_bytes(_jsonlib.dumps(payload, option=_jsonlib.OPT_INDENT_2))
    else:
        import json
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
