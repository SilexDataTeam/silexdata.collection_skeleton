# SPDX-FileCopyrightText: Silex Data Solutions
# SPDX-License-Identifier: Apache-2.0
"""reusable-release.yml: whether a merge releases, and as which version."""

import pytest


@pytest.mark.parametrize(
    ("token", "api_key", "configured"),
    [
        ("true", "true", "true"),
        ("true", "false", "false"),
        ("false", "true", "false"),
        ("false", "false", "false"),
    ],
)
def test_release_is_skipped_unless_both_secrets_are_set(
    step, token, api_key, configured
):
    result = step(
        "reusable-release.yml",
        "release",
        "secrets",
        {"HAS_RELEASE_TOKEN": token, "HAS_GALAXY_API_KEY": api_key},
    )
    assert result.returncode == 0
    assert result.outputs["configured"] == configured
    # Skipping is announced, never silent, and never a failure.
    assert bool(result.annotations("notice")) == (configured == "false")


def collection(tmp_path, version, fragments):
    tmp_path.mkdir()
    (tmp_path / "galaxy.yml").write_text(f"version: {version}\n")
    frag_dir = tmp_path / "changelogs" / "fragments"
    frag_dir.mkdir(parents=True)
    for name, body in fragments.items():
        (frag_dir / name).write_text(body)
    return tmp_path


@pytest.mark.parametrize(
    ("version", "fragments", "expected"),
    [
        # Pre-1.0: nothing is released until major_changes cuts exactly 1.0.0.
        ("0.0.1", {"a.yml": "minor_changes:\n  - x\n"}, None),
        ("0.0.1", {"a.yml": "bugfixes:\n  - x\n"}, None),
        ("0.0.1", {"a.yml": "breaking_changes:\n  - x\n"}, None),
        ("0.0.1", {"a.yml": "major_changes:\n  - x\n"}, "1.0.0"),
        (
            "0.0.1",
            {"a.yml": "minor_changes:\n  - x\n", "b.yml": "major_changes:\n  - y\n"},
            "1.0.0",
        ),
        # From 1.0.0 on: semver from the most significant section.
        ("1.2.3", {"a.yml": "bugfixes:\n  - x\n"}, "1.2.4"),
        ("1.2.3", {"a.yml": "minor_changes:\n  - x\n"}, "1.3.0"),
        (
            "1.2.3",
            {"a.yml": "minor_changes:\n  - x\n", "b.yaml": "bugfixes:\n  - y\n"},
            "1.3.0",
        ),
        ("1.2.3", {"a.yml": "major_changes:\n  - x\n"}, "2.0.0"),
        ("1.2.3", {"a.yml": "breaking_changes:\n  - x\n"}, "2.0.0"),
        ("1.2.3", {"a.yaml": "removed_features:\n  - x\n"}, "2.0.0"),
        # Fragments that never warrant a release, at any version.
        ("1.2.3", {"a.yml": "trivial:\n  - x\n"}, None),
        ("1.2.3", {"a.yml": "release_summary: x\n"}, None),
        ("1.2.3", {"a.yml": ""}, None),
        ("1.2.3", {}, None),
    ],
)
def test_next_version(step, tmp_path, version, fragments, expected):
    cwd = collection(tmp_path / "coll", version, fragments)
    result = step("reusable-release.yml", "release", "ver", {}, cwd=cwd)
    assert result.returncode == 0, result.stdout
    if expected is None:
        assert result.outputs["release"] == "false"
        assert result.outputs["reason"]
        assert "version" not in result.outputs
    else:
        assert result.outputs["release"] == "true"
        assert result.outputs["version"] == expected


def released_collection(tmp_path, version, released, fragments):
    """A collection whose changelog.yaml records `released` versions."""
    cwd = collection(tmp_path, version, fragments)
    releases = "".join(f"  {v}:\n    release_date: '2026-01-01'\n" for v in released)
    (cwd / "changelogs" / "changelog.yaml").write_text(
        "ancestor: null\nreleases:\n" + (releases or "  {}\n")
    )
    return cwd


@pytest.mark.parametrize(
    ("version", "released", "fragments", "expected"),
    [
        # galaxy.yml is the latest release: bump it, exactly as before.
        ("1.2.0", ["1.0.0", "1.1.0", "1.2.0"], {"a.yml": "bugfixes:\n  - x\n"}, "1.2.1"),
        ("1.2.0", ["1.2.0"], {"a.yml": "removed_features:\n  - x\n"}, "2.0.0"),
        # galaxy.yml set ahead (e.g. for a tombstone): release it, not past it.
        ("2.0.0", ["1.1.0", "1.2.0"], {"a.yml": "removed_features:\n  - x\n"}, "2.0.0"),
        ("2.0.0", ["1.2.0"], {"a.yml": "breaking_changes:\n  - x\n", "b.yml": "bugfixes:\n  - y\n"}, "2.0.0"),
        ("2.0.0", ["1.2.0"], {"a.yml": "bugfixes:\n  - x\n"}, "2.0.0"),
        ("1.3.0", ["1.2.0"], {"a.yml": "minor_changes:\n  - x\n"}, "1.3.0"),
        # A preset below what the fragments need is raised to the bump.
        ("1.2.1", ["1.2.0"], {"a.yml": "breaking_changes:\n  - x\n"}, "2.0.0"),
        # Releases are compared as versions, not strings.
        ("1.10.0", ["1.9.0"], {"a.yml": "minor_changes:\n  - x\n"}, "1.10.0"),
        ("1.9.1", ["1.9.0", "1.10.0"], {"a.yml": "bugfixes:\n  - x\n"}, "1.9.2"),
        # A preset alone releases nothing.
        ("2.0.0", ["1.2.0"], {"a.yml": "trivial:\n  - x\n"}, None),
        # No releases recorded yet: galaxy.yml is the base, as before.
        ("1.2.3", [], {"a.yml": "minor_changes:\n  - x\n"}, "1.3.0"),
        ("0.0.1", [], {"a.yml": "major_changes:\n  - x\n"}, "1.0.0"),
    ],
)
def test_next_version_with_releases(step, tmp_path, version, released, fragments, expected):
    cwd = released_collection(tmp_path / "coll", version, released, fragments)
    result = step("reusable-release.yml", "release", "ver", {}, cwd=cwd)
    assert result.returncode == 0, result.stdout
    if expected is None:
        assert result.outputs["release"] == "false"
        assert "version" not in result.outputs
    else:
        assert result.outputs["release"] == "true"
        assert result.outputs["version"] == expected
