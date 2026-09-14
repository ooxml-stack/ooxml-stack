"""Ref classification and repository URL normalization."""

from __future__ import annotations

import subprocess

import pytest

from ecosystem_fixtures import CORE_SHA, init_repo
from scripts.ooxml_ci import gitfacts, urls


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("git@github.com:ooxml-stack/ooxml-core.git", "github.com/ooxml-stack/ooxml-core"),
        ("https://github.com/ooxml-stack/ooxml-core.git", "github.com/ooxml-stack/ooxml-core"),
        ("https://github.com/ooxml-stack/ooxml-core", "github.com/ooxml-stack/ooxml-core"),
        # A trailing slash must not leave ``.git`` glued to the repository name.
        ("https://github.com/ooxml-stack/ooxml-core.git/", "github.com/ooxml-stack/ooxml-core"),
        ("https://github.com/ooxml-stack/ooxml-core/", "github.com/ooxml-stack/ooxml-core"),
        ("git://github.com/ooxml-stack/ooxml-core.git", "github.com/ooxml-stack/ooxml-core"),
        ("ssh://git@github.com/ooxml-stack/ooxml-core.git", "github.com/ooxml-stack/ooxml-core"),
        # The scp form takes any user name, not just ``git``.
        ("deploy@code.example:ooxml-stack/ooxml-core.git", "code.example/ooxml-stack/ooxml-core"),
        ("svc-bot@code.example:ooxml-stack/ooxml-core.git", "code.example/ooxml-stack/ooxml-core"),
    ],
)
def test_normalize_repo(url, expected):
    assert urls.normalize_repo(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/ooxml-stack/ooxml-core.git/",
        "https://github.com/ooxml-stack/ooxml-core.git",
        "git://github.com/ooxml-stack/ooxml-core.git",
        "HTTPS://github.com/ooxml-stack/ooxml-core.git",
        "ssh://git@github.com/ooxml-stack/ooxml-core.git",
        "git@github.com:ooxml-stack/ooxml-core.git",
        "deploy@code.example:ooxml-stack/ooxml-core.git",
    ],
)
def test_a_remote_clone_url_resolves_to_its_policy_node(url):
    """A trailing slash or a different scheme must not invent an undeclared node."""
    assert urls.repo_name(url) == "ooxml-core"
    assert urls.owner_of(url) == "ooxml-stack"


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/ooxml-stack/ooxml-core.git",
        "https://github.com/ooxml-stack/ooxml-core",
        "https://github.com/ooxml-stack/ooxml-core.git/",
        "git://github.com/ooxml-stack/ooxml-core.git",
        "HTTPS://github.com/ooxml-stack/ooxml-core.git",
        "ssh://git@github.com/ooxml-stack/ooxml-core.git",
        "git@github.com:ooxml-stack/ooxml-core.git",
        "deploy@code.example:ooxml-stack/ooxml-core.git",
    ],
)
def test_the_clone_gate_accepts_every_form_the_normalizer_resolves(url):
    """The gate and the normalizer must not drift, or a real clone disappears."""
    assert urls.is_remote_repo(url), url
    assert urls.repo_name(url) == "ooxml-core", url


@pytest.mark.parametrize("url", ["../local", "file:///tmp/x", "git+https://github.com/a/b.git"])
def test_a_non_remote_argument_is_not_a_clone_target(url):
    assert not urls.is_remote_repo(url)


def test_every_remote_form_normalizes_to_one_slug():
    """Cross-scheme equality is what keeps declaration/origin comparisons honest."""
    forms = [
        "https://github.com/ooxml-stack/ooxml-core.git",
        "https://github.com/ooxml-stack/ooxml-core",
        "https://github.com/ooxml-stack/ooxml-core.git/",
        "git://github.com/ooxml-stack/ooxml-core.git",
        "HTTPS://github.com/ooxml-stack/ooxml-core.git",
        "ssh://git@github.com/ooxml-stack/ooxml-core.git",
        "git@github.com:ooxml-stack/ooxml-core.git",
    ]
    assert {urls.normalize_repo(form) for form in forms} == {
        "github.com/ooxml-stack/ooxml-core"
    }


def test_url_from_uses_derives_the_declared_repo_url():
    assert urls.url_from_uses("ooxml-stack/ooxml-stack/.github/workflows/x.yml") == (
        "https://github.com/ooxml-stack/ooxml-stack"
    )
    assert urls.owner_from_uses("other-org/repo/path") == "other-org"
    assert urls.owner_of("https://github.com/other-org/repo.git") == "other-org"


def test_classify_remote_ref_distinguishes_tag_shapes():
    listing = {
        "ok": True,
        "tags": {"v0.6.0": "1" * 40, "v0.6.1": "2" * 40},
        "peeled": {"v0.6.1": "3" * 40},
        "heads": {"main": "4" * 40},
    }
    assert gitfacts.classify_remote_ref("v0.6.0", "tag", listing, None, 5)["kind"] == "lightweight_tag"
    assert gitfacts.classify_remote_ref("v0.6.1", "tag", listing, None, 5) == {
        "kind": "annotated_tag",
        "commit": "3" * 40,
    }
    assert gitfacts.classify_remote_ref("main", "branch", listing, None, 5)["kind"] == "branch"
    assert gitfacts.classify_remote_ref("v9.9.9", "tag", listing, None, 5)["kind"] == "missing"


def test_classify_remote_ref_honours_a_declared_branch_selector():
    """A branch declaration must not be masked by a same-named tag."""
    listing = {
        "ok": True,
        "tags": {"stable": "1" * 40},
        "peeled": {},
        "heads": {"stable": "2" * 40},
    }
    assert gitfacts.classify_remote_ref("stable", "branch", listing, None, 5) == {
        "kind": "branch",
        "commit": "2" * 40,
    }
    assert gitfacts.classify_remote_ref("stable", "tag", listing, None, 5)["kind"] == "lightweight_tag"


def test_classify_remote_ref_cannot_confirm_an_absent_sha(tmp_path):
    listing = {"ok": True, "tags": {}, "peeled": {}, "heads": {}}
    result = gitfacts.classify_remote_ref(CORE_SHA, "sha", listing, tmp_path, 5, False)
    assert result["kind"] == "unverifiable"


def test_classify_remote_ref_confirms_a_local_sha(tmp_path):
    init_repo(tmp_path / "repo")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path / "repo", capture_output=True, text=True
    ).stdout.strip()
    listing = {"ok": True, "tags": {}, "peeled": {}, "heads": {}}
    result = gitfacts.classify_remote_ref(head, "sha", listing, tmp_path / "repo", 5, False)
    assert result == {"kind": "full_commit", "commit": head}


def test_classify_remote_ref_reports_an_unreachable_remote():
    result = gitfacts.classify_remote_ref("v0.6.0", "tag", {"ok": False, "error": "boom"}, None, 5)
    assert result == {"kind": "unverifiable", "reason": "boom"}