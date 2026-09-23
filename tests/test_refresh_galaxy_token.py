# SPDX-FileCopyrightText: Silex Data Solutions
# SPDX-License-Identifier: Apache-2.0
"""reusable-refresh-galaxy-token.yml: keep the Galaxy offline token alive."""

import os

import pytest

WORKFLOW = "reusable-refresh-galaxy-token.yml"
SSO_URL = (
    "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token"
)
TOKEN = "eyJhbGciOiJIUzI1NiJ9.offline-token-under-test.c2lnbmF0dXJl"


@pytest.fixture
def fake_curl(tmp_path):
    """A `curl` on PATH that records its arguments and stdin, and exits as told."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "curl").write_text(
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "$@" > "$CURL_ARGS"\n'
        'cat > "$CURL_STDIN"\n'
        'exit "$CURL_RC"\n'
    )
    (bindir / "curl").chmod(0o755)
    args, stdin = tmp_path / "curl.args", tmp_path / "curl.stdin"

    def runner(rc=0):
        return {
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "CURL_ARGS": str(args),
            "CURL_STDIN": str(stdin),
            "CURL_RC": str(rc),
        }

    runner.args = lambda: args.read_text().splitlines() if args.exists() else None
    runner.stdin = lambda: stdin.read_text() if stdin.exists() else None
    return runner


def refresh(step, token, runner):
    return step(
        WORKFLOW,
        "refresh",
        "refresh",
        {"TOKEN": token, "SSO_URL": SSO_URL},
        runner=runner,
    )


def test_the_token_is_exchanged_with_red_hat_sso(step, fake_curl):
    result = refresh(step, TOKEN, fake_curl())
    assert result.returncode == 0, result.stdout
    assert not result.annotations("error")
    args = fake_curl.args()
    assert args[0] == SSO_URL
    for flag in ("--fail", "--silent", "--show-error"):
        assert flag in args
    assert args[args.index("--output") + 1] == "/dev/null"
    assert "grant_type=refresh_token" in args
    assert "client_id=cloud-services" in args
    # curl reads the value for refresh_token from stdin.
    assert args[args.index("--data-urlencode") + 1] == "refresh_token@-"
    assert fake_curl.stdin() == TOKEN


def test_the_token_never_appears_on_curls_command_line(step, fake_curl):
    refresh(step, TOKEN, fake_curl())
    assert not any(TOKEN in arg for arg in fake_curl.args())


def test_a_rejected_token_fails_the_run(step, fake_curl):
    result = refresh(step, TOKEN, fake_curl(rc=22))
    assert result.returncode != 0
    errors = result.annotations("error")
    assert errors and "rejected" in errors[0]
    assert TOKEN not in result.stdout


def test_a_missing_token_fails_without_calling_sso(step, fake_curl):
    result = refresh(step, "", fake_curl())
    assert result.returncode != 0
    assert result.annotations("error")
    assert fake_curl.args() is None
