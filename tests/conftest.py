# Author: Hershal Pandya — https://www.linkedin.com/in/hershalpandya/
"""Shared fixtures. The two fixture projects are built once per session and copied into each test's tmp_path,
so every test still owns a private, writable project."""

from copy import deepcopy
import shutil

import pytest

from support import build_delivery_edition, build_story


@pytest.fixture(scope="session")
def _story_cache(tmp_path_factory):
    work = tmp_path_factory.mktemp("story-cache")
    _, plan = build_story(work)
    return work, plan


@pytest.fixture
def story(_story_cache, tmp_path):
    """A format-2 story project at tmp_path/story; yields (root, plan)."""
    work, plan = _story_cache
    shutil.copytree(work, tmp_path, dirs_exist_ok=True)
    return tmp_path / "story", deepcopy(plan)


@pytest.fixture(scope="session")
def _delivery_cache(tmp_path_factory):
    work = tmp_path_factory.mktemp("delivery-cache")
    _, _, spec, _ = build_delivery_edition(work)
    return work, spec


@pytest.fixture
def delivery(_delivery_cache, tmp_path):
    """An imported edition and its source project under tmp_path; yields (legacy, root, spec, metadata)."""
    work, spec = _delivery_cache
    shutil.copytree(work, tmp_path, dirs_exist_ok=True)
    return (tmp_path / "delivery-source", tmp_path / "delivery-edition", deepcopy(spec),
            tmp_path / "delivery-metadata.json")
