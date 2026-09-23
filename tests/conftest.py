# SPDX-FileCopyrightText: Silex Data Solutions
# SPDX-License-Identifier: Apache-2.0
"""Run a single `run:` step of a reusable workflow in isolation.

The steps under test are the ones that make decisions - version floors,
release versions, pass/fail gates - so they are exercised here against
fixtures before a change reaches any collection.

A step is addressed by workflow file, job id and step id, and receives its
inputs only through the environment. That is a requirement, not a convenience:
a step that interpolates `${{ }}` into its script cannot be run outside
GitHub Actions, and is open to template injection there.
"""

import dataclasses
import os
import pathlib
import subprocess

import pytest
import yaml

WORKFLOWS = pathlib.Path(__file__).resolve().parent.parent / ".github" / "workflows"

# GitHub's default for `shell: bash` on Linux runners.
BASH = ["bash", "--noprofile", "--norc", "-eo", "pipefail"]


@dataclasses.dataclass
class StepResult:
    returncode: int
    stdout: str
    outputs: dict

    def annotations(self, kind):
        """Workflow-command lines of one kind, e.g. 'error' or 'notice'."""
        return [
            line for line in self.stdout.splitlines() if line.startswith(f"::{kind}")
        ]


def load_step(workflow, job, step_id):
    data = yaml.safe_load((WORKFLOWS / workflow).read_text())
    steps = [s for s in data["jobs"][job]["steps"] if s.get("id") == step_id]
    assert len(steps) == 1, (
        f"{workflow}: job {job!r} has {len(steps)} steps with id {step_id!r}"
    )
    step = steps[0]
    assert "${{" not in step["run"], (
        f"{workflow} {job}/{step_id}: pass inputs through env:, not ${{{{ }}}} in the script"
    )
    return step


def run_step(tmp_path, workflow, job, step_id, env, cwd=None, runner=None):
    """Run the step with exactly the env it declares, and return its result.

    `runner` holds variables the runner itself provides, such as RUNNER_TEMP,
    which a step uses without declaring.
    """
    step = load_step(workflow, job, step_id)
    declared = set(step.get("env") or {})
    assert set(env) == declared, (
        f"{workflow} {job}/{step_id} declares env {sorted(declared)}; the test passed {sorted(env)}"
    )
    script = tmp_path / f"{job}-{step_id}.sh"
    script.write_text(step["run"])
    output_file = tmp_path / f"{job}-{step_id}.output"
    output_file.write_text("")
    proc = subprocess.run(
        [*BASH, str(script)],
        cwd=cwd or tmp_path,
        env={
            # The interpreter setup-python put on PATH is the one with PyYAML.
            "PATH": os.environ["PATH"],
            "HOME": str(tmp_path),
            "GITHUB_OUTPUT": str(output_file),
            **(runner or {}),
            **env,
        },
        capture_output=True,
        text=True,
        check=False,
    )
    outputs = dict(
        line.split("=", 1)
        for line in output_file.read_text().splitlines()
        if "=" in line
    )
    return StepResult(proc.returncode, proc.stdout + proc.stderr, outputs)


@pytest.fixture
def step(tmp_path):
    """`step(workflow, job, step_id, env, cwd=None, runner=None)` -> StepResult."""
    return lambda *args, **kwargs: run_step(tmp_path, *args, **kwargs)
