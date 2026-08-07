"""Naulon — field-level model of the monthly cellular data envelope of a
vehicle telematics fleet.

Sampling rate is rarely what drives the bill. This library breaks the envelope
down field by field, each billed at the rate of the clock it actually follows,
and reports where the bytes go.
"""

from naulon.loader import load_constants, load_schema, load_vectors, model_dir
from naulon.model import Contribution, ModelError, Result, compute, resolve_config

__all__ = [
    "Contribution",
    "ModelError",
    "Result",
    "compute",
    "estimate",
    "load_constants",
    "load_schema",
    "load_vectors",
    "model_dir",
    "resolve_config",
]

__version__ = "0.1.0"


def estimate(config: dict) -> Result:
    """Price a configuration against the shipped constants."""
    return compute(config, load_constants())
