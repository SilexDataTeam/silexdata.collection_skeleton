# SPDX-FileCopyrightText: Silex Data Solutions
# SPDX-License-Identifier: Apache-2.0
"""The `Nox result` / `Coverage result` gates.

GitHub reports a job skipped by `if:` as passing a required check, so these
gates are the only thing that stops a broken PR merging. Anything other than
success upstream - including skipped and cancelled - must fail them.
"""

import itertools

import pytest

GATES = {
    ("reusable-nox.yml", "result"): ("DETECT", "EXTRA", "NOX"),
    ("reusable-coverage.yml", "result"): ("DETECT", "COVERAGE", "AGGREGATE"),
}
NOT_SUCCESS = ("failure", "cancelled", "skipped", "")


@pytest.mark.parametrize(("workflow", "job"), GATES)
def test_gate_passes_when_everything_succeeded(step, workflow, job):
    env = dict.fromkeys(GATES[workflow, job], "success")
    assert step(workflow, job, "gate", env).returncode == 0


@pytest.mark.parametrize(
    ("workflow", "job", "failing", "result"),
    [
        (workflow, job, var, result)
        for (workflow, job), names in GATES.items()
        for var, result in itertools.product(names, NOT_SUCCESS)
    ],
)
def test_gate_fails_on_anything_but_success(step, workflow, job, failing, result):
    env = dict.fromkeys(GATES[workflow, job], "success") | {failing: result}
    outcome = step(workflow, job, "gate", env)
    assert outcome.returncode != 0
    assert outcome.annotations("error")
