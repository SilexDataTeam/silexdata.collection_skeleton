# SPDX-FileCopyrightText: Silex Data Solutions
# SPDX-License-Identifier: Apache-2.0
"""reusable-coverage.yml: the badge and the service-unavailable warning."""

import json

import pytest


@pytest.mark.parametrize(
    ("line_rate", "message", "color"),
    [
        ("0.5", "50.0%", "red"),
        ("0.599", "59.9%", "red"),
        ("0.6", "60.0%", "yellow"),
        ("0.7999", "80.0%", "brightgreen"),
        ("0.79", "79.0%", "yellow"),
        ("0.8", "80.0%", "brightgreen"),
        ("1", "100.0%", "brightgreen"),
    ],
)
def test_badge_colour_follows_thresholds(step, tmp_path, line_rate, message, color):
    reports = tmp_path / "tests" / "output" / "reports"
    (reports / "coverage").mkdir(parents=True)
    (reports / "coverage.xml").write_text(f'<coverage line-rate="{line_rate}"/>')
    result = step(
        "reusable-coverage.yml",
        "aggregate",
        "badge",
        {"THRESHOLDS": "60 80"},
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stdout
    badge = json.loads((reports / "coverage" / "coverage-badge.json").read_text())
    assert badge == {
        "schemaVersion": 1,
        "label": "coverage",
        "message": message,
        "color": color,
    }


@pytest.mark.parametrize(
    ("log", "warned"),
    [
        # The setup role's marker, however deep in ansible's indented output.
        (
            'ok: [testhost] => {\n    "msg": "SETUP_SERVICE_UNAVAILABLE: skipping live tests"\n}\n',
            True,
        ),
        ("PLAY RECAP\ntesthost : ok=3 changed=0 failed=0\n", False),
        (None, False),  # integration never started, so there is no log
    ],
)
def test_service_warning_is_raised_as_a_native_annotation(step, tmp_path, log, warned):
    if log is not None:
        (tmp_path / "integration.log").write_text(log)
    result = step(
        "reusable-coverage.yml",
        "coverage",
        "service-warning",
        {"TITLE": "Service unavailable"},
        runner={"RUNNER_TEMP": str(tmp_path)},
    )
    assert result.returncode == 0
    warnings = result.annotations("warning")
    assert bool(warnings) == warned
    if warned:
        assert warnings[0].startswith("::warning title=Service unavailable::")
