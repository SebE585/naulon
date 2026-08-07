"""Cross-implementation parity.

Every implementation of the model — Python, JavaScript, whatever comes next —
must reproduce model/vectors.json exactly. This is what makes duplicating a
hundred lines of arithmetic safe: divergence cannot be merged.
"""

from __future__ import annotations

import pytest

from naulon import compute, load_constants, load_vectors

VECTORS = load_vectors()


@pytest.mark.parametrize("vector", VECTORS, ids=[v["name"] for v in VECTORS])
def test_vector(vector):
    result = compute(vector["config"], load_constants())
    for key, expected in vector["expect"].items():
        actual = getattr(result, key)
        assert actual == pytest.approx(expected, rel=1e-9), f"{vector['name']}.{key}"


def test_vectors_cover_every_profile():
    covered = {v["config"]["profile"] for v in VECTORS}
    assert covered == set(load_constants()["profiles"])
