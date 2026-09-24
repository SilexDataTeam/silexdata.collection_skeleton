# SPDX-FileCopyrightText: Silex Data Solutions
# SPDX-License-Identifier: Apache-2.0
"""reusable-nox.yml: refuse matrix sessions marked default in antsibull-nox.toml."""

import pytest

MATRIX_SESSIONS = [
    "ansible_test_sanity",
    "ansible_test_units",
    "ansible_test_integration_w_default_container",
    "ansible_test_integration",
    "ee_check",
]


def check(step, tmp_path, toml):
    (tmp_path / "antsibull-nox.toml").write_text(toml)
    return step(
        "reusable-nox.yml",
        "detect",
        "nox-config",
        {"CONFIG": "antsibull-nox.toml"},
        cwd=tmp_path,
    )


@pytest.mark.parametrize("session", MATRIX_SESSIONS)
def test_a_matrix_session_marked_default_fails(step, tmp_path, session):
    result = check(step, tmp_path, f"[sessions.{session}]\ndefault = true\n")
    assert result.returncode != 0
    errors = result.annotations("error")
    assert len(errors) == 1
    assert f"[sessions.{session}] sets default = true" in errors[0]
    assert errors[0].startswith("::error file=antsibull-nox.toml,")


def test_every_offending_session_is_named(step, tmp_path):
    toml = "".join(f"[sessions.{s}]\ndefault = true\n" for s in MATRIX_SESSIONS[:2])
    result = check(step, tmp_path, toml)
    assert result.returncode != 0
    assert len(result.annotations("error")) == 2


@pytest.mark.parametrize(
    "toml",
    [
        "",
        "[collection]\nmin_python_version = '3.10'\n",
        "".join(f"[sessions.{s}]\ndefault = false\n" for s in MATRIX_SESSIONS),
        # Unset means antsibull-nox's own default, which is false.
        "[sessions.ansible_test_sanity]\nmin_version = '2.16'\n",
        # Ordinary sessions are meant to be defaults.
        "[sessions.lint]\ndefault = true\n[sessions.license_check]\ndefault = true\n",
    ],
    ids=["empty", "no-sessions", "all-false", "unset", "non-matrix-defaults"],
)
def test_configs_without_matrix_defaults_pass(step, tmp_path, toml):
    result = check(step, tmp_path, toml)
    assert result.returncode == 0, result.stdout
    assert not result.annotations("error")


def test_the_skeletons_own_config_passes(step, tmp_path):
    # The skeleton's antsibull-nox.toml.j2 sets these false; this is its shape.
    toml = """
[sessions.lint]
run_yamllint = true
[sessions.ansible_test_sanity]
default = false
min_version = "2.14"
[sessions.ansible_test_units]
default = false
min_version = "2.14"
[sessions.ansible_test_integration_w_default_container]
default = false
min_version = "2.14"
"""
    assert check(step, tmp_path, toml).returncode == 0
