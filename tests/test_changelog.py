# SPDX-FileCopyrightText: Silex Data Solutions
# SPDX-License-Identifier: Apache-2.0
"""reusable-changelog.yml: a PR must add or extend a changelog fragment."""

import subprocess

import pytest

FRAGMENTS = "changelogs/fragments/"


def git(cwd, *args):
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=selftest",
            "-c",
            "user.email=selftest@localhost",
            *args,
        ],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def pr(tmp_path):
    """A clone whose HEAD is a PR branch off origin/main, as actions/checkout leaves it."""
    origin, clone = tmp_path / "origin.git", tmp_path / "clone"
    git(tmp_path, "init", "--quiet", "--bare", "--initial-branch=main", str(origin))
    git(tmp_path, "clone", "--quiet", str(origin), str(clone))
    (clone / FRAGMENTS).mkdir(parents=True)
    (clone / FRAGMENTS / ".gitkeep").write_text("")
    (clone / FRAGMENTS / "existing.yml").write_text("minor_changes:\n  - old\n")
    git(clone, "add", "-A")
    git(clone, "commit", "--quiet", "-m", "base")
    git(clone, "push", "--quiet", "origin", "main")
    git(clone, "switch", "--quiet", "-c", "feature")
    return clone


def commit(clone, change):
    change(clone)
    git(clone, "add", "-A")
    git(clone, "commit", "--quiet", "--allow-empty", "-m", "change")


@pytest.mark.parametrize(
    ("change", "passes"),
    [
        (lambda c: (c / FRAGMENTS / "new.yml").write_text("bugfixes:\n  - x\n"), True),
        (
            lambda c: (c / FRAGMENTS / "existing.yml").write_text(
                "minor_changes:\n  - old\n  - more\n"
            ),
            True,
        ),
        (lambda c: (c / "README.md").write_text("docs only\n"), False),
        (lambda c: (c / FRAGMENTS / ".gitkeep").write_text("touched\n"), False),
        (lambda c: (c / FRAGMENTS / "existing.yml").unlink(), False),
        (lambda c: None, False),
    ],
    ids=[
        "adds-fragment",
        "extends-fragment",
        "no-fragment",
        "gitkeep-only",
        "deletes-fragment",
        "empty",
    ],
)
def test_fragment_required(step, pr, change, passes):
    commit(pr, change)
    result = step(
        "reusable-changelog.yml",
        "fragment-present",
        "fragment",
        {"BASE": "main", "FRAGMENTS": FRAGMENTS},
        cwd=pr,
    )
    assert (result.returncode == 0) == passes, result.stdout
    assert bool(result.annotations("error")) == (not passes)
