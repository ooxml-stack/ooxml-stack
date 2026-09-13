"""PEP 440 constraint evaluation and the version diagnostics.

``versions.satisfies`` delegates to ``packaging``. These tests pin the concrete
cases a hand-rolled comparator got wrong, and the "cannot evaluate" path that
must never turn into a silent pass.
"""

from __future__ import annotations

import pytest

import ecosystem_fixtures  # noqa: F401  (puts the repo root on sys.path)
from scripts.ooxml_ci import versions

CASES = [
    # A public specifier ignores the candidate's local segment.
    ("1.0+local", "!=1.0", False),
    ("1.0+abc", "==1.0", True),
    ("1.0+abc", "==1.0+abc", True),
    ("1.0+abc", "==1.0+def", False),
    ("0.5+local", "<=0.5", True),
    # Wildcards zero-pad the release on the right.
    ("1.0", "==1.0.0.*", True),
    ("1", "==1.0.*", True),
    ("1.0.0", "==1.0.*", True),
    ("1.0.1", "==1.0.0.*", False),
    # Pre-releases are excluded unless the specifier is itself a pre-release.
    ("1.0.dev", "==1.0", False),
    ("1.0.dev0", "==1.0", False),
    ("1.0a1", "==1.0", False),
    ("0.6.0rc1", ">=0.6.0", False),
    # Exclusive ordered comparisons.
    ("0.6.0", ">0.6", False),
    ("0.6.0", ">=0.6", True),
    ("0.5post1.dev1", ">0.5", False),
    ("1a1", "<1!1.0", True),
    # Equality and compatible release.
    ("0.6.0", "==0.6", True),
    ("0.6.0", "!=0.6", False),
    ("1", "~=1.0.0", True),
    ("0.5.9", "~=0.5.0", True),
    ("0.6.0", "~=0.5.0", False),
    ("0.5.4", "~=0.5.4", True),
    ("1.4.7", "==1.4.*", True),
    ("1.5.0", "==1.4.*", False),
    ("1.4.7", "===1.4.7", True),
    # Intersections.
    ("1.0", ">=0.5,<2", True),
    ("1.0.1", ">=1.0,!=1.0.1", False),
]


@pytest.mark.parametrize(("version", "spec", "expected"), CASES)
def test_satisfies_matches_pep_440(version, spec, expected):
    assert versions.satisfies(version, spec) is expected


@pytest.mark.parametrize("spec", ["not a spec", "", ">=0.5,~=bad", "ooxml-core^1.0"])
def test_unsupported_specs_are_not_evaluated(spec):
    """``None`` -- never a silent ``False`` -- so the caller reports it."""
    assert versions.satisfies("0.6.0", spec) is None


@pytest.mark.parametrize("version", ["", "not-a-version", "1.0.0-"])
def test_unsupported_versions_are_not_evaluated(version):
    assert versions.satisfies(version, ">=0.1") is None