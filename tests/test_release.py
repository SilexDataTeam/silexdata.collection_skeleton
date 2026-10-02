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
