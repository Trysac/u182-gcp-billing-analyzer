"""Behavior tests for the public API of gcp_billing_analyzer."""

from __future__ import annotations

import pytest

import gcp_billing_analyzer


def test_normalize_trims_and_lowercases() -> None:
    assert gcp_billing_analyzer.normalize("  Hello World ") == "hello world"


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_normalize_rejects_blank_input(value: str) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        gcp_billing_analyzer.normalize(value)


def test_version_is_semver() -> None:
    parts = gcp_billing_analyzer.__version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)
