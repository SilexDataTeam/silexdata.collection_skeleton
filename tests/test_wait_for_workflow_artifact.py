# SPDX-FileCopyrightText: Silex Data Solutions
# SPDX-License-Identifier: Apache-2.0
"""wait-for-workflow-artifact: which run for the commit decides the outcome."""

import json
import pathlib
import subprocess

import pytest

SELECT_RUN = (
    pathlib.Path(__file__).resolve().parent.parent
    / ".github"
    / "actions"
    / "wait-for-workflow-artifact"
    / "select-run.js"
)

SAME_SECOND = "2026-10-02T17:59:49Z"


def run(run_id, status="completed", conclusion=None, created_at=SAME_SECOND):
    return {
        "id": run_id,
        "status": status,
        "conclusion": conclusion,
        "created_at": created_at,
    }


def select(runs):
    """Run selectRun under node, as github-script would, and return its choice."""
    proc = subprocess.run(
        [
            "node",
            "-e",
            "const { selectRun } = require(process.argv[1]);"
            "const c = selectRun(JSON.parse(process.argv[2]));"
            "console.log(JSON.stringify({action: c.action, id: c.run ? c.run.id : null}));",
            str(SELECT_RUN),
            json.dumps(runs),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    choice = json.loads(proc.stdout)
    return choice["action"], choice["id"]


@pytest.mark.parametrize("order", [1, -1], ids=["cancelled-listed-first", "cancelled-listed-last"])
def test_a_cancelled_duplicate_does_not_hide_the_successful_run(order):
    # SilexDataTeam/silexdata.collection_skeleton#23: two runs created in the
    # same second, the first cancelled by the concurrency group.
    runs = [run(1, conclusion="cancelled"), run(2, conclusion="success")][::order]
    assert select(runs) == ("use", 2)


def test_a_cancelled_duplicate_waits_for_the_run_still_going():
    runs = [run(1, conclusion="cancelled"), run(2, status="in_progress")]
    assert select(runs) == ("wait", 2)


def test_a_failure_waits_for_a_run_still_going():
    runs = [run(1, conclusion="failure"), run(2, status="queued")]
    assert select(runs) == ("wait", 2)


def test_the_newest_success_is_used():
    runs = [
        run(1, conclusion="success", created_at="2026-10-02T17:00:00Z"),
        run(2, conclusion="success", created_at="2026-10-02T18:00:00Z"),
    ]
    assert select(runs) == ("use", 2)


def test_a_failure_is_reported_over_a_cancelled_run():
    runs = [run(1, conclusion="failure"), run(2, conclusion="cancelled")]
    assert select(runs) == ("fail", 1)


@pytest.mark.parametrize("conclusion", ["cancelled", "skipped"])
def test_fails_when_every_run_was_superseded(conclusion):
    runs = [run(1, conclusion=conclusion), run(2, conclusion=conclusion)]
    assert select(runs) == ("fail", 2)


def test_waits_for_the_first_run_to_appear():
    assert select([]) == ("wait", None)


def test_a_lone_run_still_going_is_waited_on():
    assert select([run(1, status="in_progress")]) == ("wait", 1)
