# SPDX-FileCopyrightText: Silex Data Solutions
# SPDX-License-Identifier: Apache-2.0
"""reusable-sync-rules.yml: mirror skeleton/.claude into a collection."""

import os
import subprocess

import pytest
import yaml

WORKFLOW = "reusable-sync-rules.yml"
SRC = ".skeleton-src/skeleton/.claude"
BRANCH = "sync/claude-rules"
FRAGMENT = "changelogs/fragments/sync-claude-rules.yml"

SKELETON = {
    "CLAUDE.md.j2": "# {{ namespace }}.{{ collection_name }}\n",
    "rules/ci.md": "ci rules v2\n",
    "rules/licensing.md": "licensing rules\n",
    "skills/setup/SKILL.md": "setup skill\n",
}
COLLECTION = {
    "CLAUDE.md": "# silexdata.cyberark - tailored\n",
    "rules/ci.md": "ci rules v2\n",
    "rules/licensing.md": "licensing rules\n",
    "skills/setup/SKILL.md": "setup skill\n",
}


def git(cwd, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@localhost", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def write_tree(root, files):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def tree(root):
    return {
        str(p.relative_to(root)): p.read_text()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


@pytest.fixture
def collection(tmp_path):
    """A clone of a collection whose origin/main holds COLLECTION's .claude/."""
    origin, clone = tmp_path / "origin.git", tmp_path / "clone"
    git(tmp_path, "init", "--quiet", "--bare", "--initial-branch=main", str(origin))
    git(tmp_path, "clone", "--quiet", str(origin), str(clone))
    write_tree(clone / ".claude", COLLECTION)
    git(clone, "add", "-A")
    git(clone, "commit", "--quiet", "-m", "base")
    git(clone, "push", "--quiet", "origin", "main")
    write_tree(clone / SRC, SKELETON)
    return clone


def mirror(step, cwd):
    return step(WORKFLOW, "sync", "mirror", {"SRC": SRC, "DEST": ".claude"}, cwd=cwd)


def test_in_sync_changes_nothing(step, collection):
    result = mirror(step, collection)
    assert result.returncode == 0, result.stdout
    assert result.outputs["changed"] == "false"
    assert tree(collection / ".claude") == COLLECTION


@pytest.mark.parametrize(
    "drift",
    [
        lambda c: (c / ".claude/rules/ci.md").write_text(
            "ci rules v1, edited locally\n"
        ),
        lambda c: (c / ".claude/rules/licensing.md").unlink(),
        lambda c: (c / ".claude/rules/extra.md").write_text("not in the skeleton\n"),
        lambda c: (
            (c / ".claude/skills/local/SKILL.md").parent.mkdir(parents=True)
            or (c / ".claude/skills/local/SKILL.md").write_text("local skill\n")
        ),
    ],
    ids=["edited", "deleted", "extra-rule", "extra-skill"],
)
def test_drift_is_mirrored_away(step, collection, drift):
    drift(collection)
    git(collection, "add", "-A", ".claude")
    git(collection, "commit", "--quiet", "-m", "drift")
    result = mirror(step, collection)
    assert result.returncode == 0, result.stdout
    assert result.outputs["changed"] == "true"
    assert tree(collection / ".claude") == COLLECTION


def test_skeleton_changes_arrive(step, collection):
    write_tree(
        collection / SRC,
        {"rules/new.md": "a new rule\n", "rules/ci.md": "ci rules v3\n"},
    )
    result = mirror(step, collection)
    assert result.outputs["changed"] == "true"
    synced = tree(collection / ".claude")
    assert synced["rules/new.md"] == "a new rule\n"
    assert synced["rules/ci.md"] == "ci rules v3\n"


def test_claude_md_is_the_collections_own(step, collection):
    (collection / ".claude/CLAUDE.md").write_text("# edited for this collection\n")
    git(collection, "commit", "--quiet", "-am", "tailor")
    result = mirror(step, collection)
    assert result.outputs["changed"] == "false"
    assert (
        collection / ".claude/CLAUDE.md"
    ).read_text() == "# edited for this collection\n"
    assert not (collection / ".claude/CLAUDE.md.j2").exists()


def test_other_templates_are_refused(step, collection):
    write_tree(collection / SRC, {"rules/per-collection.md.j2": "{{ namespace }}\n"})
    result = mirror(step, collection)
    assert result.returncode != 0
    assert result.annotations("error")
    assert tree(collection / ".claude") == COLLECTION


def test_missing_skeleton_source_fails(step, collection):
    subprocess.run(["rm", "-rf", str(collection / ".skeleton-src")], check=True)
    result = mirror(step, collection)
    assert result.returncode != 0
    assert result.annotations("error")


def commit(step, cwd):
    return step(
        WORKFLOW, "sync", "commit", {"BRANCH": BRANCH, "FRAGMENT": FRAGMENT}, cwd=cwd
    )


@pytest.fixture
def drifted(collection):
    """The collection with a drifted rule committed and pushed to main."""
    (collection / ".claude/rules/ci.md").write_text("drifted\n")
    git(collection, "commit", "--quiet", "-am", "drift")
    git(collection, "push", "--quiet", "origin", "main")
    return collection


def sync(step, collection):
    """One workflow run: a fresh checkout of main, mirrored, then committed."""
    git(collection, "fetch", "--quiet", "origin")
    git(collection, "switch", "--quiet", "main")
    git(collection, "reset", "--quiet", "--hard", "origin/main")
    assert mirror(step, collection).outputs["changed"] == "true"
    return commit(step, collection)


def test_sync_is_pushed_with_a_trivial_fragment(step, drifted):
    collection = drifted
    result = sync(step, collection)
    assert result.returncode == 0, result.stdout
    assert result.outputs["pushed"] == "true"
    pushed = git(collection, "ls-tree", "-r", "--name-only", f"origin/{BRANCH}")
    assert FRAGMENT in pushed.splitlines()
    # Exactly what the collection's yamllint and antsibull-changelog accept: a
    # document start, then a trivial section, which never triggers a release.
    fragment = git(collection, "show", f"origin/{BRANCH}:{FRAGMENT}")
    assert fragment.startswith("---\n")
    assert yaml.safe_load(fragment) == {
        "trivial": ["Sync .claude/ with the collection skeleton."]
    }
    assert (
        git(collection, "show", f"origin/{BRANCH}:.claude/rules/ci.md")
        == "ci rules v2\n"
    )
    # Only .claude/ and the fragment change; nothing else is swept in.
    changed = git(collection, "diff", "--name-only", "origin/main", f"origin/{BRANCH}")
    assert sorted(changed.split()) == [".claude/rules/ci.md", FRAGMENT]


def test_an_identical_sync_is_not_re_pushed(step, drifted):
    collection = drifted
    sync(step, collection)
    first = git(collection, "rev-parse", f"origin/{BRANCH}")
    result = sync(step, collection)
    assert result.outputs["pushed"] == "false"
    assert git(collection, "rev-parse", f"origin/{BRANCH}") == first


def test_the_branch_follows_the_default_branch(step, drifted):
    collection = drifted
    sync(step, collection)
    git(collection, "switch", "--quiet", "main")
    git(collection, "reset", "--quiet", "--hard", "origin/main")
    (collection / "README.md").write_text("main moved on\n")
    git(collection, "add", "README.md")
    git(collection, "commit", "--quiet", "-m", "unrelated")
    git(collection, "push", "--quiet", "origin", "main")
    result = sync(step, collection)
    assert result.outputs["pushed"] == "true"
    assert "README.md" in git(collection, "ls-tree", "--name-only", f"origin/{BRANCH}")


@pytest.fixture
def fake_gh(tmp_path):
    """A `gh` on PATH that logs its calls and plays back canned answers."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "gh.log"
    (bindir / "gh").write_text(
        "#!/usr/bin/env bash\n"
        'echo "$*" >> "$GH_LOG"\n'
        'case "$1 $2" in\n'
        '  "pr list") printf "%s" "$GH_EXISTING" ;;\n'
        '  "pr create") printf "%s\\n" "$GH_CREATE_OUT"; exit "$GH_CREATE_RC" ;;\n'
        "  *) exit 99 ;;\n"
        "esac\n"
    )
    (bindir / "gh").chmod(0o755)

    def runner(existing="", create_out="", create_rc=0):
        return {
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "GH_LOG": str(log),
            "GH_EXISTING": existing,
            "GH_CREATE_OUT": create_out,
            "GH_CREATE_RC": str(create_rc),
        }

    runner.calls = lambda: log.read_text().splitlines() if log.exists() else []
    return runner


PR_ENV = {
    "GH_TOKEN": "t",
    "REPO": "SilexDataTeam/silexdata.cyberark",
    "SERVER": "https://github.com",
    "BRANCH": BRANCH,
    "BASE": "main",
}


def open_pr(step, runner):
    return step(WORKFLOW, "sync", "pr", PR_ENV, runner=runner)


def test_an_open_sync_pr_is_reused(step, fake_gh):
    url = "https://github.com/SilexDataTeam/silexdata.cyberark/pull/7"
    result = open_pr(step, fake_gh(existing=url))
    assert result.returncode == 0
    assert result.outputs["url"] == url
    assert not any(c.startswith("pr create") for c in fake_gh.calls())


def test_a_new_pr_is_opened_against_the_default_branch(step, fake_gh):
    url = "https://github.com/SilexDataTeam/silexdata.cyberark/pull/8"
    result = open_pr(step, fake_gh(create_out=url))
    assert result.returncode == 0, result.stdout
    assert result.outputs["url"] == url
    assert result.annotations("notice")
    create = [c for c in fake_gh.calls() if c.startswith("pr create")]
    assert len(create) == 1 and f"--base main --head {BRANCH}" in create[0]


def test_an_org_that_forbids_actions_prs_gets_a_one_click_link(step, fake_gh):
    refusal = (
        "pull request create failed: GraphQL: "
        "GitHub Actions is not permitted to create or approve pull requests (createPullRequest)"
    )
    result = open_pr(step, fake_gh(create_out=refusal, create_rc=1))
    assert result.returncode == 0, result.stdout
    link = f"https://github.com/SilexDataTeam/silexdata.cyberark/compare/main...{BRANCH}?expand=1"
    assert result.outputs["url"] == link
    warnings = result.annotations("warning")
    assert warnings and link in warnings[0]


def test_any_other_pr_failure_fails_the_run(step, fake_gh):
    result = open_pr(step, fake_gh(create_out="HTTP 502: Bad Gateway", create_rc=1))
    assert result.returncode != 0
    assert result.annotations("error")
    assert "url" not in result.outputs
