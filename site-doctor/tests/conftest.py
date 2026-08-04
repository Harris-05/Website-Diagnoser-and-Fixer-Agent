"""Shared pytest fixtures.

The one thing worth knowing here: crawler.storage.CACHE_ROOT is a
*relative* path ("./.site-doctor-cache"), and storage.page_dir() creates
directories as a side effect of building a path. So any test that touches
a storage path would write real folders into whatever directory pytest was
started from. isolated_cache redirects that at tmp_path instead.
"""

import pytest

from crawler import storage


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """Point the on-disk cache at a throwaway tmp dir for one test."""
    monkeypatch.setattr(storage, "CACHE_ROOT", tmp_path / ".site-doctor-cache")
    return storage.CACHE_ROOT
