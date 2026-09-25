# SPDX-FileCopyrightText: Silex Data Solutions
# SPDX-License-Identifier: Apache-2.0
"""reusable-nox.yml: sanity ignore files must reach the newest ansible-core."""

import os

import pytest

META = "- ansible-test-sanity -> Meta session for running all ansible-test-sanity-* sessions.\n"


def listing(versions, suffix="", extra=""):
    """What `nox --list` prints: a line per sanity session, among others."""
    lines = "".join(
        f"- ansible-test-sanity-{v}{suffix} -> Run sanity tests from ansible-core {v}'s ansible-test\n"
        for v in versions
    )
    return (
        "Sessions defined in noxfile.py:\n\n* lint -> Run all linters\n"
        + lines
        + META
        + extra
    )


@pytest.fixture
def collection(tmp_path):
    (tmp_path / "tests" / "sanity").mkdir(parents=True)
    return tmp_path


def ignores(collection, *versions):
    for v in versions:
        (collection / "tests" / "sanity" / f"ignore-{v}.txt").write_text(
            "plugins/modules/m.py validate-modules:missing-gplv3-license\n"
        )


def check(step, collection, nox_output):
    bindir = collection / "bin"
    bindir.mkdir()
    (bindir / "nox").write_text(
        '#!/usr/bin/env bash\necho called >> "$NOX_CALLS"\nprintf "%s" "$NOX_LISTING"\n'
    )
    (bindir / "nox").chmod(0o755)
    calls = collection / "nox.calls"
    result = step(
        "reusable-nox.yml",
        "detect",
        "sanity-ignores",
        {"IGNORES": "tests/sanity"},
        cwd=collection,
        runner={
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "NOX_CALLS": str(calls),
            "NOX_LISTING": nox_output,
        },
    )
    result.nox_called = calls.exists()
    return result


MATRIX = ["2.14", "2.15", "2.16", "2.17", "2.18", "2.19", "2.20", "2.21", "2.22"]


def test_a_newest_version_without_its_ignore_file_fails(step, collection):
    ignores(collection, *MATRIX[:-1])  # akamai before 2.22 joined the matrix
    result = check(step, collection, listing(MATRIX))
    assert result.returncode != 0
    errors = result.annotations("error")
    assert len(errors) == 1
    assert "no tests/sanity/ignore-2.22.txt" in errors[0]
    assert errors[0].endswith("copy it to ignore-2.22.txt.")


def test_a_license_sidecar_is_named_too(step, collection):
    ignores(collection, "2.21")
    (collection / "tests" / "sanity" / "ignore-2.21.txt.license").write_text(
        "SPDX-FileCopyrightText: Silex Data Solutions\n"
        "SPDX-License-Identifier: Apache-2.0\n"
    )
    result = check(step, collection, listing(["2.21", "2.22"]))
    assert result.returncode != 0
    assert result.annotations("error")[0].endswith(
        "copy it to ignore-2.22.txt, and its .license sidecar to ignore-2.22.txt.license."
    )


def test_older_nox_session_names_are_understood(step, collection):
    # antsibull-nox 1.8 named sessions ansible-test-sanity-<core>-<python>.
    ignores(collection, *MATRIX[:-1])
    result = check(step, collection, listing(MATRIX, suffix="-3.14"))
    assert result.returncode != 0
    assert "ignore-2.22.txt" in result.annotations("error")[0]


@pytest.mark.parametrize(
    ("present", "why"),
    [
        (MATRIX, "every version has its file"),
        (["2.14", "2.15"], "exceptions only ever needed for old versions"),
        (["2.22"], "only the newest needs one"),
    ],
    ids=["all", "old-only", "newest-only"],
)
def test_ignore_files_that_are_carried_forward_pass(step, collection, present, why):
    ignores(collection, *present)
    result = check(step, collection, listing(MATRIX))
    assert result.returncode == 0, (why, result.stdout)
    assert not result.annotations("error")


def test_devel_and_milestone_sessions_are_left_out(step, collection):
    ignores(collection, *MATRIX)
    extra = (
        "- ansible-test-sanity-devel -> Run sanity tests from ansible-core's devel branch\n"
        "- ansible-test-sanity-milestone -> Run sanity tests from ansible-core's milestone branch\n"
    )
    result = check(step, collection, listing(MATRIX, extra=extra))
    assert result.returncode == 0, result.stdout


def test_a_collection_without_ignore_files_does_not_run_nox(step, collection):
    result = check(step, collection, listing(MATRIX))
    assert result.returncode == 0
    assert not result.nox_called


def test_versions_are_ordered_numerically(step, collection):
    # Sorted as text, 2.9 would come after 2.10 and be taken for the newest.
    ignores(collection, "2.9")
    result = check(step, collection, listing(["2.9", "2.10"]))
    assert result.returncode != 0
    assert "copy it to ignore-2.10.txt" in result.annotations("error")[0]


@pytest.mark.parametrize("versions", [[], ["2.22"]], ids=["none", "one"])
def test_a_matrix_with_no_previous_version_passes(step, collection, versions):
    ignores(collection, "2.14")
    result = check(step, collection, listing(versions))
    assert result.returncode == 0, result.stdout
