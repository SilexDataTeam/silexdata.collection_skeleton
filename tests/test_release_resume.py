# SPDX-FileCopyrightText: Silex Data Solutions
# SPDX-License-Identifier: Apache-2.0
"""reusable-release.yml: finishing a release from its tag, idempotently."""

import os
import subprocess

import pytest

WORKFLOW = "reusable-release.yml"
TOKEN = "galaxy-token-under-test-0123456789abcdef"


def git(cwd, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@localhost", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def tagged(tmp_path):
    """A checkout at tag 1.0.0 whose galaxy.yml says version 1.0.0."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "--quiet")
    (repo / "galaxy.yml").write_text(
        "namespace: silexdata\nname: cyberark\nversion: 1.0.0\n"
    )
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", "chore(release): 1.0.0")
    git(repo, "tag", "1.0.0")
    return repo


@pytest.mark.parametrize(
    "version_line", ["version: 1.0.0", "version: '1.0.0'", 'version: "1.0.0"']
)
def test_a_release_tag_can_be_resumed(step, tagged, version_line):
    (tagged / "galaxy.yml").write_text(
        f"namespace: silexdata\nname: cyberark\n{version_line}\n"
    )
    result = step(WORKFLOW, "release", "resume", {"TAG": "1.0.0"}, cwd=tagged)
    assert result.returncode == 0, result.stdout
    assert result.outputs == {"release": "true", "version": "1.0.0"}


def test_a_missing_tag_cannot_be_resumed(step, tagged):
    result = step(WORKFLOW, "release", "resume", {"TAG": "9.9.9"}, cwd=tagged)
    assert result.returncode != 0
    assert "no tag 9.9.9" in result.annotations("error")[0]
    assert "release" not in result.outputs


def test_a_tag_whose_galaxy_version_differs_is_not_a_release_tag(step, tagged):
    git(tagged, "tag", "v1")
    result = step(WORKFLOW, "release", "resume", {"TAG": "v1"}, cwd=tagged)
    assert result.returncode != 0
    assert "not a release tag" in result.annotations("error")[0]


@pytest.fixture
def fakes(tmp_path):
    """curl, ansible-galaxy and gh on PATH, each logging argv and scripted by env."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "calls.log"
    scripts = {
        "curl": 'printf "%s" "$FAKE_HTTP_STATUS"\n',
        "ansible-galaxy": 'env | grep -c "^ANSIBLE_GALAXY_SERVER_RELEASE_GALAXY_TOKEN=$EXPECT_TOKEN\\$" > "$TOKEN_SEEN"\nexit "$FAKE_PUBLISH_RC"\n',
        "gh": 'if [ "$1 $2" = "release view" ]; then exit "$FAKE_RELEASE_EXISTS_RC"; fi\n',
    }
    for name, body in scripts.items():
        path = bindir / name
        path.write_text(f'#!/usr/bin/env bash\necho "{name} $*" >> "$CALLS"\n{body}')
        path.chmod(0o755)
    seen = tmp_path / "token-seen"

    def runner(status="404", publish_rc=0, release_exists=False):
        return {
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "CALLS": str(log),
            "TOKEN_SEEN": str(seen),
            "EXPECT_TOKEN": TOKEN,
            "FAKE_HTTP_STATUS": status,
            "FAKE_PUBLISH_RC": str(publish_rc),
            "FAKE_RELEASE_EXISTS_RC": "0" if release_exists else "1",
        }

    runner.calls = lambda: log.read_text().splitlines() if log.exists() else []
    runner.token_seen = lambda: (
        seen.read_text().strip() == "1" if seen.exists() else False
    )
    return runner


PUBLISH_ENV = {
    "VERSION": "1.0.0",
    "NAMESPACE": "silexdata",
    "NAME": "cyberark",
    "GALAXY_URL": "https://galaxy.ansible.com/",
    "ANSIBLE_GALAXY_SERVER_LIST": "release_galaxy",
    "ANSIBLE_GALAXY_SERVER_RELEASE_GALAXY_URL": "https://galaxy.ansible.com/",
    "ANSIBLE_GALAXY_SERVER_RELEASE_GALAXY_TOKEN": TOKEN,
}


def publish(step, runner):
    return step(WORKFLOW, "release", "publish", PUBLISH_ENV, runner=runner)


def test_an_unpublished_version_is_published(step, fakes):
    result = publish(step, fakes(status="404"))
    assert result.returncode == 0, result.stdout
    assert result.outputs["published"] == "true"
    calls = fakes.calls()
    assert calls[0].startswith(
        "curl --silent --output /dev/null --write-out %{http_code} "
        "https://galaxy.ansible.com/api/v3/plugin/ansible/content/published/"
        "collections/index/silexdata/cyberark/versions/1.0.0/"
    )
    assert (
        calls[1]
        == "ansible-galaxy collection publish dist/silexdata-cyberark-1.0.0.tar.gz"
    )


def test_the_token_reaches_ansible_galaxy_only_through_its_environment(step, fakes):
    publish(step, fakes(status="404"))
    assert fakes.token_seen()
    assert not any(TOKEN in call for call in fakes.calls())
    assert not any("--api-key" in call or "--token" in call for call in fakes.calls())


def test_an_already_published_version_is_skipped(step, fakes):
    result = publish(step, fakes(status="200"))
    assert result.returncode == 0, result.stdout
    assert result.outputs["published"] == "false"
    assert result.annotations("notice")
    assert not any(c.startswith("ansible-galaxy") for c in fakes.calls())


@pytest.mark.parametrize("status", ["500", "401", "000", ""])
def test_an_unknown_galaxy_state_fails_rather_than_guessing(step, fakes, status):
    result = publish(step, fakes(status=status))
    assert result.returncode != 0
    assert result.annotations("error")
    assert not any(c.startswith("ansible-galaxy") for c in fakes.calls())


def test_a_failed_publish_fails_the_step(step, fakes):
    result = publish(step, fakes(status="404", publish_rc=1))
    assert result.returncode != 0
    assert "published" not in result.outputs


RELEASE_ENV = {
    "GH_TOKEN": "t",
    "VERSION": "1.0.0",
    "NAMESPACE": "silexdata",
    "NAME": "cyberark",
}


def test_a_missing_github_release_is_created_from_the_existing_tag(step, fakes):
    result = step(
        WORKFLOW,
        "release",
        "gh-release",
        RELEASE_ENV,
        runner=fakes(release_exists=False),
    )
    assert result.returncode == 0, result.stdout
    create = [c for c in fakes.calls() if c.startswith("gh release create")]
    assert create == [
        "gh release create 1.0.0 dist/silexdata-cyberark-1.0.0.tar.gz --title 1.0.0 --generate-notes --verify-tag"
    ]


def test_an_existing_github_release_is_left_alone(step, fakes):
    result = step(
        WORKFLOW,
        "release",
        "gh-release",
        RELEASE_ENV,
        runner=fakes(release_exists=True),
    )
    assert result.returncode == 0, result.stdout
    assert result.annotations("notice")
    assert not any(c.startswith("gh release create") for c in fakes.calls())


def test_an_incomplete_release_says_which_tag_to_resume(step):
    result = step(WORKFLOW, "release", "resume-hint", {"TAG": "1.0.0"})
    errors = result.annotations("error")
    assert errors and "tag 1.0.0" in errors[0] and "Actions tab" in errors[0]
