# SPDX-FileCopyrightText: Silex Data Solutions
# SPDX-License-Identifier: Apache-2.0
"""The harness must run steps exactly as the runner would, no stricter.

A stricter shell reports bugs CI never has; a laxer one misses bugs it does.
"""

import subprocess

import pytest

from conftest import SHELLS, effective_shell


def workflow(step_shell=None, job_shell=None, workflow_shell=None):
    step = {"run": "true"} | ({"shell": step_shell} if step_shell else {})
    job = {"steps": [step]}
    if job_shell:
        job["defaults"] = {"run": {"shell": job_shell}}
    data = {"jobs": {"j": job}}
    if workflow_shell:
        data["defaults"] = {"run": {"shell": workflow_shell}}
    return data, step


@pytest.mark.parametrize(
    ("shells", "expected"),
    [
        ({}, None),
        ({"workflow_shell": "bash"}, "bash"),
        ({"job_shell": "bash"}, "bash"),
        ({"step_shell": "bash"}, "bash"),
        ({"workflow_shell": "sh", "job_shell": "bash"}, "bash"),
        ({"job_shell": "sh", "step_shell": "bash"}, "bash"),
    ],
)
def test_the_closest_shell_setting_wins(shells, expected):
    data, step = workflow(**shells)
    assert effective_shell(data, "j", step) == expected


def run(shell, script, tmp_path):
    path = tmp_path / "s.sh"
    path.write_text(script)
    return subprocess.run(
        [*SHELLS[shell], str(path)], capture_output=True, text=True, check=False
    )


def test_default_shell_stops_on_error_but_not_on_a_failing_pipeline(tmp_path):
    assert run(None, "false\necho reached\n", tmp_path).returncode != 0
    result = run(None, "false | true\necho reached\n", tmp_path)
    assert result.returncode == 0
    assert result.stdout == "reached\n"


def test_explicit_bash_also_stops_on_a_failing_pipeline(tmp_path):
    result = run("bash", "false | true\necho reached\n", tmp_path)
    assert result.returncode != 0
    assert result.stdout == ""
