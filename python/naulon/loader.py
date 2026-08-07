"""Locating and loading the shared model files.

model/ is the source of truth for both the Python and the JavaScript
implementation. Neither owns it, and neither may inline its values.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_ENV_VAR = "NAULON_MODEL_DIR"


def model_dir() -> Path:
    """Where model/ lives.

    Honours NAULON_MODEL_DIR, then falls back to the copy shipped inside the
    package, then to the repository layout for an editable install.
    """
    override = os.environ.get(_ENV_VAR)
    if override:
        path = Path(override)
        if not path.is_dir():
            raise FileNotFoundError(f"{_ENV_VAR} points at {path}, which is not a directory")
        return path

    candidates = [
        Path(__file__).parent / "model",
        Path(__file__).parent.parent.parent / "model",
    ]
    for candidate in candidates:
        if (candidate / "constants.yaml").is_file():
            return candidate
    raise FileNotFoundError(
        "cannot locate model/constants.yaml; set " + _ENV_VAR + " to the model directory"
    )


@lru_cache(maxsize=1)
def load_constants() -> dict[str, Any]:
    with (model_dir() / "constants.yaml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    with (model_dir() / "schema.json").open(encoding="utf-8") as fh:
        return json.load(fh)


def load_vectors() -> list[dict[str, Any]]:
    """Cross-implementation parity fixtures.

    Every implementation must reproduce these outputs. They pin behaviour; they
    do not prove correctness.
    """
    path = model_dir() / "vectors.json"
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)["vectors"]
