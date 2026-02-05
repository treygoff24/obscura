"""Shared test fixtures for Obscura test suite."""

import pathlib
import shutil
import tempfile

import pytest


@pytest.fixture
def tmp_dir():
    """Provide a temporary directory that is cleaned up after the test."""
    d = tempfile.mkdtemp(prefix="obscura_test_")
    yield pathlib.Path(d)
    shutil.rmtree(d, ignore_errors=True)
