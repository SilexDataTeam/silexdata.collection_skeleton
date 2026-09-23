# SPDX-FileCopyrightText: Silex Data Solutions
# SPDX-License-Identifier: Apache-2.0
"""Values the reusable workflows detect from the caller's collection."""

import json

import pytest


def runtime(tmp_path, requires):
    (tmp_path / "meta").mkdir()
    (tmp_path / "meta" / "runtime.yml").write_text(
        f"---\nrequires_ansible: {requires}\n"
    )
    return tmp_path


@pytest.mark.parametrize(
    ("requires", "floor"),
    [
        ("'>=2.16.0'", "2.16"),
        ('">=2.14.0"', "2.14"),
        (">=2.9.10", "2.9"),
        ("'>=2.15.0,<2.20'", "2.15"),
    ],
)
def test_nox_floor_comes_from_requires_ansible(step, tmp_path, requires, floor):
    result = step(
        "reusable-nox.yml",
        "detect",
        "runtime",
        {"OVERRIDE": ""},
        cwd=runtime(tmp_path, requires),
    )
    assert result.returncode == 0, result.stdout
    assert result.outputs["min_ansible_core"] == floor


def test_nox_floor_override_wins(step, tmp_path):
    result = step(
        "reusable-nox.yml",
        "detect",
        "runtime",
        {"OVERRIDE": "2.18"},
        cwd=runtime(tmp_path, "'>=2.14.0'"),
    )
    assert result.outputs["min_ansible_core"] == "2.18"


def test_nox_floor_fails_loudly_when_underivable(step, tmp_path):
    result = step(
        "reusable-nox.yml",
        "detect",
        "runtime",
        {"OVERRIDE": ""},
        cwd=runtime(tmp_path, "''"),
    )
    assert result.returncode != 0
    assert result.annotations("error")
    assert "min_ansible_core" not in result.outputs


@pytest.mark.parametrize(
    "workflow", ["reusable-coverage.yml", "reusable-docs.yml", "reusable-release.yml"]
)
def test_namespace_and_name_come_from_galaxy_yml(step, tmp_path, workflow):
    (tmp_path / "galaxy.yml").write_text(
        "---\n# name: not-this-one\nnamespace: silexdata\nname: cyberark\nversion: 0.0.1\n"
    )
    job = "release" if workflow == "reusable-release.yml" else "detect"
    result = step(workflow, job, "galaxy", {}, cwd=tmp_path)
    assert result.returncode == 0, result.stdout
    assert result.outputs["namespace"] == "silexdata"
    assert result.outputs["name"] == "cyberark"


MATRIX = (
    '[{"ansible": "2.14", "python": "3.11"}, {"ansible": "2.15", "python": "3.11"},'
    ' {"ansible": "2.16", "python": "3.11"}, {"ansible": "2.9", "python": "3.8"},'
    ' {"ansible": "2.21", "python": "3.12"}]'
)


@pytest.mark.parametrize(
    ("requires", "override", "versions"),
    [
        ("'>=2.16.0'", "", ["2.16", "2.21"]),
        ("'>=2.14.0'", "", ["2.14", "2.15", "2.16", "2.21"]),
        # Compared numerically, not as strings: 2.9 < 2.14 < 2.16.
        ("'>=2.9.0'", "", ["2.14", "2.15", "2.16", "2.9", "2.21"]),
        ("'>=2.10.0'", "", ["2.14", "2.15", "2.16", "2.21"]),
        ("'>=2.14.0'", "2.21", ["2.21"]),
    ],
)
def test_coverage_matrix_starts_at_the_floor(
    step, tmp_path, requires, override, versions
):
    result = step(
        "reusable-coverage.yml",
        "detect",
        "matrix",
        {"OVERRIDE": override, "MATRIX": MATRIX},
        cwd=runtime(tmp_path, requires),
    )
    assert result.returncode == 0, result.stdout
    assert [e["ansible"] for e in json.loads(result.outputs["matrix"])] == versions


@pytest.mark.parametrize(
    ("requires", "override"),
    [("''", ""), ("'>=2.14.0'", "2.99")],
    ids=["underivable", "nothing-left"],
)
def test_coverage_matrix_fails_loudly(step, tmp_path, requires, override):
    result = step(
        "reusable-coverage.yml",
        "detect",
        "matrix",
        {"OVERRIDE": override, "MATRIX": MATRIX},
        cwd=runtime(tmp_path, requires),
    )
    assert result.returncode != 0
    assert result.annotations("error")
    assert "matrix" not in result.outputs
